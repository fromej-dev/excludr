"""Tests for the batch AI screening Prefect flow."""

from contextlib import nullcontext
from unittest.mock import AsyncMock

import pytest

from app.features.criteria.models import Criterion, CriterionType
from app.features.research.models import Article, ArticleStatus
from app.features.screening import flows
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
)


@pytest.fixture
def notifier(monkeypatch):
    """Capture websocket notifications sent by the flow."""
    room = AsyncMock(return_value=1)
    user = AsyncMock(return_value=True)
    monkeypatch.setattr(flows.NotificationService, "notify_room", room)
    monkeypatch.setattr(flows.NotificationService, "notify_user_in_room", user)
    return room, user


@pytest.fixture
def flow_session(session, monkeypatch):
    """Make the flow's own ``Session(engine)`` use the per-test session."""
    monkeypatch.setattr(flows, "Session", lambda _engine: nullcontext(session))
    return session


@pytest.fixture
def setup(session, a_user, a_project):
    user = a_user()
    project = a_project(user)
    project.review_question = "Q?"
    session.add(project)
    session.add(
        Criterion(
            project_id=project.id,
            type=CriterionType.inclusion,
            code="I1",
            description="d",
            is_active=True,
        )
    )
    articles = []
    for i in range(3):
        a = Article(
            project_id=project.id,
            title=f"A{i}",
            status=ArticleStatus.screening,
        )
        session.add(a)
        articles.append(a)
    session.commit()
    return user, project, articles


def _fake_screen(fail_ids=()):
    calls = []

    async def fake(article, criteria, review_question, session, reviewer_id=None):
        calls.append((article.id, [c.code for c in criteria], review_question))
        if article.id in fail_ids:
            raise RuntimeError("provider exploded: secret")
        d = ScreeningDecision(
            article_id=article.id,
            stage=ScreeningStage.title_abstract,
            decision=ScreeningDecisionType.include,
            source=DecisionSource.ai_agent,
            confidence_score=0.9,
        )
        session.add(d)
        session.commit()
        return d

    return fake, calls


@pytest.mark.asyncio
async def test_flow_screens_all_and_notifies(
    flow_session, setup, notifier, monkeypatch
):
    user, project, articles = setup
    fake, calls = _fake_screen()
    monkeypatch.setattr(flows, "screen_article", fake)
    ids = [a.id for a in articles]

    result = await flows.batch_ai_screening_flow.fn(project.id, ids, user.id)

    assert result == {"total": 3, "screened": 3, "errors": 0}
    assert [c[0] for c in calls] == ids
    assert calls[0][1:] == (["I1"], "Q?")
    room, user_notify = notifier
    # 3 progress messages + 1 completion on the project room
    assert room.await_count == 4
    assert all(
        c.kwargs["room_name"] == f"project_{project.id}" for c in room.await_args_list
    )
    last = room.await_args_list[-1].kwargs["data"]
    assert last["type"] == "ai_screening_complete"
    assert (last["screened"], last["total"], last["errors"]) == (3, 3, 0)
    user_notify.assert_awaited_once()
    assert user_notify.await_args.kwargs["data"]["type"] == "ai_screening_complete"


@pytest.mark.asyncio
async def test_flow_isolates_per_article_errors(
    flow_session, setup, notifier, monkeypatch
):
    user, project, articles = setup
    fake, calls = _fake_screen(fail_ids={articles[1].id})
    monkeypatch.setattr(flows, "screen_article", fake)

    result = await flows.batch_ai_screening_flow.fn(
        project.id, [a.id for a in articles], user.id
    )

    assert result == {"total": 3, "screened": 2, "errors": 1}
    assert len(calls) == 3  # batch continued after the failure
    room, _ = notifier
    payloads = [c.kwargs["data"] for c in room.await_args_list]
    err = [p for p in payloads if p["type"] == "ai_screening_error"]
    assert len(err) == 1 and err[0]["article_id"] == articles[1].id
    assert "secret" not in str(payloads)  # no raw exception text to clients
    final = payloads[-1]
    assert (final["screened"], final["errors"]) == (2, 1)


@pytest.mark.asyncio
async def test_flow_skips_unknown_and_foreign_articles(
    flow_session, setup, notifier, monkeypatch, session
):
    user, project, articles = setup
    other = Article(project_id=project.id + 999, title="foreign")
    session.add(other)
    session.commit()
    fake, calls = _fake_screen()
    monkeypatch.setattr(flows, "screen_article", fake)

    result = await flows.batch_ai_screening_flow.fn(
        project.id, [articles[0].id, 987654, other.id], user.id
    )

    assert [c[0] for c in calls] == [articles[0].id]
    assert result["screened"] == 1 and result["errors"] == 2


@pytest.mark.asyncio
async def test_flow_survives_notification_failure(
    flow_session, setup, notifier, monkeypatch
):
    user, project, articles = setup
    fake, _ = _fake_screen()
    monkeypatch.setattr(flows, "screen_article", fake)
    notifier[0].side_effect = RuntimeError("ws down")

    result = await flows.batch_ai_screening_flow.fn(
        project.id, [a.id for a in articles], user.id
    )
    assert result["screened"] == 3


@pytest.mark.asyncio
async def test_flow_without_active_criteria_reports_error(
    flow_session, setup, notifier, monkeypatch, session
):
    user, project, articles = setup
    for c in session.query(Criterion).all():
        c.is_active = False
        session.add(c)
    session.commit()
    fake, calls = _fake_screen()
    monkeypatch.setattr(flows, "screen_article", fake)

    result = await flows.batch_ai_screening_flow.fn(
        project.id, [a.id for a in articles], user.id
    )
    assert calls == []
    assert result["screened"] == 0 and result["errors"] == 3
