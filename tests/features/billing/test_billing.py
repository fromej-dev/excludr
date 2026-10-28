"""Tests for review passes: allowances, read-only projects, Stripe Checkout and webhooks.

Stripe is never called: the HTTP client is swapped for an ``httpx.MockTransport``.
"""

import json
import time
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from urllib.parse import parse_qsl

import httpx
import pytest
from sqlmodel import select

from app.core.config import Settings
from app.features.audit.models import AuditEvent
from app.features.billing import services as billing
from app.features.billing import stripe_client
from app.features.billing.models import PlanSource, ProjectPlan, StripeEvent
from app.features.criteria.models import Criterion, CriterionType
from app.features.research.models import Article, ArticleStatus
from app.features.screening import flows
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
)

BASE = "api/v1/projects"
WEBHOOK_SECRET = "whsec_test"


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "secret_key": "x",
        "billing_enabled": True,
        "stripe_secret_key": "sk_test_123",
        "stripe_webhook_secret": WEBHOOK_SECRET,
        "public_app_url": "https://app.test",
        "anthropic_api_key": "k",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(autouse=True)
def billing_on(monkeypatch):
    """Enable billing and AI (never starting the real flow) for every test here."""
    settings = _settings()
    for target in (
        "app.features.billing.services.get_settings",
        "app.features.billing.routers.get_settings",
        "app.features.research.agent.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings)
    flow_mock = AsyncMock()
    monkeypatch.setattr(
        "app.features.screening.routers.batch_ai_screening_flow", flow_mock
    )
    return flow_mock


@pytest.fixture
def stripe_api(monkeypatch):
    """Fake Stripe API; records requests and answers Checkout Session creation."""
    calls: list[httpx.Request] = []
    state = {"status": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.path == "/v1/checkout/sessions"
        if state["status"] != 200:
            return httpx.Response(
                state["status"], json={"error": {"message": "Invalid API key"}}
            )
        return httpx.Response(
            200, json={"id": "cs_test_1", "url": "https://checkout.stripe.test/cs_1"}
        )

    monkeypatch.setattr(
        stripe_client,
        "get_http_client",
        lambda: httpx.AsyncClient(
            base_url=stripe_client.STRIPE_API_URL,
            transport=httpx.MockTransport(handler),
        ),
    )
    return calls, state


def _form(request: httpx.Request) -> dict[str, str]:
    return dict(parse_qsl(request.content.decode()))


def _criterion(session, project):
    session.add(
        Criterion(
            project_id=project.id,
            type=CriterionType.inclusion,
            code="I1",
            description="d",
            is_active=True,
        )
    )
    session.commit()


def _full_text_articles(session, project, n, ai_screened=False):
    """Create ``n`` full-text-ready articles, optionally with an AI decision each."""
    articles = []
    for i in range(n):
        article = Article(
            project_id=project.id,
            title=f"Article {i}",
            status=ArticleStatus.full_text_retrieved,
            current_stage=ScreeningStage.full_text,
            full_text_content="full text",
        )
        session.add(article)
        articles.append(article)
    session.commit()
    if ai_screened:
        for article in articles:
            _ai_decision(session, article, ScreeningStage.full_text)
        session.commit()
    return articles


def _ai_decision(session, article, stage):
    session.add(
        ScreeningDecision(
            article_id=article.id,
            stage=stage,
            decision=ScreeningDecisionType.include,
            source=DecisionSource.ai_agent,
        )
    )


def _give_plan(session, project, limit=250, expires_in_days=30, tier="pass_250"):
    now = datetime.now(timezone.utc)
    plan = ProjectPlan(
        project_id=project.id,
        tier=tier,
        fulltext_limit=limit,
        activated_at=now - timedelta(days=10),
        expires_at=now + timedelta(days=expires_in_days),
        source=PlanSource.admin,
    )
    session.add(plan)
    session.commit()
    return plan


def _webhook(client, event, secret=WEBHOOK_SECRET, timestamp=None):
    payload = json.dumps(event).encode()
    header = stripe_client.sign_payload(payload, secret, timestamp or int(time.time()))
    return client.post(
        "api/v1/billing/webhook",
        content=payload,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )


def _paid_event(project, tier="pass_250", kind="new", event_id="evt_1", **extra):
    checkout = {
        "id": "cs_test_1",
        "payment_status": "paid",
        "amount_total": 4900,
        "metadata": {
            "project_id": str(project.id),
            "tier": tier,
            "kind": kind,
            "user_id": str(project.owner_id),
        },
    }
    checkout.update(extra)
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {"object": checkout},
    }


# --- Plans and status ----------------------------------------------------------


def test_public_plans_lists_tiers(client):
    res = client.get("api/v1/billing/plans")
    assert res.status_code == 200
    body = res.json()
    assert body["billing_enabled"] is True
    assert body["free"]["fulltext_limit"] == 50
    assert [(t["tier"], t["price_cents"]) for t in body["tiers"]] == [
        ("pass_250", 4900),
        ("pass_1000", 12900),
    ]


def test_status_of_free_project(auth_as, a_project):
    client, user = auth_as()
    project = a_project(user)
    body = client.get(f"{BASE}/{project.id}/billing").json()
    assert body["plan"] == "free" and body["active"] is False
    assert body["read_only"] is False
    assert body["full_text"] == {"used": 0, "limit": 50, "scope": "account"}
    assert body["dual_screening_allowed"] is False
    assert [(o["tier"], o["amount_cents"], o["kind"]) for o in body["options"]] == [
        ("pass_250", 4900, "new"),
        ("pass_1000", 12900, "new"),
    ]


def test_status_when_billing_disabled(auth_as, a_project, monkeypatch):
    monkeypatch.setattr(
        "app.features.billing.services.get_settings",
        lambda: _settings(billing_enabled=False),
    )
    client, user = auth_as()
    project = a_project(user)
    body = client.get(f"{BASE}/{project.id}/billing").json()
    assert body["billing_enabled"] is False
    assert body["dual_screening_allowed"] is True and body["options"] == []
    assert body["online_payment"] is False


def test_status_offers_online_payment_with_stripe_key(auth_as, a_project):
    client, user = auth_as()
    project = a_project(user)
    assert client.get(f"{BASE}/{project.id}/billing").json()["online_payment"] is True


def test_limits_apply_without_stripe(auth_as, a_project, session, monkeypatch):
    """Billing on, Stripe not set up: limits hold, passes come from admins."""
    monkeypatch.setattr(
        "app.features.billing.services.get_settings",
        lambda: _settings(stripe_secret_key=None, stripe_webhook_secret=None),
    )
    client, user = auth_as()
    used, project = a_project(user), a_project(user)
    _full_text_articles(session, used, 50, ai_screened=True)
    _criterion(session, project)
    _full_text_articles(session, project, 1)

    status = client.get(f"{BASE}/{project.id}/billing").json()
    assert status["online_payment"] is False
    assert status["options"]  # prices are still shown, to ask an admin for
    assert client.post(f"{BASE}/{project.id}/screening/run-ai").status_code == 402
    res = client.patch(f"{BASE}/{project.id}", json={"required_reviewers": 2})
    assert res.status_code == 402

    _give_plan(session, project)
    assert client.post(f"{BASE}/{project.id}/screening/run-ai").status_code == 200


def test_status_needs_membership(auth_as, a_project):
    project = a_project()
    client, _ = auth_as()
    assert client.get(f"{BASE}/{project.id}/billing").status_code == 403


# --- Allowances ----------------------------------------------------------------


def test_free_allowance_is_shared_across_unpaid_projects(auth_as, a_project, session):
    client, user = auth_as()
    first, second = a_project(user), a_project(user)
    _full_text_articles(session, first, 50, ai_screened=True)
    _criterion(session, second)
    [article] = _full_text_articles(session, second, 1)

    status = client.get(f"{BASE}/{second.id}/billing").json()
    assert status["full_text"]["used"] == 50

    res = client.post(f"{BASE}/{second.id}/screening/articles/{article.id}/screen-ai")
    assert res.status_code == 402
    assert "free AI allowance" in res.json()["detail"]


def test_rescreening_does_not_use_allowance(a_user, a_project, session):
    project = a_project(a_user())
    articles = _full_text_articles(session, project, 50, ai_screened=True)
    billing.check_can_ai_screen(session, project, articles[0])  # no error


def test_title_abstract_screening_does_not_count_as_full_text(
    a_user, a_project, session
):
    project = a_project(a_user())
    article = Article(project_id=project.id, title="t", status=ArticleStatus.screening)
    session.add(article)
    session.commit()
    _ai_decision(session, article, ScreeningStage.title_abstract)
    session.commit()
    full = billing.get_allowance(session, project, ScreeningStage.full_text)
    abstract = billing.get_allowance(session, project, ScreeningStage.title_abstract)
    assert (full.used, abstract.used) == (0, 1)


def test_paid_project_has_own_allowance_and_frees_the_account_pool(
    a_user, a_project, session
):
    user = a_user()
    paid, free = a_project(user), a_project(user)
    _full_text_articles(session, paid, 40, ai_screened=True)
    _give_plan(session, paid, limit=250)
    assert billing.get_allowance(session, paid, ScreeningStage.full_text) == (
        billing.Allowance(ScreeningStage.full_text, 40, 250, "project")
    )
    pool = billing.get_allowance(session, free, ScreeningStage.full_text)
    assert (pool.used, pool.scope) == (0, "account")


def test_free_allowance_is_per_owner(a_user, a_project, session):
    other = a_project(a_user())
    _full_text_articles(session, other, 50, ai_screened=True)
    mine = a_project(a_user())
    assert billing.get_allowance(session, mine, ScreeningStage.full_text).used == 0


def test_batch_queues_only_what_the_allowance_covers(
    auth_as, a_project, session, billing_on
):
    client, user = auth_as()
    used, project = a_project(user), a_project(user)
    _full_text_articles(session, used, 48, ai_screened=True)
    _criterion(session, project)
    articles = _full_text_articles(session, project, 5)

    res = client.post(f"{BASE}/{project.id}/screening/run-ai")
    assert res.status_code == 200
    assert res.json()["article_count"] == 2
    assert res.json()["skipped_over_allowance"] == 3
    queued = billing_on.call_args.args[1]
    assert queued == [articles[0].id, articles[1].id]


def test_batch_refused_when_allowance_used_up(auth_as, a_project, session):
    client, user = auth_as()
    used, project = a_project(user), a_project(user)
    _full_text_articles(session, used, 50, ai_screened=True)
    _criterion(session, project)
    _full_text_articles(session, project, 2)
    res = client.post(f"{BASE}/{project.id}/screening/run-ai")
    assert res.status_code == 402


def test_batch_rescreens_stale_articles_beyond_the_allowance(
    a_user, a_project, session
):
    project = a_project(a_user())
    screened = _full_text_articles(session, project, 50, ai_screened=True)
    new = _full_text_articles(session, project, 1)
    ids = [screened[0].id, new[0].id]
    kept, skipped = billing.split_by_allowance(session, project, ids)
    assert (kept, skipped) == ([screened[0].id], 1)


@pytest.mark.asyncio
async def test_flow_skips_articles_once_allowance_is_used(
    a_user, a_project, session, monkeypatch
):
    monkeypatch.setattr(flows, "Session", lambda _engine: nullcontext(session))
    monkeypatch.setattr(flows.NotificationService, "notify_room", AsyncMock())
    monkeypatch.setattr(flows.NotificationService, "notify_user_in_room", AsyncMock())
    user = a_user()
    used, project = a_project(user), a_project(user)
    _full_text_articles(session, used, 49, ai_screened=True)
    _criterion(session, project)
    articles = _full_text_articles(session, project, 3)

    async def fake_screen(article, criteria, review_question, session, reviewer_id):
        decision = ScreeningDecision(
            article_id=article.id,
            stage=ScreeningStage.full_text,
            decision=ScreeningDecisionType.include,
            source=DecisionSource.ai_agent,
        )
        session.add(decision)
        session.commit()
        return decision

    monkeypatch.setattr(flows, "screen_article", fake_screen)
    result = await flows.batch_ai_screening_flow(
        project.id, [a.id for a in articles], user.id
    )
    assert result == {"total": 3, "screened": 1, "errors": 0, "skipped": 2}


# --- Dual screening and read-only projects --------------------------------------


def test_dual_screening_needs_a_pass(auth_as, a_project, session):
    client, user = auth_as()
    project = a_project(user)
    res = client.patch(f"{BASE}/{project.id}", json={"required_reviewers": 2})
    assert res.status_code == 402

    _give_plan(session, project)
    res = client.patch(f"{BASE}/{project.id}", json={"required_reviewers": 2})
    assert res.status_code == 200


def test_expired_pass_makes_project_read_only(auth_as, a_project, session):
    client, user = auth_as()
    project = a_project(user)
    _give_plan(session, project, expires_in_days=-1)

    res = client.post(
        f"{BASE}/{project.id}/criteria",
        json={"type": "inclusion", "code": "I1", "description": "d"},
    )
    assert res.status_code == 402
    assert "read-only" in res.json()["detail"]
    assert client.get(f"{BASE}/{project.id}").status_code == 200
    assert client.get(f"{BASE}/{project.id}/criteria").status_code == 200

    status = client.get(f"{BASE}/{project.id}/billing").json()
    assert status["read_only"] is True
    assert {o["kind"] for o in status["options"]} == {"renewal"}

    assert client.delete(f"{BASE}/{project.id}").status_code == 204


def test_active_pass_allows_writes(auth_as, a_project, session):
    client, user = auth_as()
    project = a_project(user)
    _give_plan(session, project)
    res = client.post(
        f"{BASE}/{project.id}/criteria",
        json={"type": "inclusion", "code": "I1", "description": "d"},
    )
    assert res.status_code == 201


# --- Checkout ----------------------------------------------------------------------


def test_checkout_creates_stripe_session(auth_as, a_project, stripe_api):
    calls, _ = stripe_api
    client, user = auth_as()
    project = a_project(user)

    res = client.post(
        f"{BASE}/{project.id}/billing/checkout", json={"tier": "pass_1000"}
    )
    assert res.status_code == 200
    assert res.json() == {"url": "https://checkout.stripe.test/cs_1"}

    [request] = calls
    assert request.headers["Authorization"] == "Bearer sk_test_123"
    form = _form(request)
    assert form["mode"] == "payment"
    assert form["line_items[0][price_data][unit_amount]"] == "12900"
    assert form["line_items[0][price_data][currency]"] == "eur"
    assert form["metadata[project_id]"] == str(project.id)
    assert form["metadata[tier]"] == "pass_1000"
    assert form["metadata[kind]"] == "new"
    assert form["customer_email"] == user.email
    assert form["invoice_creation[enabled]"] == "true"
    assert "automatic_tax[enabled]" not in form
    assert form["success_url"] == (
        f"https://app.test/projects/{project.id}?billing=success"
    )


def test_upgrade_charges_the_difference(auth_as, a_project, session, stripe_api):
    calls, _ = stripe_api
    client, user = auth_as()
    project = a_project(user)
    _give_plan(session, project)

    status = client.get(f"{BASE}/{project.id}/billing").json()
    assert [(o["tier"], o["amount_cents"]) for o in status["options"]] == [
        ("pass_1000", 8000)
    ]
    res = client.post(
        f"{BASE}/{project.id}/billing/checkout", json={"tier": "pass_1000"}
    )
    assert res.status_code == 200
    form = _form(calls[0])
    assert form["line_items[0][price_data][unit_amount]"] == "8000"
    assert form["metadata[kind]"] == "upgrade"


def test_checkout_rejects_tiers_not_on_offer(auth_as, a_project, session, stripe_api):
    client, user = auth_as()
    project = a_project(user)
    _give_plan(session, project, limit=1000, tier="pass_1000")
    for tier in ("pass_250", "pass_1000", "nope"):
        res = client.post(f"{BASE}/{project.id}/billing/checkout", json={"tier": tier})
        assert res.status_code == 400
    assert stripe_api[0] == []


def test_checkout_is_owner_only(auth_as, a_project, a_member, stripe_api):
    project = a_project()
    reviewer = a_member(project)
    client, _ = auth_as(reviewer)
    res = client.post(
        f"{BASE}/{project.id}/billing/checkout", json={"tier": "pass_250"}
    )
    assert res.status_code == 403


def test_checkout_reports_stripe_errors(auth_as, a_project, stripe_api):
    stripe_api[1]["status"] = 401
    client, user = auth_as()
    project = a_project(user)
    res = client.post(
        f"{BASE}/{project.id}/billing/checkout", json={"tier": "pass_250"}
    )
    assert res.status_code == 502


def test_checkout_unavailable_when_billing_disabled(
    auth_as, a_project, monkeypatch, stripe_api
):
    monkeypatch.setattr(
        "app.features.billing.services.get_settings",
        lambda: _settings(billing_enabled=False),
    )
    client, user = auth_as()
    project = a_project(user)
    res = client.post(
        f"{BASE}/{project.id}/billing/checkout", json={"tier": "pass_250"}
    )
    assert res.status_code == 404


def test_checkout_unavailable_without_stripe_key(auth_as, a_project, monkeypatch):
    monkeypatch.setattr(
        "app.features.billing.routers.get_settings",
        lambda: _settings(stripe_secret_key=None),
    )
    client, user = auth_as()
    project = a_project(user)
    res = client.post(
        f"{BASE}/{project.id}/billing/checkout", json={"tier": "pass_250"}
    )
    assert res.status_code == 503


# --- Webhooks ------------------------------------------------------------------------


def test_webhook_activates_a_pass(client, a_user, a_project, session):
    project = a_project(a_user())
    res = _webhook(client, _paid_event(project))
    assert res.status_code == 200
    assert res.json()["outcome"] == billing.PASS_ACTIVATED

    plan = billing.get_plan(session, project.id)
    assert (plan.tier, plan.fulltext_limit, plan.source) == (
        "pass_250",
        250,
        PlanSource.stripe,
    )
    assert plan.amount_paid_cents == 4900
    expires = billing._aware(plan.expires_at)
    assert (
        timedelta(days=364)
        < expires - datetime.now(timezone.utc)
        <= timedelta(days=365)
    )
    event = session.exec(
        select(AuditEvent).where(
            AuditEvent.project_id == project.id,
            AuditEvent.action == billing.PASS_ACTIVATED,
        )
    ).one()
    assert event.user_id == project.owner_id


def test_webhook_applies_each_event_once(client, a_user, a_project, session):
    project = a_project(a_user())
    _webhook(client, _paid_event(project))
    expires = billing.get_plan(session, project.id).expires_at
    res = _webhook(client, _paid_event(project))
    assert res.json()["outcome"] == "duplicate"
    session.expire_all()
    assert billing.get_plan(session, project.id).expires_at == expires
    assert session.get(StripeEvent, "evt_1") is not None


def test_webhook_ignores_unpaid_checkouts(client, a_user, a_project, session):
    project = a_project(a_user())
    res = _webhook(client, _paid_event(project, payment_status="unpaid"))
    assert res.json()["outcome"] == "ignored"
    assert billing.get_plan(session, project.id) is None


def test_webhook_activates_on_async_payment(client, a_user, a_project, session):
    project = a_project(a_user())
    event = _paid_event(project)
    event["type"] = "checkout.session.async_payment_succeeded"
    assert _webhook(client, event).json()["outcome"] == billing.PASS_ACTIVATED


def test_webhook_upgrade_keeps_expiry(client, a_user, a_project, session):
    project = a_project(a_user())
    plan = _give_plan(session, project)
    expires = plan.expires_at
    res = _webhook(client, _paid_event(project, tier="pass_1000", kind="upgrade"))
    assert res.json()["outcome"] == billing.PASS_UPGRADED
    session.refresh(plan)
    assert (plan.tier, plan.fulltext_limit) == ("pass_1000", 1000)
    assert plan.expires_at == expires


def test_webhook_renews_an_expired_pass(client, a_user, a_project, session):
    project = a_project(a_user())
    plan = _give_plan(session, project, expires_in_days=-5)
    res = _webhook(client, _paid_event(project, kind="renewal"))
    assert res.json()["outcome"] == billing.PASS_ACTIVATED
    session.refresh(plan)
    assert billing.is_active(plan)
    assert not billing.is_read_only(session, project)


def test_webhook_rejects_bad_signatures(client, a_user, a_project, session):
    project = a_project(a_user())
    assert _webhook(client, _paid_event(project), secret="wrong").status_code == 400
    stale = int(time.time()) - 3600
    assert _webhook(client, _paid_event(project), timestamp=stale).status_code == 400
    res = client.post("api/v1/billing/webhook", content=b"{}")
    assert res.status_code == 400
    assert billing.get_plan(session, project.id) is None


def test_webhook_ignores_unknown_projects(client):
    event = _paid_event(type("P", (), {"id": 999999, "owner_id": 1})())
    assert _webhook(client, event).json()["outcome"] == "ignored"


def test_verify_webhook_accepts_any_matching_v1():
    payload = b'{"id": "evt"}'
    good = stripe_client.sign_payload(payload, "s", 1000).split(",")[1]
    header = f"t=1000,v1=deadbeef,{good}"
    assert stripe_client.verify_webhook(payload, header, "s", now=1000) == {"id": "evt"}


def test_encode_form_flattens_nested_params():
    assert stripe_client.encode_form(
        {"a": {"b": [{"c": 1}], "d": True}, "e": None}
    ) == [("a[b][0][c]", "1"), ("a[d]", "true")]
