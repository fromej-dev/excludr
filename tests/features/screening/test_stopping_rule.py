"""Stopping rule: streak, status, apply, reopen and the guards on closed records."""

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from app.core.config import Settings
from app.features.ai_usage.models import AIUsage
from app.features.audit.models import AuditEvent
from app.features.billing.models import ProjectPlan
from app.features.criteria.models import Criterion, CriterionType
from app.features.projects.models import ImportBatch, ProjectRole
from app.features.research.models import Article, ArticleStatus, FinalDecision
from app.features.screening import flows, inflight, stopping
from app.features.screening.models import (
    DecisionSource,
    RankingRun,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
)

BASE = "api/v1/projects"
TA, FT = ScreeningStage.title_abstract, ScreeningStage.full_text
D = ScreeningDecisionType
HUMAN, AI = DecisionSource.human, DecisionSource.ai_agent


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _prioritize(session, project, threshold=3, since=None, reviewers=1):
    project.prioritized_screening = True
    project.stop_after_consecutive_excludes = threshold
    project.required_reviewers = reviewers
    project.prioritized_screening_enabled_at = since or _now() - timedelta(days=1)
    session.add(project)
    session.commit()


def _vote(
    session,
    article,
    user,
    decision,
    *,
    resolution=False,
    stage=TA,
    source=HUMAN,
    created_at=None,
):
    row = ScreeningDecision(
        article_id=article.id,
        reviewer_id=user.id if user else None,
        stage=stage,
        decision=decision,
        source=source,
        is_resolution=resolution,
        created_at=created_at,
    )
    session.add(row)
    session.commit()
    return row


def _close_ta(session, article, outcome):
    if outcome == D.exclude:
        article.status = ArticleStatus.excluded
        article.current_stage = ScreeningStage.completed
        article.final_decision = FinalDecision.excluded
    else:
        article.status = ArticleStatus.awaiting_full_text
        article.current_stage = FT
    session.add(article)
    session.commit()


def _ex(session, article, user, **kw):
    _vote(session, article, user, D.exclude, **kw)
    _close_ta(session, article, D.exclude)


def _inc(session, article, user, **kw):
    _vote(session, article, user, D.include, **kw)
    _close_ta(session, article, D.include)


def _agreed_ex(session, article, r1, r2):
    _vote(session, article, r1, D.exclude)
    _ex(session, article, r2)


def streak(session, project):
    return stopping.compute_streak(session, project).consecutive_excludes


@pytest.fixture
def env(auth_as, a_project, a_member, an_article_in, session):
    client, owner = auth_as()
    project = a_project(owner)

    class E:
        pass

    e = E()
    e.client, e.owner, e.project = client, owner, project
    e.session, e.article, e.member, e.auth_as = (
        session,
        an_article_in,
        a_member,
        auth_as,
    )
    e.url = f"{BASE}/{project.id}/screening"
    e.prio = lambda **kw: _prioritize(session, project, **kw)
    e.arts = lambda n, **kw: [an_article_in(project, **kw) for _ in range(n)]
    return e


def _events(session, project, action):
    session.expire_all()
    return session.exec(
        select(AuditEvent)
        .where(AuditEvent.project_id == project.id, AuditEvent.action == action)
        .order_by(AuditEvent.id)
    ).all()


# --- streak ---------------------------------------------------------------


def test_streak_zero_when_prioritization_off(env):
    (a1,) = env.arts(1)
    _ex(env.session, a1, env.owner)
    assert streak(env.session, env.project) == 0
    assert stopping.summary(env.session, env.project) is None


def test_streak_counts_excludes_since_last_include(env):
    env.prio()
    a = env.arts(6)
    for art, kind in zip(a, "EEIEEE", strict=True):
        (_ex if kind == "E" else _inc)(env.session, art, env.owner)
    assert streak(env.session, env.project) == 3


def test_streak_orders_by_settlement_not_article_id(env):
    env.prio()
    a1, a2, a3 = env.arts(3)
    _ex(env.session, a3, env.owner)
    _inc(env.session, a1, env.owner)
    _ex(env.session, a2, env.owner)
    assert streak(env.session, env.project) == 1


def test_uncertain_vote_resets(env):
    env.prio()
    a1, a2, a3, a4 = env.arts(4)
    _ex(env.session, a1, env.owner)
    _ex(env.session, a2, env.owner)
    _vote(env.session, a3, env.owner, D.uncertain)
    _ex(env.session, a4, env.owner)
    assert streak(env.session, env.project) == 1


def test_superseded_uncertain_no_longer_resets(env):
    env.prio()
    a1, a2, a3, a4 = env.arts(4)
    _ex(env.session, a1, env.owner)
    _ex(env.session, a2, env.owner)
    _vote(env.session, a3, env.owner, D.uncertain)
    _ex(env.session, a4, env.owner)
    _ex(env.session, a3, env.owner)
    assert streak(env.session, env.project) == 4


def test_uncertain_by_other_reviewer_still_resets(env):
    env.prio()
    r1, r2 = env.member(env.project), env.member(env.project)
    a1, a2 = env.arts(2)
    _ex(env.session, a1, env.owner)
    _vote(env.session, a2, r1, D.uncertain)
    _ex(env.session, a2, r2)
    assert streak(env.session, env.project) == 1


def test_dual_counts_agreed_outcomes_only(env):
    env.prio(reviewers=2)
    r1, r2 = env.member(env.project), env.member(env.project)
    a1, a2 = env.arts(2)
    _agreed_ex(env.session, a1, r1, r2)
    assert streak(env.session, env.project) == 1
    _vote(env.session, a2, r1, D.exclude)
    assert streak(env.session, env.project) == 1


def test_dual_pending_include_vote_resets(env):
    env.prio(reviewers=2)
    r1, r2 = env.member(env.project), env.member(env.project)
    a1, a2, a3 = env.arts(3)
    _agreed_ex(env.session, a1, r1, r2)
    _vote(env.session, a2, r1, D.include)
    assert streak(env.session, env.project) == 0
    _agreed_ex(env.session, a3, r1, r2)
    assert streak(env.session, env.project) == 1


def test_dual_conflict_resets_and_resolution_counts(env):
    env.prio(reviewers=2)
    r1, r2 = env.member(env.project), env.member(env.project)
    a1, a2 = env.arts(2)
    _agreed_ex(env.session, a1, r1, r2)
    _vote(env.session, a2, r1, D.include)
    _vote(env.session, a2, r2, D.exclude)
    assert streak(env.session, env.project) == 0
    _ex(env.session, a2, env.owner, resolution=True)
    assert streak(env.session, env.project) == 1


def test_dual_vote_change_settles_at_change(env):
    env.prio(reviewers=2)
    r1, r2 = env.member(env.project), env.member(env.project)
    a1, a2 = env.arts(2)
    _vote(env.session, a1, r1, D.include)
    _vote(env.session, a1, r2, D.exclude)
    _agreed_ex(env.session, a2, r1, r2)
    assert streak(env.session, env.project) == 1
    _ex(env.session, a1, r1)
    assert streak(env.session, env.project) == 2


def test_streak_ignores_ai_full_text_and_skipped(env):
    env.prio()
    session = env.session
    y, a1, p, f, s, x = env.arts(6)
    _vote(session, y, env.owner, D.include)
    _vote(session, y, env.owner, D.exclude, stage=FT)
    _close_ta(session, y, D.exclude)
    _ex(session, a1, env.owner)
    assert streak(session, env.project) == 1

    _vote(session, p, None, D.include, source=AI)
    f.status, f.current_stage = ArticleStatus.full_text_retrieved, FT
    session.add(f)
    _vote(session, f, env.owner, D.include, stage=FT)
    s.title_abstract_skipped = True
    session.add(s)
    _vote(session, s, env.owner, D.include)
    _vote(session, x, None, D.exclude, source=AI)
    _close_ta(session, x, D.exclude)
    assert streak(session, env.project) == 1


def test_streak_only_since_enabled(env):
    t = _now()
    env.prio(since=t)
    a = env.arts(5)
    old, new = t - timedelta(hours=1), t + timedelta(hours=1)
    _ex(env.session, a[0], env.owner, created_at=old)
    _ex(env.session, a[1], env.owner, created_at=old)
    _inc(env.session, a[2], env.owner, created_at=old)
    _ex(env.session, a[3], env.owner, created_at=new)
    _ex(env.session, a[4], env.owner, created_at=new)
    result = stopping.compute_streak(env.session, env.project)
    assert result.consecutive_excludes == 2
    assert result.counting_since == t


def test_streak_window_restarts_at_applied_at(env):
    t = _now()
    env.prio(since=t)
    env.project.stopping_rule_applied_at = t + timedelta(hours=2)
    env.session.add(env.project)
    env.session.commit()
    a1, a2, a3 = env.arts(3)
    _ex(env.session, a1, env.owner, created_at=t + timedelta(hours=1))
    _ex(env.session, a2, env.owner, created_at=t + timedelta(hours=1))
    _ex(env.session, a3, env.owner, created_at=t + timedelta(hours=3))
    assert streak(env.session, env.project) == 1


# --- status and stats -----------------------------------------------------


def test_get_stopping_rule_status_for_viewer(env):
    env.prio(threshold=2)
    session = env.session
    a1, a2, p1, u1 = env.arts(4)
    (i1,) = env.arts(1, status=ArticleStatus.imported)
    _ex(session, a1, env.owner)
    _vote(session, p1, env.owner, D.uncertain)
    _ex(session, a2, env.owner)
    run = RankingRun(
        project_id=env.project.id, model_version="v", method="model", trigger="auto"
    )
    session.add(run)
    session.commit()
    viewer = env.member(env.project, ProjectRole.viewer)
    env.auth_as(viewer)

    res = env.client.get(f"{env.url}/stopping-rule")

    assert res.status_code == 200
    body = res.json()
    assert body | {
        "last_ranked_at": None,
        "counting_since": None,
        "last_run": None,
    } == {
        "enabled": True,
        "prioritized": True,
        "threshold": 2,
        "consecutive_excludes": 1,
        "met": False,
        "can_apply": False,
        "remaining": 2,
        "closable": 1,
        "screened": 2,
        "not_screened": 0,
        "last_ranked_at": None,
        "applied_at": None,
        "counting_since": None,
        "last_run": None,
    }
    assert body["last_ranked_at"][:19] == _naive(run.created_at).isoformat()[:19]
    assert body["last_run"]["id"] == run.id
    assert (
        body["counting_since"][:16]
        == _naive(env.project.prioritized_screening_enabled_at).isoformat()[:16]
    )
    assert i1 and u1


def test_status_without_threshold_is_disabled(env):
    env.prio(threshold=None)
    a1, a2 = env.arts(2)
    _ex(env.session, a1, env.owner)
    _ex(env.session, a2, env.owner)
    body = env.client.get(f"{env.url}/stopping-rule").json()
    assert body["enabled"] is False and body["met"] is False
    assert body["consecutive_excludes"] == 2 and body["prioritized"] is True


def test_stats_include_short_form(env):
    (a1,) = env.arts(1)
    assert env.client.get(f"{env.url}/stats").json()["stopping_rule"] is None
    env.prio(threshold=2)
    _ex(env.session, a1, env.owner)
    assert env.client.get(f"{env.url}/stats").json()["stopping_rule"] == {
        "enabled": True,
        "threshold": 2,
        "consecutive_excludes": 1,
        "met": False,
        "applied_at": None,
    }


def test_status_403_for_non_member(env):
    env.auth_as()
    assert env.client.get(f"{env.url}/stopping-rule").status_code == 403


# --- apply ----------------------------------------------------------------


def _met(env, threshold=2):
    """Prioritize and settle ``threshold`` excludes (returns the excluded articles)."""
    env.prio(threshold=threshold)
    done = env.arts(threshold)
    for a in done:
        _ex(env.session, a, env.owner)
    return done


def _apply(env, **body):
    return env.client.post(f"{env.url}/apply-stopping-rule", json=body or None)


def test_apply_409_when_prioritization_off(env):
    env.arts(1)
    res = _apply(env)
    assert res.status_code == 409 and "off" in res.json()["detail"]


def test_apply_409_without_threshold(env):
    env.prio(threshold=None)
    env.arts(1)
    res = _apply(env, force=True, reason="x")
    assert res.status_code == 409 and "No stopping rule" in res.json()["detail"]


def test_apply_409_when_not_met(env):
    env.prio(threshold=3)
    a1, u1 = env.arts(2)
    _ex(env.session, a1, env.owner)
    res = _apply(env)
    assert res.status_code == 409 and "1 of 3" in res.json()["detail"]
    env.session.expire_all()
    assert env.session.get(Article, u1.id).status == ArticleStatus.screening
    assert env.project.stopping_rule_applied_at is None
    assert not _events(env.session, env.project, "screening.stopping_rule_applied")


@pytest.mark.parametrize("body", [{"force": True}, {"force": True, "reason": "  "}])
def test_apply_force_requires_reason(env, body):
    env.prio()
    env.arts(1)
    assert _apply(env, **body).status_code == 422


def test_apply_409_when_nothing_to_close(env):
    _met(env)
    (p1,) = env.arts(1)
    _vote(env.session, p1, env.owner, D.uncertain)
    for body in ({}, {"force": True, "reason": "x"}):
        res = _apply(env, **body)
        assert res.status_code == 409
        assert "No unscreened records left" in res.json()["detail"]
    env.session.expire_all()
    assert env.project.stopping_rule_applied_at is None


def test_apply_closes_only_untouched_records(env):
    env.prio(threshold=2)
    session = env.session
    u1, u2, p1, e1, e2, f1 = env.arts(6)
    (i1,) = env.arts(1, status=ArticleStatus.imported)
    u1.full_text_content, u1.full_text_retrieved, u1.relevance_score = "x", True, 0.2
    f1.status, f1.current_stage = ArticleStatus.full_text_retrieved, FT
    session.add_all([u1, f1])
    session.commit()
    _vote(session, u2, None, D.include, source=AI)
    _vote(session, p1, env.owner, D.uncertain)
    _ex(session, e1, env.owner)
    _ex(session, e2, env.owner)
    before = len(session.exec(select(ScreeningDecision)).all())

    res = _apply(env)

    assert res.status_code == 200
    body = res.json()
    assert (body["closed"], body["left_open"], body["not_started"]) == (2, 1, 1)
    assert body["forced"] is False and body["reason"] is None
    session.expire_all()
    for a in (u1, u2):
        a = session.get(Article, a.id)
        assert a.status == ArticleStatus.excluded
        assert a.current_stage == ScreeningStage.completed
        assert a.final_decision == FinalDecision.excluded
        assert a.not_screened_stopping_rule is True
    u1 = session.get(Article, u1.id)
    assert (u1.full_text_content, u1.full_text_retrieved) == ("x", True)
    assert u1.relevance_score == 0.2
    assert session.get(Article, p1.id).status == ArticleStatus.screening
    assert session.get(Article, i1.id).status == ArticleStatus.imported
    assert session.get(Article, f1.id).status == ArticleStatus.full_text_retrieved
    assert len(session.exec(select(ScreeningDecision)).all()) == before
    project = env.project
    session.refresh(project)
    assert project.stopping_rule_applied_at is not None
    assert (
        body["applied_at"][:19]
        == _naive(project.stopping_rule_applied_at).isoformat()[:19]
    )


def test_apply_dual_leaves_partial_and_conflicts_open(env):
    env.prio(threshold=2, reviewers=2)
    session = env.session
    r1, r2 = env.member(env.project), env.member(env.project)
    partial, conflict, untouched, e1, e2 = env.arts(5)
    _vote(session, partial, r1, D.exclude)
    _vote(session, conflict, r1, D.include)
    _vote(session, conflict, r2, D.exclude)
    _agreed_ex(session, e1, r1, r2)
    _agreed_ex(session, e2, r1, r2)

    body = _apply(env).json()

    assert (body["closed"], body["left_open"]) == (1, 2)
    session.expire_all()
    assert session.get(Article, untouched.id).not_screened_stopping_rule is True
    assert session.get(Article, partial.id).status == ArticleStatus.screening
    conflicts = env.client.get(f"{env.url}/conflicts").json()
    assert [c["article_id"] for c in conflicts] == [conflict.id]


def test_apply_audit_payload(env):
    _met(env)
    (u1,) = env.arts(1)
    _vote(env.session, u1, None, D.uncertain, source=AI)  # AI is ignored
    (extra,) = env.arts(1)
    _ex(env.session, extra, env.owner)
    run = RankingRun(
        project_id=env.project.id,
        model_version="tfidf-logreg-v1",
        method="model",
        trigger="auto",
    )
    env.session.add(run)
    env.session.commit()

    assert _apply(env).status_code == 200

    (event,) = _events(env.session, env.project, "screening.stopping_rule_applied")
    assert event.entity_type == "project" and event.user_id == env.owner.id
    assert event.details == {
        "threshold": 2,
        "consecutive_excludes": 3,
        "closed": 1,
        "left_open": 0,
        "not_started": 0,
        "screened": 3,
        "forced": False,
        "reason": None,
        "counting_since": event.details["counting_since"],
        "ranking_run_id": run.id,
        "model_version": "tfidf-logreg-v1",
        "ranking_method": "model",
    }
    assert event.details["counting_since"]


def test_apply_forced_records_reason(env):
    env.prio(threshold=3)
    env.arts(2)
    res = _apply(env, force=True, reason="Time-boxed review")
    assert res.status_code == 200
    assert res.json()["forced"] is True
    (event,) = _events(env.session, env.project, "screening.stopping_rule_applied")
    assert event.details["forced"] is True
    assert event.details["reason"] == "Time-boxed review"
    assert event.details["consecutive_excludes"] == 0
    assert event.details["model_version"] is None


def test_apply_met_with_force_is_not_forced(env):
    _met(env)
    env.arts(1)
    body = _apply(env, force=True, reason="Because").json()
    assert body["forced"] is False and body["reason"] == "Because"


def test_apply_notifies_project_room(env, monkeypatch):
    _met(env)
    env.arts(2)
    notify = AsyncMock()
    monkeypatch.setattr(stopping.NotificationService, "notify_room", notify)
    assert _apply(env).status_code == 200
    notify.assert_awaited_once()
    kwargs = notify.await_args.kwargs
    assert kwargs["room_name"] == f"project_{env.project.id}"
    assert kwargs["data"]["type"] == "stopping_rule_applied"
    assert kwargs["data"]["closed"] == 2


# --- permissions and billing ----------------------------------------------


@pytest.mark.parametrize("role", [ProjectRole.reviewer, ProjectRole.viewer])
@pytest.mark.parametrize("endpoint", ["apply-stopping-rule", "reopen-not-screened"])
def test_apply_and_reopen_forbidden_for_reviewer_and_viewer(env, role, endpoint):
    _met(env)
    (u1,) = env.arts(1)
    env.auth_as(env.member(env.project, role))
    assert env.client.post(f"{env.url}/{endpoint}").status_code == 403
    env.session.expire_all()
    assert env.session.get(Article, u1.id).status == ArticleStatus.screening


def test_apply_and_reopen_402_on_expired_pass(env, monkeypatch):
    settings = Settings(
        _env_file=None,
        secret_key="x",
        billing_enabled=True,
        stripe_secret_key="sk_test_123",
        stripe_webhook_secret="whsec",
        public_app_url="https://app.test",
    )
    monkeypatch.setattr("app.features.billing.services.get_settings", lambda: settings)
    _met(env)
    env.arts(1)
    now = _now()
    env.session.add(
        ProjectPlan(
            project_id=env.project.id,
            tier="pass_250",
            fulltext_limit=250,
            activated_at=now - timedelta(days=400),
            expires_at=now - timedelta(days=10),
            source="admin",
        )
    )
    env.session.commit()
    assert _apply(env).status_code == 402
    assert env.client.post(f"{env.url}/reopen-not-screened").status_code == 402
    assert env.client.get(f"{env.url}/stopping-rule").status_code == 200


# --- closed records are skipped -------------------------------------------


@pytest.fixture
def closed(env):
    """Met rule with two closed records and one left-open (uncertain) record."""
    env.prio(threshold=2)
    p1, u1, u2, e1, e2 = env.arts(5)
    _vote(env.session, p1, env.owner, D.uncertain)
    _ex(env.session, e1, env.owner)
    _ex(env.session, e2, env.owner)
    assert _apply(env).json()["closed"] == 2
    env.session.expire_all()
    env.closed, env.open = [u1, u2], p1
    return env


def test_closed_records_reject_human_decisions(closed):
    env = closed
    closed_id = env.closed[0].id
    before = len(env.session.exec(select(ScreeningDecision)).all())
    for stage in ("title_abstract", "full_text"):
        res = env.client.post(
            f"{env.url}/articles/{closed_id}/decisions",
            json={"stage": stage, "decision": "include"},
        )
        assert res.status_code == 409 and "stopping rule" in res.json()["detail"]
    assert len(env.session.exec(select(ScreeningDecision)).all()) == before


def test_closed_records_not_served(closed):
    env = closed
    env.auth_as(env.member(env.project))
    body = env.client.get(f"{env.url}/next").json()
    assert body["article"]["id"] == env.open.id
    res = env.client.get(
        f"{BASE}/{env.project.id}/articles", params={"pending_for_me": True}
    )
    assert [a["id"] for a in res.json()["data"]] == [env.open.id]


def test_run_ai_skips_closed_records(closed, monkeypatch):
    env = closed
    monkeypatch.setattr(
        "app.features.research.agent.get_settings",
        lambda: Settings(_env_file=None, secret_key="x", anthropic_api_key="k"),
    )
    flow = AsyncMock()
    monkeypatch.setattr("app.features.screening.routers.batch_ai_screening_flow", flow)
    inflight.clear()
    env.session.add(
        Criterion(
            project_id=env.project.id,
            type=CriterionType.inclusion,
            code="I1",
            description="d",
        )
    )
    env.session.commit()
    closed_ids = {a.id for a in env.closed}

    res = env.client.post(f"{env.url}/run-ai")
    assert res.status_code == 200
    assert closed_ids.isdisjoint(res.json()["article_ids"])
    inflight.clear()

    res = env.client.post(f"{env.url}/run-ai", json={"article_ids": [env.closed[0].id]})
    assert res.json()["article_count"] == 0
    inflight.clear()


def test_screen_ai_rejects_closed_record(closed, monkeypatch):
    env = closed
    screen = AsyncMock()
    monkeypatch.setattr("app.features.screening.routers.screen_article", screen)
    res = env.client.post(f"{env.url}/articles/{env.closed[0].id}/screen-ai")
    assert res.status_code == 409 and "stopping rule" in res.json()["detail"]
    screen.assert_not_called()
    assert env.session.exec(select(AIUsage)).first() is None


@pytest.mark.asyncio
async def test_batch_flow_skips_closed_record(closed, monkeypatch):
    env = closed
    monkeypatch.setattr(flows, "Session", lambda _engine: nullcontext(env.session))
    room = AsyncMock(return_value=1)
    monkeypatch.setattr(flows.NotificationService, "notify_room", room)
    monkeypatch.setattr(flows.NotificationService, "notify_user_in_room", AsyncMock())
    env.session.add(
        Criterion(
            project_id=env.project.id,
            type=CriterionType.inclusion,
            code="I1",
            description="d",
        )
    )
    env.session.commit()
    calls = []

    async def fake(article, **_):
        calls.append(article.id)
        d = ScreeningDecision(
            article_id=article.id, stage=TA, decision=D.include, source=AI
        )
        env.session.add(d)
        env.session.commit()
        return d

    monkeypatch.setattr(flows, "screen_article", fake)

    result = await flows.batch_ai_screening_flow.fn(
        env.project.id, [env.closed[0].id, env.open.id], env.owner.id
    )

    assert result == {"total": 2, "screened": 1, "errors": 0, "skipped": 1}
    assert calls == [env.open.id]
    types = [c.kwargs["data"].get("type") for c in room.await_args_list]
    assert "ai_screening_skipped" in types


# --- reopen -----------------------------------------------------------------


def test_reopen_restores_records(env):
    _met(env)
    u1, u2 = env.arts(2)
    u1.relevance_score = 0.4
    env.session.add(u1)
    env.session.commit()
    before = env.client.get(f"{env.url}/stopping-rule").json()["consecutive_excludes"]
    applied = _apply(env).json()["applied_at"]

    res = env.client.post(f"{env.url}/reopen-not-screened")

    assert res.status_code == 200
    assert res.json()["reopened"] == 2
    assert res.json()["previous_applied_at"][:19] == applied[:19]
    env.session.expire_all()
    for a in (u1, u2):
        a = env.session.get(Article, a.id)
        assert a.status == ArticleStatus.screening
        assert a.current_stage == TA and a.final_decision == FinalDecision.pending
        assert a.not_screened_stopping_rule is False
    assert env.session.get(Article, u1.id).relevance_score == 0.4
    env.session.refresh(env.project)
    assert env.project.stopping_rule_applied_at is None
    (event,) = _events(env.session, env.project, "screening.stopping_rule_reverted")
    assert event.details["reopened"] == 2
    assert event.details["previous_applied_at"][:19] == applied[:19]
    status = env.client.get(f"{env.url}/stopping-rule").json()
    assert status["not_screened"] == 0 and status["met"] is True
    assert status["consecutive_excludes"] == before


def test_reopen_409_when_nothing_closed(env):
    env.prio()
    res = env.client.post(f"{env.url}/reopen-not-screened")
    assert res.status_code == 409
    assert not _events(env.session, env.project, "screening.stopping_rule_reverted")


def test_reopen_schedules_rerank(env, monkeypatch):
    _met(env)
    env.arts(1)
    _apply(env)
    calls = []
    monkeypatch.setattr(
        "app.features.screening.routers.ranking.schedule_rerank",
        lambda _bg, project, **kw: calls.append((project.id, kw)),
    )
    assert env.client.post(f"{env.url}/reopen-not-screened").status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == env.project.id and calls[0][1]["force"] is True


def test_reopen_after_prioritization_turned_off(env):
    _met(env)
    (u1,) = env.arts(1)
    _apply(env)
    res = env.client.patch(
        f"{BASE}/{env.project.id}", json={"prioritized_screening": False}
    )
    assert res.status_code == 200
    assert env.client.post(f"{env.url}/reopen-not-screened").status_code == 200
    env.session.expire_all()
    assert env.session.get(Article, u1.id).status == ArticleStatus.screening


# --- re-apply ----------------------------------------------------------------


def test_reapply_after_new_import_needs_fresh_streak(env):
    env.prio(threshold=2)
    session = env.session
    old = _now() - timedelta(hours=3)
    e1, e2, u1 = env.arts(3)
    _ex(session, e1, env.owner, created_at=old)
    _ex(session, e2, env.owner, created_at=old)
    first = _apply(env).json()
    assert first["closed"] == 1
    session.refresh(env.project)
    env.project.stopping_rule_applied_at = env.project.stopping_rule_applied_at - (
        timedelta(hours=1)
    )
    session.add(env.project)
    session.commit()

    n1, n2, n3, n4 = env.arts(4)
    status = env.client.get(f"{env.url}/stopping-rule").json()
    assert (status["met"], status["consecutive_excludes"], status["closable"]) == (
        False,
        0,
        4,
    )
    assert _apply(env).status_code == 409

    for art in (n1, n2):
        res = env.client.post(
            f"{env.url}/articles/{art.id}/decisions",
            json={"stage": "title_abstract", "decision": "exclude"},
        )
        assert res.status_code == 201
    assert env.client.get(f"{env.url}/stopping-rule").json()["met"] is True

    second = _apply(env).json()
    assert second["closed"] == 2
    assert env.client.get(f"{env.url}/stopping-rule").json()["not_screened"] == 3
    assert second["applied_at"] > first["applied_at"]
    assert len(_events(session, env.project, "screening.stopping_rule_applied")) == 2
    assert u1 and n3 and n4


# --- votes spanning the window, API votes, imports --------------------------


def _spanning(env, pre_decision, post_decision, reviewers):
    t = _now()
    env.prio(since=t, reviewers=reviewers)
    r1, r2 = env.member(env.project), env.member(env.project)
    a1, a2 = env.arts(2)
    pre, post = t - timedelta(hours=1), t + timedelta(hours=1)
    _vote(env.session, a1, r1, pre_decision, created_at=pre)
    _vote(env.session, a1, r2, post_decision, created_at=post)
    return r1, r2, a1, a2, post


@pytest.mark.parametrize(
    "pre,post",
    [(D.include, D.exclude), (D.uncertain, D.exclude), (D.exclude, D.include)],
)
def test_dual_conflict_spanning_window_resets(env, pre, post):
    r1, r2, a1, a2, at = _spanning(env, pre, post, reviewers=2)
    _vote(env.session, a2, r1, D.exclude, created_at=at)
    _ex(env.session, a2, r2, created_at=at)
    assert streak(env.session, env.project) == 1  # only a2, after the reset


def test_single_uncertain_before_window_resets(env):
    r1, r2, a1, a2, _ = _spanning(env, D.uncertain, D.exclude, reviewers=1)
    _close_ta(env.session, a1, D.exclude)
    # a1 settled as an exclude after r1's older uncertain vote reset the streak
    assert streak(env.session, env.project) == 1


def test_dual_votes_through_api_and_include_resolution(env):
    env.prio(threshold=2, reviewers=2)
    r1, r2 = env.member(env.project), env.member(env.project)
    a1, a2, a3 = env.arts(3)

    def vote(user, art, decision):
        env.auth_as(user)
        res = env.client.post(
            f"{env.url}/articles/{art.id}/decisions",
            json={"stage": "title_abstract", "decision": decision},
        )
        assert res.status_code == 201

    vote(r1, a1, "exclude")
    vote(r2, a1, "exclude")
    vote(r1, a2, "include")
    vote(r2, a2, "exclude")
    assert streak(env.session, env.project) == 0  # conflict
    env.auth_as(env.owner)
    res = env.client.post(
        f"{env.url}/articles/{a2.id}/resolve",
        json={"decision": "include", "reason": "relevant"},
    )
    assert res.status_code in (200, 201)
    assert streak(env.session, env.project) == 0  # include resolution
    vote(r1, a3, "exclude")
    vote(r2, a3, "exclude")
    assert streak(env.session, env.project) == 1


def test_import_after_met_needs_fresh_streak(env):
    env.prio(threshold=2)
    old = _now() - timedelta(hours=3)
    for a in env.arts(2):
        _ex(env.session, a, env.owner, created_at=old)
    assert env.client.get(f"{env.url}/stopping-rule").json()["met"] is True
    batch = ImportBatch(project_id=env.project.id, filename="u.ris", format="ris")
    env.session.add(batch)
    env.session.commit()
    env.arts(2)
    body = env.client.get(f"{env.url}/stopping-rule").json()
    assert body["met"] is False and body["consecutive_excludes"] == 0
    assert body["counting_since"][:19] == _naive(batch.created_at).isoformat()[:19]
    assert _apply(env).status_code == 409


def test_can_apply_false_when_nothing_closable(env):
    _met(env)
    (p1,) = env.arts(1)
    _vote(env.session, p1, env.owner, D.uncertain)
    body = env.client.get(f"{env.url}/stopping-rule").json()
    assert body["can_apply"] is False
    env.arts(1)
    # the uncertain vote reset the streak only if it came after the excludes
    assert env.client.get(f"{env.url}/stopping-rule").json()["can_apply"] is False


def test_ai_decision_rejected_on_closed_record(closed):
    env = closed
    res = env.client.post(
        f"{env.url}/articles/{env.closed[0].id}/decisions",
        json={"stage": "title_abstract", "decision": "include", "source": "ai_agent"},
    )
    assert res.status_code == 409
