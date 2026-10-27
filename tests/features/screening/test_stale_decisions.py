"""Criteria snapshots, stale AI decision detection and rescreen_stale."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.features.criteria.models import Criterion, CriterionType
from app.features.research.models import Article, ArticleStatus
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
)
from app.features.screening.services import ScreeningService

BASE = "api/v1/projects"


@pytest.fixture(autouse=True)
def _ai_configured(monkeypatch):
    monkeypatch.setattr(
        "app.features.research.agent.get_settings",
        lambda: Settings(_env_file=None, secret_key="x", anthropic_api_key="k"),
    )
    flow_mock = AsyncMock()
    monkeypatch.setattr(
        "app.features.screening.routers.batch_ai_screening_flow", flow_mock
    )
    return flow_mock


def _article(session, pid, title="T"):
    a = Article(project_id=pid, title=title, status=ArticleStatus.screening)
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _criterion(session, pid, code="I1", **kw):
    c = Criterion(
        project_id=pid,
        type=kw.pop("type", CriterionType.inclusion),
        code=code,
        description="d",
        **kw,
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _ai(session, article, snapshot, **kw):
    d = ScreeningDecision(
        article_id=article.id,
        stage=ScreeningStage.title_abstract,
        decision=ScreeningDecisionType.include,
        source=DecisionSource.ai_agent,
        criteria_snapshot=snapshot,
        **kw,
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


def test_stale_endpoint_lists_only_stale(auth_as, a_project, session):
    client, user = auth_as()
    p = a_project(user)
    c = _criterion(session, p.id)
    fresh = _article(session, p.id, "fresh")
    stale = _article(session, p.id, "stale")
    legacy = _article(session, p.id, "legacy")
    _article(session, p.id, "none")
    _ai(session, fresh, {"I1": 1})
    _ai(session, stale, {"I1": 1})
    _ai(session, legacy, None)

    res = client.get(f"{BASE}/{p.id}/screening/stale-ai-decisions")
    assert res.status_code == 200
    # legacy (no snapshot) cannot be verified, so it is reported as stale
    assert set(res.json()["article_ids"]) == {legacy.id}

    c.version = 2
    session.add(c)
    session.commit()
    res = client.get(f"{BASE}/{p.id}/screening/stale-ai-decisions")
    assert set(res.json()["article_ids"]) == {fresh.id, stale.id, legacy.id}
    assert res.json()["count"] == 3


def test_stale_when_active_set_changes(auth_as, a_project, session):
    client, user = auth_as()
    p = a_project(user)
    _criterion(session, p.id, "I1")
    a = _article(session, p.id)
    _ai(session, a, {"I1": 1})
    assert (
        client.get(f"{BASE}/{p.id}/screening/stale-ai-decisions").json()["count"] == 0
    )
    _criterion(session, p.id, "E1", type=CriterionType.exclusion)
    assert (
        client.get(f"{BASE}/{p.id}/screening/stale-ai-decisions").json()["count"] == 1
    )


def test_only_latest_ai_decision_counts(auth_as, a_project, session):
    client, user = auth_as()
    p = a_project(user)
    _criterion(session, p.id, "I1")
    a = _article(session, p.id)
    _ai(session, a, {"I1": 0})  # old, stale
    _ai(session, a, {"I1": 1})  # latest, fresh
    assert (
        client.get(f"{BASE}/{p.id}/screening/stale-ai-decisions").json()["count"] == 0
    )


def test_stale_endpoint_ownership(auth_as, a_project, a_user):
    client, _ = auth_as()
    other = a_project(a_user())
    assert (
        client.get(f"{BASE}/{other.id}/screening/stale-ai-decisions").status_code == 403
    )


def test_run_ai_rescreen_stale(auth_as, a_project, session, _ai_configured):
    client, user = auth_as()
    p = a_project(user)
    c = _criterion(session, p.id)
    a = _article(session, p.id)
    _ai(session, a, {"I1": 1})

    res = client.post(f"{BASE}/{p.id}/screening/run-ai?rescreen_stale=true")
    assert res.json()["article_count"] == 0  # not stale yet

    c.version = 2
    session.add(c)
    session.commit()
    assert client.post(f"{BASE}/{p.id}/screening/run-ai").json()["article_count"] == 0
    res = client.post(f"{BASE}/{p.id}/screening/run-ai?rescreen_stale=true")
    assert res.json()["article_count"] == 1
    assert _ai_configured.call_args.args[1] == [a.id]


def test_latest_decision_tiebreak_by_id(auth_as, a_project, session):
    client, user = auth_as()
    p = a_project(user)
    _criterion(session, p.id)
    a = _article(session, p.id)
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = _ai(session, a, {"I1": 1}, created_at=ts, reasoning="first")
    second = _ai(session, a, {"I1": 1}, created_at=ts, reasoning="second")
    assert second.id > first.id

    res = client.get(f"{BASE}/{p.id}/screening/articles/{a.id}/ai-decision")
    assert res.json()["id"] == second.id
    svc = ScreeningService(session)
    latest = svc.get_latest_decision(a.id, ScreeningStage.title_abstract)
    assert latest.id == second.id
    listed = session.exec(svc.get_decisions_for_article(a.id)).all()
    assert [d.id for d in listed] == [second.id, first.id]


def test_stale_uses_id_tiebreak(auth_as, a_project, session):
    client, user = auth_as()
    p = a_project(user)
    _criterion(session, p.id)
    a = _article(session, p.id)
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _ai(session, a, {"I1": 1}, created_at=ts)
    _ai(session, a, {"I1": 0}, created_at=ts)  # same ts, higher id -> latest, stale
    assert set(
        client.get(f"{BASE}/{p.id}/screening/stale-ai-decisions").json()["article_ids"]
    ) == {a.id}
