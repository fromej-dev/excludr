"""Review passes: plan state, AI screening allowances and Stripe Checkout.

Usage is never stored as a counter: it is the number of distinct articles with an
AI decision at a stage, so re-screening an article (e.g. after criteria changed)
does not consume allowance again and the count cannot drift.

Everything here is a no-op while ``settings.billing_enabled`` is off, so
development, self-hosting and the existing tests run without limits.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import distinct, exists, func
from sqlmodel import Session, select

from app.core.config import get_settings
from app.features.audit import services as audit
from app.features.projects.models import Project
from app.features.research.models import Article
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningStage,
)
from app.features.users.models import User
from . import plans, stripe_client
from .models import Payment, PaymentStatus, PlanSource, ProjectPlan, StripeEvent

logger = logging.getLogger(__name__)

PASS_ACTIVATED = "billing.pass_activated"
PASS_UPGRADED = "billing.pass_upgraded"
PASS_EXTENDED = "billing.pass_extended"
PASS_GRANTED = "billing.pass_granted"
PASS_CHANGED = "billing.pass_changed"
PASS_REFUNDED = "billing.pass_refunded"
PAYMENT_REFUNDED = "billing.payment_refunded"


class BillingError(Exception):
    """A plan rule blocks the action (mapped to HTTP 402 by the routers)."""


class QuotaExceededError(BillingError):
    pass


class ReadOnlyProjectError(BillingError):
    pass


class PlanRequiredError(BillingError):
    pass


READ_ONLY_MESSAGE = (
    "This review's pass has expired, so the project is read-only. "
    "Renew the pass to make changes; viewing and exports stay available."
)


def billing_enabled() -> bool:
    return get_settings().billing_enabled


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; they are stored as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_plan(session: Session, project_id: int) -> Optional[ProjectPlan]:
    return session.exec(
        select(ProjectPlan).where(ProjectPlan.project_id == project_id)
    ).first()


def is_active(plan: Optional[ProjectPlan], now: Optional[datetime] = None) -> bool:
    return plan is not None and _aware(plan.expires_at) > (now or _now())


def is_read_only(session: Session, project: Project) -> bool:
    """True when the project's pass has expired (free projects never are)."""
    if not billing_enabled():
        return False
    plan = get_plan(session, project.id)
    return plan is not None and not is_active(plan)


def ensure_writable(session: Session, project: Project) -> None:
    if is_read_only(session, project):
        raise ReadOnlyProjectError(READ_ONLY_MESSAGE)


@dataclass(frozen=True)
class Allowance:
    stage: ScreeningStage
    used: int
    limit: int
    scope: str  # "project" (pass) or "account" (free, shared by unpaid projects)

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


def _count_ai_screened(
    session: Session, project_ids: list[int], stage: ScreeningStage
) -> int:
    if not project_ids:
        return 0
    return session.exec(
        select(func.count(distinct(ScreeningDecision.article_id)))
        .join(Article, Article.id == ScreeningDecision.article_id)
        .where(
            Article.project_id.in_(project_ids),
            ScreeningDecision.source == DecisionSource.ai_agent,
            ScreeningDecision.stage == stage,
        )
    ).one()


def _unpaid_project_ids(session: Session, owner_id: int) -> list[int]:
    has_plan = exists().where(ProjectPlan.project_id == Project.id)
    return list(
        session.exec(
            select(Project.id).where(Project.owner_id == owner_id, ~has_plan)
        ).all()
    )


def get_allowance(
    session: Session, project: Project, stage: ScreeningStage
) -> Allowance:
    """How many articles the AI may screen at ``stage``, and how many it has."""
    plan = get_plan(session, project.id)
    full_text = stage == ScreeningStage.full_text
    if plan is not None:
        limit = plan.fulltext_limit if full_text else plans.PASS_TITLE_ABSTRACT_LIMIT
        used = _count_ai_screened(session, [project.id], stage)
        return Allowance(stage, used, limit, "project")
    limit = plans.FREE_FULLTEXT_LIMIT if full_text else plans.FREE_TITLE_ABSTRACT_LIMIT
    used = _count_ai_screened(
        session, _unpaid_project_ids(session, project.owner_id), stage
    )
    return Allowance(stage, used, limit, "account")


def _quota_message(allowance: Allowance) -> str:
    stage = (
        "full-text"
        if allowance.stage == ScreeningStage.full_text
        else ("title/abstract")
    )
    if allowance.scope == "account":
        return (
            f"Your free AI allowance of {allowance.limit} {stage} articles is used "
            "up. Get a review pass for this project to keep screening with AI."
        )
    return (
        f"This review pass covers AI screening of {allowance.limit} {stage} "
        "articles and they are used up. Upgrade the pass to screen more."
    )


def _already_ai_screened(
    session: Session, article_ids: list[int], stage: ScreeningStage
) -> set[int]:
    if not article_ids:
        return set()
    return set(
        session.exec(
            select(ScreeningDecision.article_id).where(
                ScreeningDecision.article_id.in_(article_ids),
                ScreeningDecision.source == DecisionSource.ai_agent,
                ScreeningDecision.stage == stage,
            )
        ).all()
    )


def check_can_ai_screen(session: Session, project: Project, article: Article) -> None:
    """Raise a :class:`BillingError` if the AI may not screen ``article`` now."""
    if not billing_enabled():
        return
    ensure_writable(session, project)
    stage = article.current_stage
    if article.id in _already_ai_screened(session, [article.id], stage):
        return  # re-screening is free
    allowance = get_allowance(session, project, stage)
    if allowance.remaining <= 0:
        raise QuotaExceededError(_quota_message(allowance))


def split_by_allowance(
    session: Session, project: Project, article_ids: list[int]
) -> tuple[list[int], int]:
    """Keep the articles the allowance covers, in order; return them and the
    number left out. Raises :class:`QuotaExceededError` if none fit."""
    if not billing_enabled() or not article_ids:
        return article_ids, 0
    ensure_writable(session, project)
    stages = dict(
        session.exec(
            select(Article.id, Article.current_stage).where(Article.id.in_(article_ids))
        ).all()
    )
    remaining: dict[ScreeningStage, int] = {}
    rescreens: set[int] = set()
    allowances: dict[ScreeningStage, Allowance] = {}
    for stage in set(stages.values()):
        ids = [i for i in article_ids if stages.get(i) == stage]
        rescreens |= _already_ai_screened(session, ids, stage)
        allowances[stage] = get_allowance(session, project, stage)
        remaining[stage] = allowances[stage].remaining
    kept: list[int] = []
    for article_id in article_ids:
        stage = stages.get(article_id)
        if stage is None:
            continue
        if article_id in rescreens:
            kept.append(article_id)
        elif remaining[stage] > 0:
            remaining[stage] -= 1
            kept.append(article_id)
    if not kept:
        exhausted = next(iter(allowances.values()))
        raise QuotaExceededError(_quota_message(exhausted))
    return kept, len(article_ids) - len(kept)


def ensure_dual_screening_allowed(session: Session, project: Project) -> None:
    if billing_enabled() and not is_active(get_plan(session, project.id)):
        raise PlanRequiredError(
            "Dual screening needs a review pass. Get one for this project first."
        )


# --- Status ------------------------------------------------------------------


def upgrade_options(session: Session, project: Project) -> list[dict[str, Any]]:
    """Tiers the owner can buy now, with the amount to pay for each."""
    plan = get_plan(session, project.id)
    if not is_active(plan):
        return [
            {
                "tier": t.code,
                "label": t.label,
                "fulltext_limit": t.fulltext_limit,
                "amount_cents": t.price_cents,
                "kind": "renewal" if plan else "new",
            }
            for t in plans.TIERS.values()
        ]
    current = plans.TIERS.get(plan.tier)
    if current is None:  # custom grants are changed by hand
        return []
    return [
        {
            "tier": t.code,
            "label": t.label,
            "fulltext_limit": t.fulltext_limit,
            "amount_cents": t.price_cents - current.price_cents,
            "kind": "upgrade",
        }
        for t in plans.TIERS.values()
        if t.fulltext_limit > plan.fulltext_limit
        and t.price_cents > current.price_cents
    ]


def _usage(allowance: Allowance) -> dict[str, Any]:
    return {"used": allowance.used, "limit": allowance.limit, "scope": allowance.scope}


def get_status(session: Session, project: Project) -> dict[str, Any]:
    plan = get_plan(session, project.id)
    tier = plans.TIERS.get(plan.tier) if plan else None
    if plan is None:
        label = "No review pass yet"
    elif tier is not None:
        label = tier.label
    else:
        label = f"Custom pass, up to {plan.fulltext_limit:,} full texts"
    enabled = billing_enabled()
    return {
        "billing_enabled": enabled,
        "plan": plan.tier if plan else "free",
        "plan_label": label,
        "active": is_active(plan),
        "read_only": enabled and plan is not None and not is_active(plan),
        "expires_at": _aware(plan.expires_at) if plan else None,
        "full_text": _usage(get_allowance(session, project, ScreeningStage.full_text)),
        "title_abstract": _usage(
            get_allowance(session, project, ScreeningStage.title_abstract)
        ),
        "dual_screening_allowed": not enabled or is_active(plan),
        "currency": plans.CURRENCY,
        "options": upgrade_options(session, project) if enabled else [],
        # Without Stripe keys passes are granted by an admin instead of bought here
        "online_payment": enabled and bool(get_settings().stripe_secret_key),
    }


def public_plans() -> dict[str, Any]:
    return {
        "billing_enabled": billing_enabled(),
        "currency": plans.CURRENCY,
        "pass_duration_days": plans.PASS_DURATION_DAYS,
        "free": {"fulltext_limit": plans.FREE_FULLTEXT_LIMIT},
        "tiers": [
            {
                "tier": t.code,
                "label": t.label,
                "fulltext_limit": t.fulltext_limit,
                "price_cents": t.price_cents,
            }
            for t in plans.TIERS.values()
        ],
    }


# --- Checkout and webhooks ---------------------------------------------------


async def create_checkout(
    session: Session, project: Project, user: User, tier_code: str
) -> str:
    """Start a Stripe Checkout payment for ``tier_code`` and return its URL.

    Raises:
        ValueError: the tier cannot be bought for this project right now.
        stripe_client.StripeError: Stripe rejected the request.
    """
    settings = get_settings()
    option = next(
        (o for o in upgrade_options(session, project) if o["tier"] == tier_code), None
    )
    if option is None:
        raise ValueError("This pass cannot be bought for this project")
    base = settings.public_app_url.rstrip("/")
    name = (
        option["label"]
        if option["kind"] != "upgrade"
        else (f"Upgrade to {option['label'][0].lower()}{option['label'][1:]}")
    )
    params: dict[str, Any] = {
        "mode": "payment",
        "client_reference_id": str(project.id),
        "customer_email": user.email,
        "success_url": f"{base}/projects/{project.id}?billing=success",
        "cancel_url": f"{base}/projects/{project.id}?billing=cancelled",
        "line_items": [
            {
                "quantity": 1,
                "price_data": {
                    "currency": plans.CURRENCY,
                    "unit_amount": option["amount_cents"],
                    "product_data": {
                        "name": name,
                        "description": f"Excludr project: {project.name}",
                    },
                },
            }
        ],
        "invoice_creation": {"enabled": True},
        "metadata": {
            "project_id": project.id,
            "tier": tier_code,
            "kind": option["kind"],
            "user_id": user.id,
        },
    }
    if settings.stripe_automatic_tax:
        params["automatic_tax"] = {"enabled": True}
    checkout = await stripe_client.create_checkout_session(
        settings.stripe_secret_key or "", params
    )
    return checkout["url"]


PAID_EVENTS = frozenset(
    {"checkout.session.completed", "checkout.session.async_payment_succeeded"}
)


def handle_event(session: Session, event: dict[str, Any]) -> str:
    """Apply a verified Stripe event once. Returns what happened (for logs/tests)."""
    event_id = event.get("id")
    if not event_id:
        return "ignored"
    if session.get(StripeEvent, event_id) is not None:
        return "duplicate"
    session.add(StripeEvent(id=event_id, type=str(event.get("type", ""))[:100]))
    outcome = "ignored"
    obj = (event.get("data") or {}).get("object") or {}
    if event.get("type") in PAID_EVENTS:
        if obj.get("payment_status") == "paid":
            outcome = _apply_checkout(session, obj)
    elif event.get("type") == "charge.refunded":
        outcome = _apply_refund(session, obj)
    session.commit()
    return outcome


def _apply_checkout(session: Session, checkout: dict[str, Any]) -> str:
    metadata = checkout.get("metadata") or {}
    tier = plans.TIERS.get(metadata.get("tier", ""))
    try:
        project = session.get(Project, int(metadata.get("project_id", "")))
        user_id = int(metadata["user_id"]) if metadata.get("user_id") else None
    except ValueError:
        project, user_id = None, None
    if tier is None or project is None:
        logger.error("Paid checkout %s has unusable metadata", checkout.get("id"))
        return "ignored"
    existing = session.exec(
        select(Payment).where(Payment.stripe_checkout_session_id == checkout.get("id"))
    ).first()
    if existing is not None:
        return "duplicate"  # same checkout reported by another event
    amount = int(checkout.get("amount_total") or 0)
    now = _now()
    plan = get_plan(session, project.id)
    active = is_active(plan, now)
    session.add(
        Payment(
            project_id=project.id,
            project_name=project.name[:100],
            user_id=user_id,
            stripe_checkout_session_id=str(checkout.get("id")),
            stripe_payment_intent=checkout.get("payment_intent"),
            tier=tier.code,
            kind=str(metadata.get("kind") or "new")[:20],
            amount_cents=amount,
            currency=str(checkout.get("currency") or plans.CURRENCY)[:3],
            plan_before=_snapshot(plan),
        )
    )
    if plan is None:
        plan = ProjectPlan(
            project_id=project.id,
            tier=tier.code,
            fulltext_limit=tier.fulltext_limit,
            activated_at=now,
            expires_at=now,
            source=PlanSource.stripe,
        )
    if metadata.get("kind") == "upgrade" and plan.id is not None:
        # Paid the difference: bigger limit, same expiry date.
        plan.tier = tier.code
        plan.fulltext_limit = max(plan.fulltext_limit, tier.fulltext_limit)
        action = PASS_UPGRADED
    elif active:
        # The same pass bought again while running: add another term.
        plan.expires_at = _aware(plan.expires_at) + timedelta(
            days=plans.PASS_DURATION_DAYS
        )
        action = PASS_EXTENDED
    else:
        # New pass, or renewal of an expired one.
        plan.tier = tier.code
        plan.fulltext_limit = tier.fulltext_limit
        plan.activated_at = now
        plan.expires_at = now + timedelta(days=plans.PASS_DURATION_DAYS)
        action = PASS_ACTIVATED
    plan.source = PlanSource.stripe
    plan.stripe_checkout_session_id = checkout.get("id")
    plan.amount_paid_cents = (plan.amount_paid_cents or 0) + amount
    plan.updated_at = now
    session.add(plan)
    audit.record_event(
        session,
        project.id,
        action,
        "project_plan",
        None,
        user_id,
        {"tier": tier.code, "amount_cents": amount, "checkout": checkout.get("id")},
    )
    return action


def _snapshot(plan: Optional[ProjectPlan]) -> Optional[dict[str, Any]]:
    if plan is None:
        return None
    return {
        "tier": plan.tier,
        "fulltext_limit": plan.fulltext_limit,
        "activated_at": _aware(plan.activated_at).isoformat(),
        "expires_at": _aware(plan.expires_at).isoformat(),
        "source": plan.source,
    }


def _apply_refund(session: Session, charge: dict[str, Any]) -> str:
    """Record a Stripe refund; a full refund of the latest payment undoes it."""
    intent = charge.get("payment_intent")
    payment = (
        session.exec(
            select(Payment).where(Payment.stripe_payment_intent == intent)
        ).first()
        if intent
        else None
    )
    if payment is None:
        logger.warning("Refund for unknown payment intent %s", intent)
        return "ignored"
    payment.refunded_cents = int(charge.get("amount_refunded") or 0)
    full = payment.refunded_cents >= payment.amount_cents
    payment.status = (
        PaymentStatus.refunded if full else PaymentStatus.partially_refunded
    )
    session.add(payment)
    if payment.project_id is None:
        return PAYMENT_REFUNDED
    details = {"payment_id": payment.id, "refunded_cents": payment.refunded_cents}
    latest_id = session.exec(
        select(func.max(Payment.id)).where(Payment.project_id == payment.project_id)
    ).one()
    if not full or latest_id != payment.id:
        # Partial refunds, and refunds of a payment later ones built on, leave
        # the plan alone: an admin adjusts it by hand if needed.
        details["plan_unchanged"] = True
        action = PAYMENT_REFUNDED
    else:
        _restore_plan(session, payment.project_id, payment.plan_before)
        action = PASS_REFUNDED
    audit.record_event(
        session, payment.project_id, action, "payment", payment.id, None, details
    )
    return action


def _restore_plan(
    session: Session, project_id: int, before: Optional[dict[str, Any]]
) -> None:
    plan = get_plan(session, project_id)
    if before is None:
        if plan is not None:
            session.delete(plan)  # back to the free tier
        return
    if plan is None:
        plan = ProjectPlan(
            project_id=project_id, amount_paid_cents=0, **_restored(before)
        )
    else:
        for key, value in _restored(before).items():
            setattr(plan, key, value)
    plan.updated_at = _now()
    session.add(plan)


def _restored(before: dict[str, Any]) -> dict[str, Any]:
    return {
        "tier": before["tier"],
        "fulltext_limit": before["fulltext_limit"],
        "activated_at": datetime.fromisoformat(before["activated_at"]),
        "expires_at": datetime.fromisoformat(before["expires_at"]),
        "source": before["source"],
    }


def update_pass(
    session: Session,
    project: Project,
    admin: User,
    fulltext_limit: Optional[int] = None,
    expires_at: Optional[datetime] = None,
) -> ProjectPlan:
    """Change a project's pass by hand: its limit and/or end date.

    Raises:
        LookupError: the project has no pass (grant one instead).
    """
    plan = get_plan(session, project.id)
    if plan is None:
        raise LookupError("This project has no pass; grant one instead")
    before = _snapshot(plan)
    if fulltext_limit is not None:
        plan.fulltext_limit = fulltext_limit
    if expires_at is not None:
        plan.expires_at = _aware(expires_at)
    plan.updated_at = _now()
    session.add(plan)
    audit.record_event(
        session,
        project.id,
        PASS_CHANGED,
        "project_plan",
        None,
        admin.id,
        {"before": before, "after": _snapshot(plan)},
    )
    session.refresh(plan)
    return plan


def grant_pass(
    session: Session,
    project: Project,
    admin: User,
    tier_code: str,
    fulltext_limit: Optional[int],
    days: int,
) -> ProjectPlan:
    """Give a project a pass by hand (invoice/PO payments, pilots, discounts)."""
    tier = plans.TIERS.get(tier_code)
    if tier is None and tier_code != plans.CUSTOM_TIER:
        raise ValueError(f"Unknown tier '{tier_code}'")
    limit = fulltext_limit or (tier.fulltext_limit if tier else None)
    if not limit:
        raise ValueError("A custom pass needs a full-text limit")
    now = _now()
    plan = get_plan(session, project.id) or ProjectPlan(
        project_id=project.id,
        tier=tier_code,
        fulltext_limit=limit,
        activated_at=now,
        expires_at=now,
        source=PlanSource.admin,
    )
    plan.tier = tier_code
    plan.fulltext_limit = limit
    plan.activated_at = now
    plan.expires_at = now + timedelta(days=days)
    plan.source = PlanSource.admin
    plan.granted_by = admin.id
    plan.updated_at = now
    session.add(plan)
    audit.record_event(
        session,
        project.id,
        PASS_GRANTED,
        "project_plan",
        None,
        admin.id,
        {"tier": tier_code, "fulltext_limit": limit, "days": days},
    )
    session.refresh(plan)
    return plan
