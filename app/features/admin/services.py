"""Read models for the admin area: users, projects with their plans, payments
and headline numbers. Aggregates are computed per page with grouped queries."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, distinct, func, or_
from sqlmodel import Session, select

from app.core.config import get_settings
from app.features.ai_usage import services as ai_usage
from app.features.billing import plans
from app.features.billing import services as billing
from app.features.billing.models import Payment, ProjectPlan
from app.features.projects.models import Project
from app.features.research.models import Article
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningStage,
)
from app.features.users.models import User

EXPIRING_DAYS = 30
PROJECT_STATES = ("free", "active", "expiring", "expired")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.lower()}%"


def _page(items: list[Any], total: int, page: int, page_size: int) -> dict[str, Any]:
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# --- Projects ------------------------------------------------------------------


def _ai_fulltext_by_project(session: Session, project_ids: list[int]) -> dict[int, int]:
    if not project_ids:
        return {}
    rows = session.exec(
        select(Article.project_id, func.count(distinct(ScreeningDecision.article_id)))
        .join(Article, Article.id == ScreeningDecision.article_id)
        .where(
            Article.project_id.in_(project_ids),
            ScreeningDecision.source == DecisionSource.ai_agent,
            ScreeningDecision.stage == ScreeningStage.full_text,
        )
        .group_by(Article.project_id)
    ).all()
    return dict(rows)


def _articles_by_project(session: Session, project_ids: list[int]) -> dict[int, int]:
    if not project_ids:
        return {}
    rows = session.exec(
        select(Article.project_id, func.count(Article.id))
        .where(Article.project_id.in_(project_ids))
        .group_by(Article.project_id)
    ).all()
    return dict(rows)


def _state(plan: Optional[ProjectPlan], now: datetime) -> str:
    if plan is None:
        return "free"
    expires = billing._aware(plan.expires_at)
    if expires <= now:
        return "expired"
    return "expiring" if expires <= now + timedelta(days=EXPIRING_DAYS) else "active"


def _plan_summary(plan: Optional[ProjectPlan], now: datetime) -> Optional[dict]:
    if plan is None:
        return None
    return {
        "tier": plan.tier,
        "fulltext_limit": plan.fulltext_limit,
        "activated_at": billing._aware(plan.activated_at),
        "expires_at": billing._aware(plan.expires_at),
        "source": plan.source,
        "amount_paid_cents": plan.amount_paid_cents,
        "active": billing.is_active(plan, now),
    }


def _project_rows(
    session: Session, rows: list[tuple[Project, Optional[ProjectPlan], Optional[User]]]
) -> list[dict[str, Any]]:
    now = _now()
    ids = [p.id for p, _, _ in rows]
    used = _ai_fulltext_by_project(session, ids)
    articles = _articles_by_project(session, ids)
    return [
        {
            "id": project.id,
            "name": project.name,
            "owner_id": project.owner_id,
            "owner_email": owner.email if owner else None,
            "owner_name": owner.name if owner else None,
            "created_at": project.created_at,
            "article_count": articles.get(project.id, 0),
            "ai_fulltext_used": used.get(project.id, 0),
            "plan": _plan_summary(plan, now),
            "state": _state(plan, now),
        }
        for project, plan, owner in rows
    ]


def list_projects(
    session: Session,
    search: Optional[str] = None,
    state: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
    owner_id: Optional[int] = None,
) -> dict[str, Any]:
    now = _now()
    conditions = []
    if search:
        pattern = _like(search)
        conditions.append(
            or_(
                func.lower(Project.name).like(pattern, escape="\\"),
                func.lower(User.email).like(pattern, escape="\\"),
            )
        )
    if owner_id is not None:
        conditions.append(Project.owner_id == owner_id)
    if state == "free":
        conditions.append(ProjectPlan.id.is_(None))
    elif state == "active":
        conditions.append(ProjectPlan.expires_at > now)
    elif state == "expiring":
        conditions.append(
            and_(
                ProjectPlan.expires_at > now,
                ProjectPlan.expires_at <= now + timedelta(days=EXPIRING_DAYS),
            )
        )
    elif state == "expired":
        conditions.append(ProjectPlan.expires_at <= now)

    def joined(stmt):
        return (
            stmt.outerjoin(ProjectPlan, ProjectPlan.project_id == Project.id)
            .outerjoin(User, User.id == Project.owner_id)
            .where(*conditions)
        )

    total = session.exec(joined(select(func.count(Project.id)))).one()
    stmt = joined(select(Project, ProjectPlan, User)).order_by(
        Project.created_at.desc(), Project.id.desc()
    )
    if page_size:
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = list(session.exec(stmt).all())
    return _page(_project_rows(session, rows), total, page, page_size)


# --- Users ---------------------------------------------------------------------


def _user_aggregates(
    session: Session, user_ids: list[int]
) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    if not user_ids:
        return {}, {}, {}
    projects = dict(
        session.exec(
            select(Project.owner_id, func.count(Project.id))
            .where(Project.owner_id.in_(user_ids))
            .group_by(Project.owner_id)
        ).all()
    )
    passes = dict(
        session.exec(
            select(Project.owner_id, func.count(ProjectPlan.id))
            .join(ProjectPlan, ProjectPlan.project_id == Project.id)
            .where(Project.owner_id.in_(user_ids), ProjectPlan.expires_at > _now())
            .group_by(Project.owner_id)
        ).all()
    )
    used = dict(
        session.exec(
            select(Project.owner_id, func.count(distinct(ScreeningDecision.article_id)))
            .join(Article, Article.id == ScreeningDecision.article_id)
            .join(Project, Project.id == Article.project_id)
            .where(
                Project.owner_id.in_(user_ids),
                ScreeningDecision.source == DecisionSource.ai_agent,
                ScreeningDecision.stage == ScreeningStage.full_text,
            )
            .group_by(Project.owner_id)
        ).all()
    )
    return projects, passes, used


def _user_row(
    user: User, aggregates: tuple[dict[int, int], dict[int, int], dict[int, int]]
) -> dict[str, Any]:
    projects, passes, used = aggregates
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "is_verified": user.is_verified,
        "created_at": user.created_at,
        "project_count": projects.get(user.id, 0),
        "active_passes": passes.get(user.id, 0),
        "ai_fulltext_used": used.get(user.id, 0),
    }


def list_users(
    session: Session, search: Optional[str] = None, page: int = 1, page_size: int = 25
) -> dict[str, Any]:
    conditions = []
    if search:
        pattern = _like(search)
        conditions.append(
            or_(
                func.lower(User.email).like(pattern, escape="\\"),
                func.lower(User.name).like(pattern, escape="\\"),
            )
        )
    total = session.exec(select(func.count(User.id)).where(*conditions)).one()
    users = list(
        session.exec(
            select(User)
            .where(*conditions)
            .order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    aggregates = _user_aggregates(session, [u.id for u in users])
    return _page([_user_row(u, aggregates) for u in users], total, page, page_size)


def get_user_detail(session: Session, user: User) -> dict[str, Any]:
    row = _user_row(user, _user_aggregates(session, [user.id]))
    row["projects"] = list_projects(session, owner_id=user.id, page_size=0)["items"]
    row["payments_total_cents"] = session.exec(
        select(
            func.coalesce(func.sum(Payment.amount_cents - Payment.refunded_cents), 0)
        ).where(Payment.user_id == user.id)
    ).one()
    return row


class SelfChangeError(ValueError):
    """Admins may not deactivate or demote their own account."""


def update_user(
    session: Session,
    admin: User,
    user: User,
    is_active: Optional[bool],
    is_superuser: Optional[bool],
) -> User:
    if user.id == admin.id and (is_active is False or is_superuser is False):
        raise SelfChangeError("You cannot deactivate or demote your own account")
    if is_active is not None:
        user.is_active = is_active
    if is_superuser is not None:
        user.is_superuser = is_superuser
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# --- Payments ----------------------------------------------------------------------


def dashboard_url(payment_intent: Optional[str]) -> Optional[str]:
    """Link to the payment in the Stripe dashboard (test or live by API key)."""
    if not payment_intent:
        return None
    key = get_settings().stripe_secret_key or ""
    mode = "test/" if key.startswith(("sk_test", "rk_test")) else ""
    return f"https://dashboard.stripe.com/{mode}payments/{payment_intent}"


def list_payments(
    session: Session,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    conditions = [Payment.status == status] if status else []
    total = session.exec(select(func.count(Payment.id)).where(*conditions)).one()
    rows = session.exec(
        select(Payment, User.email)
        .outerjoin(User, User.id == Payment.user_id)
        .where(*conditions)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {
            **payment.model_dump(exclude={"plan_before", "stripe_checkout_session_id"}),
            "user_email": email,
            "dashboard_url": dashboard_url(payment.stripe_payment_intent),
        }
        for payment, email in rows
    ]
    return _page(items, total, page, page_size)


# --- Overview --------------------------------------------------------------------


def overview(session: Session) -> dict[str, Any]:
    now = _now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    net = func.coalesce(func.sum(Payment.amount_cents - Payment.refunded_cents), 0)

    def ai_count(stage: ScreeningStage) -> int:
        return session.exec(
            select(func.count(ScreeningDecision.id)).where(
                ScreeningDecision.source == DecisionSource.ai_agent,
                ScreeningDecision.stage == stage,
                ScreeningDecision.created_at >= month_start,
            )
        ).one()

    ai_month = ai_usage.month_totals(session, month_start)

    return {
        "users_total": session.exec(select(func.count(User.id))).one(),
        "users_new_30d": session.exec(
            select(func.count(User.id)).where(
                User.created_at >= now - timedelta(days=30)
            )
        ).one(),
        "projects_total": session.exec(select(func.count(Project.id))).one(),
        "active_passes": session.exec(
            select(func.count(ProjectPlan.id)).where(ProjectPlan.expires_at > now)
        ).one(),
        "expiring_30d": session.exec(
            select(func.count(ProjectPlan.id)).where(
                ProjectPlan.expires_at > now,
                ProjectPlan.expires_at <= now + timedelta(days=EXPIRING_DAYS),
            )
        ).one(),
        "revenue_month_cents": session.exec(
            select(net).where(Payment.created_at >= month_start)
        ).one(),
        "revenue_total_cents": session.exec(select(net)).one(),
        "payments_month": session.exec(
            select(func.count(Payment.id)).where(Payment.created_at >= month_start)
        ).one(),
        "ai_fulltext_month": ai_count(ScreeningStage.full_text),
        "ai_title_abstract_month": ai_count(ScreeningStage.title_abstract),
        "ai_tokens_month": ai_month["total_tokens"],
        "ai_cost_month_usd": ai_month["cost_usd"],
        "currency": plans.CURRENCY,
    }
