"""Tests for the admin API, payment records and refunds, and the make-admin command."""

import json
import time
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from app import cli
from app.core.config import Settings
from app.features.audit.models import AuditEvent
from app.features.billing import services as billing
from app.features.billing import stripe_client
from app.features.billing.models import Payment, PlanSource, ProjectPlan
from app.features.research.models import Article, ArticleStatus
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
)

ADMIN = "api/v1/admin"
WEBHOOK_SECRET = "whsec_test"


@pytest.fixture(autouse=True)
def billing_on(monkeypatch):
    settings = Settings(
        _env_file=None,
        secret_key="x",
        billing_enabled=True,
        stripe_secret_key="sk_test_123",
        stripe_webhook_secret=WEBHOOK_SECRET,
    )
    for target in (
        "app.features.billing.services.get_settings",
        "app.features.billing.routers.get_settings",
        "app.features.admin.services.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings)


@pytest.fixture
def as_admin(auth_as, a_user, session):
    """Log in as a new superuser; returns (client, admin)."""
    admin = a_user()
    admin.is_superuser = True
    session.add(admin)
    session.commit()
    return auth_as(admin)


def _plan(session, project, days=200, limit=250, tier="pass_250"):
    now = datetime.now(timezone.utc)
    plan = ProjectPlan(
        project_id=project.id,
        tier=tier,
        fulltext_limit=limit,
        activated_at=now - timedelta(days=10),
        expires_at=now + timedelta(days=days),
        source=PlanSource.admin,
    )
    session.add(plan)
    session.commit()
    return plan


def _ai_screened(session, project, n):
    for i in range(n):
        article = Article(
            project_id=project.id,
            title=f"A{i}",
            status=ArticleStatus.full_text_retrieved,
            current_stage=ScreeningStage.full_text,
        )
        session.add(article)
        session.flush()
        session.add(
            ScreeningDecision(
                article_id=article.id,
                stage=ScreeningStage.full_text,
                decision=ScreeningDecisionType.include,
                source=DecisionSource.ai_agent,
            )
        )
    session.commit()


def _webhook(client, event):
    payload = json.dumps(event).encode()
    header = stripe_client.sign_payload(payload, WEBHOOK_SECRET, int(time.time()))
    res = client.post(
        "api/v1/billing/webhook",
        content=payload,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )
    assert res.status_code == 200
    return res.json()["outcome"]


def _paid(project, n=1, tier="pass_250", kind="new", amount=4900):
    return {
        "id": f"evt_paid_{n}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_{n}",
                "payment_intent": f"pi_{n}",
                "payment_status": "paid",
                "amount_total": amount,
                "currency": "eur",
                "metadata": {
                    "project_id": str(project.id),
                    "tier": tier,
                    "kind": kind,
                    "user_id": str(project.owner_id),
                },
            }
        },
    }


def _refund(n=1, amount_refunded=4900, event=None):
    return {
        "id": event or f"evt_refund_{n}_{amount_refunded}",
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": f"ch_{n}",
                "payment_intent": f"pi_{n}",
                "amount_refunded": amount_refunded,
            }
        },
    }


# --- Access ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/overview"),
        ("get", "/users"),
        ("get", "/users/1"),
        ("patch", "/users/1"),
        ("get", "/projects"),
        ("post", "/projects/1/plan"),
        ("patch", "/projects/1/plan"),
        ("get", "/payments"),
    ],
)
def test_admin_endpoints_are_superuser_only(auth_as, client, method, path):
    assert getattr(client, method)(f"{ADMIN}{path}").status_code == 401
    client, _ = auth_as()
    kwargs = {"json": {}} if method != "get" else {}
    assert getattr(client, method)(f"{ADMIN}{path}", **kwargs).status_code == 403


# --- Users -------------------------------------------------------------------------


def test_list_users_with_aggregates_and_search(as_admin, a_user, a_project, session):
    client, _ = as_admin
    owner = a_user()
    paid, _free = a_project(owner), a_project(owner)
    _plan(session, paid)
    _ai_screened(session, paid, 3)

    res = client.get(f"{ADMIN}/users", params={"search": owner.email[:12]})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    [row] = body["items"]
    assert (row["id"], row["project_count"], row["active_passes"]) == (owner.id, 2, 1)
    assert row["ai_fulltext_used"] == 3


def test_users_are_paginated(as_admin, a_user):
    client, _ = as_admin
    for _ in range(3):
        a_user()
    body = client.get(f"{ADMIN}/users", params={"page_size": 2}).json()
    assert len(body["items"]) == 2 and body["total"] >= 4
    page2 = client.get(f"{ADMIN}/users", params={"page_size": 2, "page": 2}).json()
    assert {u["id"] for u in page2["items"]}.isdisjoint(
        {u["id"] for u in body["items"]}
    )


def test_user_detail_lists_projects_and_payments(
    as_admin, a_user, a_project, session, client
):
    admin_client, _ = as_admin
    owner = a_user()
    project = a_project(owner)
    _webhook(client, _paid(project))
    body = admin_client.get(f"{ADMIN}/users/{owner.id}").json()
    assert [p["id"] for p in body["projects"]] == [project.id]
    assert body["projects"][0]["state"] == "active"
    assert body["payments_total_cents"] == 4900
    assert admin_client.get(f"{ADMIN}/users/999999").status_code == 404


def test_deactivated_user_is_locked_out(as_admin, a_user, token_for, client):
    admin_client, _ = as_admin
    user = a_user()
    res = admin_client.patch(f"{ADMIN}/users/{user.id}", json={"is_active": False})
    assert res.status_code == 200 and res.json()["is_active"] is False

    client.headers["Authorization"] = f"Bearer {token_for(user)}"
    assert client.get("api/v1/users/me").status_code == 401


def test_admin_rights_can_be_granted(as_admin, a_user, token_for, client):
    admin_client, _ = as_admin
    user = a_user()
    res = admin_client.patch(f"{ADMIN}/users/{user.id}", json={"is_superuser": True})
    assert res.json()["is_superuser"] is True
    client.headers["Authorization"] = f"Bearer {token_for(user)}"
    assert client.get(f"{ADMIN}/overview").status_code == 200


def test_admins_cannot_lock_themselves_out(as_admin):
    client, admin = as_admin
    for change in ({"is_active": False}, {"is_superuser": False}):
        res = client.patch(f"{ADMIN}/users/{admin.id}", json=change)
        assert res.status_code == 400


# --- Projects and plans ------------------------------------------------------------


def test_projects_filtered_by_plan_state(as_admin, a_user, a_project, session):
    client, _ = as_admin
    owner = a_user()
    free = a_project(owner)
    active = a_project(owner)
    expiring = a_project(owner)
    expired = a_project(owner)
    _plan(session, active, days=200)
    _plan(session, expiring, days=10)
    _plan(session, expired, days=-1)
    mine = {free.id, active.id, expiring.id, expired.id}

    def ids(state=None):
        params = {"search": owner.email, "page_size": 100}
        if state:
            params["state"] = state
        body = client.get(f"{ADMIN}/projects", params=params).json()
        return {p["id"]: p["state"] for p in body["items"] if p["id"] in mine}

    assert ids() == {
        free.id: "free",
        active.id: "active",
        expiring.id: "expiring",
        expired.id: "expired",
    }
    assert set(ids("free")) == {free.id}
    assert set(ids("active")) == {active.id, expiring.id}
    assert set(ids("expiring")) == {expiring.id}
    assert set(ids("expired")) == {expired.id}
    assert client.get(f"{ADMIN}/projects", params={"state": "nope"}).status_code == 422


def test_project_rows_show_usage_and_owner(as_admin, a_user, a_project, session):
    client, _ = as_admin
    owner = a_user()
    project = a_project(owner)
    _ai_screened(session, project, 4)
    body = client.get(f"{ADMIN}/projects", params={"search": project.name}).json()
    row = next(p for p in body["items"] if p["id"] == project.id)
    assert (row["owner_email"], row["article_count"], row["ai_fulltext_used"]) == (
        owner.email,
        4,
        4,
    )
    assert row["plan"] is None


def test_grant_pass(as_admin, a_project, session):
    client, admin = as_admin
    project = a_project()
    res = client.post(
        f"{ADMIN}/projects/{project.id}/plan",
        json={"tier": "custom", "fulltext_limit": 3000, "days": 90},
    )
    assert res.status_code == 200
    plan = billing.get_plan(session, project.id)
    assert (plan.tier, plan.fulltext_limit, plan.granted_by) == (
        "custom",
        3000,
        admin.id,
    )
    assert billing.is_active(plan)
    bad = client.post(f"{ADMIN}/projects/{project.id}/plan", json={"tier": "custom"})
    assert bad.status_code == 400
    missing = client.post(f"{ADMIN}/projects/999999/plan", json={"tier": "pass_250"})
    assert missing.status_code == 404


def test_extend_and_change_limit(as_admin, a_project, session):
    client, admin = as_admin
    project = a_project()
    plan = _plan(session, project, days=10)
    new_end = datetime.now(timezone.utc) + timedelta(days=400)
    res = client.patch(
        f"{ADMIN}/projects/{project.id}/plan",
        json={"fulltext_limit": 600, "expires_at": new_end.isoformat()},
    )
    assert res.status_code == 200
    session.refresh(plan)
    assert plan.fulltext_limit == 600
    assert abs(billing._aware(plan.expires_at) - new_end) < timedelta(seconds=1)
    event = session.exec(
        select(AuditEvent).where(
            AuditEvent.project_id == project.id,
            AuditEvent.action == billing.PASS_CHANGED,
        )
    ).one()
    assert event.user_id == admin.id
    assert event.details["before"]["fulltext_limit"] == 250
    assert event.details["after"]["fulltext_limit"] == 600


def test_end_pass_early_makes_project_read_only(as_admin, a_project, session):
    client, _ = as_admin
    project = a_project()
    _plan(session, project)
    now = datetime.now(timezone.utc).isoformat()
    res = client.patch(f"{ADMIN}/projects/{project.id}/plan", json={"expires_at": now})
    assert res.status_code == 200
    assert billing.is_read_only(session, project)


def test_change_needs_an_existing_pass(as_admin, a_project):
    client, _ = as_admin
    project = a_project()
    res = client.patch(
        f"{ADMIN}/projects/{project.id}/plan", json={"fulltext_limit": 5}
    )
    assert res.status_code == 404


# --- Payments and refunds -------------------------------------------------------------


def test_payment_is_recorded_and_listed(as_admin, a_user, a_project, session, client):
    project = a_project(a_user())
    assert _webhook(client, _paid(project)) == billing.PASS_ACTIVATED
    admin_client, _ = as_admin
    body = admin_client.get(f"{ADMIN}/payments").json()
    row = next(p for p in body["items"] if p["project_id"] == project.id)
    assert (row["amount_cents"], row["status"], row["kind"]) == (4900, "paid", "new")
    assert row["user_email"] == project.owner.email
    assert row["dashboard_url"] == "https://dashboard.stripe.com/test/payments/pi_1"
    assert "plan_before" not in row
    paid_only = admin_client.get(f"{ADMIN}/payments", params={"status": "refunded"})
    assert all(p["status"] == "refunded" for p in paid_only.json()["items"])


def test_same_checkout_is_applied_once(client, a_user, a_project, session):
    project = a_project(a_user())
    _webhook(client, _paid(project))
    expires = billing.get_plan(session, project.id).expires_at
    second = _paid(project)
    second["id"] = "evt_other"
    second["type"] = "checkout.session.async_payment_succeeded"
    assert _webhook(client, second) == "duplicate"
    session.expire_all()
    assert billing.get_plan(session, project.id).expires_at == expires


def test_full_refund_of_a_new_pass_returns_project_to_free(
    client, a_user, a_project, session
):
    project = a_project(a_user())
    _webhook(client, _paid(project))
    assert _webhook(client, _refund()) == billing.PASS_REFUNDED
    session.expire_all()
    assert billing.get_plan(session, project.id) is None
    payment = session.exec(
        select(Payment).where(Payment.project_id == project.id)
    ).one()
    assert (payment.status, payment.refunded_cents) == ("refunded", 4900)


def test_full_refund_of_an_upgrade_restores_previous_tier(
    client, a_user, a_project, session
):
    project = a_project(a_user())
    _webhook(client, _paid(project))
    expires = billing.get_plan(session, project.id).expires_at
    _webhook(client, _paid(project, n=2, tier="pass_1000", kind="upgrade", amount=8000))
    assert billing.get_plan(session, project.id).fulltext_limit == 1000

    assert _webhook(client, _refund(n=2, amount_refunded=8000)) == billing.PASS_REFUNDED
    session.expire_all()
    plan = billing.get_plan(session, project.id)
    assert (plan.tier, plan.fulltext_limit) == ("pass_250", 250)
    assert billing._aware(plan.expires_at) == billing._aware(expires)


def test_partial_refund_leaves_the_pass(client, a_user, a_project, session):
    project = a_project(a_user())
    _webhook(client, _paid(project))
    assert _webhook(client, _refund(amount_refunded=1000)) == billing.PAYMENT_REFUNDED
    session.expire_all()
    assert billing.is_active(billing.get_plan(session, project.id))
    payment = session.exec(
        select(Payment).where(Payment.project_id == project.id)
    ).one()
    assert payment.status == "partially_refunded"


def test_refund_of_an_older_payment_leaves_the_pass(client, a_user, a_project, session):
    project = a_project(a_user())
    _webhook(client, _paid(project))
    _webhook(client, _paid(project, n=2, tier="pass_1000", kind="upgrade", amount=8000))
    assert _webhook(client, _refund(n=1)) == billing.PAYMENT_REFUNDED
    session.expire_all()
    assert billing.get_plan(session, project.id).fulltext_limit == 1000
    event = session.exec(
        select(AuditEvent).where(AuditEvent.action == billing.PAYMENT_REFUNDED)
    ).one()
    assert event.details["plan_unchanged"] is True


def test_refund_of_unknown_payment_is_ignored(client):
    assert _webhook(client, _refund(n=99)) == "ignored"


def test_payments_survive_project_deletion(auth_as, a_user, a_project, session, client):
    owner = a_user()
    project = a_project(owner)
    _webhook(client, _paid(project))
    owner_client, _ = auth_as(owner)
    assert owner_client.delete(f"api/v1/projects/{project.id}").status_code == 204
    payment = session.exec(
        select(Payment).where(Payment.stripe_payment_intent == "pi_1")
    ).one()
    assert payment.project_id is None and payment.project_name == project.name


# --- Overview ----------------------------------------------------------------------------


def test_overview_counts(as_admin, a_user, a_project, session, client):
    admin_client, _ = as_admin
    before = admin_client.get(f"{ADMIN}/overview").json()
    owner = a_user()
    paid, expiring = a_project(owner), a_project(owner)
    _webhook(client, _paid(paid))
    _webhook(client, _refund(amount_refunded=900))
    _plan(session, expiring, days=5)
    _ai_screened(session, paid, 2)

    after = admin_client.get(f"{ADMIN}/overview").json()
    assert after["users_total"] - before["users_total"] == 1
    assert after["projects_total"] - before["projects_total"] == 2
    assert after["active_passes"] - before["active_passes"] == 2
    assert after["expiring_30d"] - before["expiring_30d"] == 1
    assert after["revenue_month_cents"] - before["revenue_month_cents"] == 4000
    assert after["revenue_total_cents"] - before["revenue_total_cents"] == 4000
    assert after["payments_month"] - before["payments_month"] == 1
    assert after["ai_fulltext_month"] - before["ai_fulltext_month"] == 2
    assert after["currency"] == "eur"


# --- make-admin command ---------------------------------------------------------------------


def test_make_admin_grants_and_revokes(a_user, session):
    user = a_user()
    assert cli.make_admin(session, user.email) == f"{user.email} is now an admin"
    session.refresh(user)
    assert user.is_superuser
    cli.make_admin(session, user.email, revoke=True)
    session.refresh(user)
    assert not user.is_superuser


def test_make_admin_command(a_user, session, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Session", lambda _engine: nullcontext(session))
    user = a_user()
    assert cli.main(["make-admin", user.email]) == 0
    assert "now an admin" in capsys.readouterr().out
    assert cli.main(["make-admin", "nobody@example.com"]) == 1
    assert "No account" in capsys.readouterr().err
