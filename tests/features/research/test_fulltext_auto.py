"""Full-text retrieval starts by itself when an article starts waiting for its full text."""

from contextlib import nullcontext
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from app.core.config import get_settings
from app.features.audit.models import AuditEvent
from app.features.projects.models import ProjectRole
from app.features.research import flows
from app.features.research.models import Article, ArticleStatus
from app.features.screening.models import ScreeningStage
from .fulltext_helpers import pdf_response
from .test_fulltext_flow_and_api import oa_pdf, unpaywall

BASE = "api/v1/projects"


@pytest.fixture
def auto_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "fulltext_auto_retrieval", True)


@pytest.fixture
def scheduled(monkeypatch):
    """Record the flow runs the endpoints queue instead of running them."""
    calls = []

    async def fake_flow(project_id, article_ids, user_id, trigger="manual"):
        calls.append((project_id, article_ids, user_id, trigger))

    monkeypatch.setattr(flows, "retrieve_fulltext_flow", fake_flow)
    return calls


@pytest.fixture
def notifier(monkeypatch):
    room = AsyncMock(return_value=1)
    user = AsyncMock(return_value=True)
    monkeypatch.setattr(flows.NotificationService, "notify_room", room)
    monkeypatch.setattr(flows.NotificationService, "notify_user_in_room", user)
    return room, user


def _decide(client, project, article, decision="include", stage="title_abstract"):
    res = client.post(
        f"{BASE}/{project.id}/screening/articles/{article.id}/decisions",
        json={"stage": stage, "decision": decision, "source": "human"},
    )
    assert res.status_code == 201, res.text
    return res


def _status(session, article):
    session.expire_all()
    return session.get(Article, article.id).status


def test_include_at_title_abstract_starts_retrieval(
    auto_on, scheduled, auth_as, a_project, an_article_in, session
):
    client, user = auth_as()
    project = a_project(user)
    article = an_article_in(project)

    _decide(client, project, article)

    assert _status(session, article) == ArticleStatus.awaiting_full_text
    assert scheduled == [(project.id, [article.id], user.id, "auto")]


def test_no_retrieval_for_other_outcomes_or_when_switched_off(
    auto_on, scheduled, auth_as, a_project, an_article_in, monkeypatch
):
    client, user = auth_as()
    project = a_project(user)

    _decide(client, project, an_article_in(project), "exclude")
    _decide(client, project, an_article_in(project), "uncertain")
    # A full text uploaded earlier skips retrieval altogether
    _decide(client, project, an_article_in(project, full_text_retrieved=True))
    # Deciding again at the full-text stage does not start it again
    waiting = an_article_in(
        project,
        status=ArticleStatus.awaiting_full_text,
        current_stage=ScreeningStage.full_text,
    )
    _decide(client, project, waiting, "uncertain", stage="full_text")
    assert scheduled == []

    monkeypatch.setattr(get_settings(), "fulltext_auto_retrieval", False)
    _decide(client, project, an_article_in(project))
    assert scheduled == []


def test_dual_screening_starts_retrieval_once_settled(
    auto_on, scheduled, auth_as, a_project, a_member, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    project.required_reviewers = 2
    session.add(project)
    session.commit()
    r1 = a_member(project, ProjectRole.reviewer)
    r2 = a_member(project, ProjectRole.reviewer)
    agreed = an_article_in(project)
    disputed = an_article_in(project)

    auth_as(r1)
    _decide(client, project, agreed)
    _decide(client, project, disputed)
    assert scheduled == []
    auth_as(r2)
    _decide(client, project, agreed)
    _decide(client, project, disputed, "exclude")
    assert scheduled == [(project.id, [agreed.id], r2.id, "auto")]

    scheduled.clear()
    auth_as(owner)
    res = client.post(
        f"{BASE}/{project.id}/screening/articles/{disputed.id}/resolve",
        json={"decision": "include", "reason": "fits the population"},
    )
    assert res.status_code == 200
    assert scheduled == [(project.id, [disputed.id], owner.id, "auto")]


def test_lowering_required_reviewers_starts_retrieval_for_settled_articles(
    auto_on, scheduled, auth_as, a_project, a_member, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    project.required_reviewers = 2
    session.add(project)
    session.commit()
    reviewer = a_member(project, ProjectRole.reviewer)
    article = an_article_in(project)
    already_waiting = an_article_in(
        project,
        status=ArticleStatus.awaiting_full_text,
        current_stage=ScreeningStage.full_text,
    )
    auth_as(reviewer)
    _decide(client, project, article)
    assert scheduled == []

    auth_as(owner)
    res = client.patch(f"{BASE}/{project.id}", json={"required_reviewers": 1})
    assert res.status_code == 200
    assert _status(session, article) == ArticleStatus.awaiting_full_text
    assert scheduled == [(project.id, [article.id], owner.id, "auto")]
    assert already_waiting.id not in scheduled[0][1]


def test_decision_retrieves_full_text_in_background(
    auto_on, auth_as, a_project, an_article_in, web, notifier, session, monkeypatch
):
    monkeypatch.setattr(flows, "Session", lambda _engine: nullcontext(session))
    client, user = auth_as()
    project = a_project(user)
    article = an_article_in(project, doi="10.1/auto")
    web.add(unpaywall("10.1/auto"), oa_pdf("auto")).add(
        "oa.example.org/auto.pdf", pdf_response()
    )

    _decide(client, project, article)

    session.expire_all()
    article = session.get(Article, article.id)
    assert article.status == ArticleStatus.full_text_retrieved
    assert article.full_text_source == "unpaywall"

    # Quiet: only the project room hears about it, marked as automatic
    room, user_notify = notifier
    user_notify.assert_not_awaited()
    payloads = [c.kwargs["data"] for c in room.await_args_list]
    assert payloads[-1]["type"] == "fulltext_complete"
    assert all(p["auto"] is True for p in payloads)
    details = [
        e.details
        for e in session.exec(
            select(AuditEvent).where(
                AuditEvent.project_id == project.id,
                AuditEvent.action == "fulltext_batch.started",
            )
        ).all()
    ]
    assert details == [{"article_count": 1, "trigger": "auto"}]


@pytest.mark.asyncio
async def test_flow_skips_articles_no_longer_waiting(
    a_user, a_project, an_article_in, web, notifier, session, monkeypatch
):
    monkeypatch.setattr(flows, "Session", lambda _engine: nullcontext(session))
    user = a_user()
    project = a_project(user)
    # A full text was uploaded between scheduling and the flow's turn
    uploaded = an_article_in(
        project,
        doi="10.1/uploaded",
        status=ArticleStatus.full_text_retrieved,
        current_stage=ScreeningStage.full_text,
        full_text_retrieved=True,
    )

    result = await flows.retrieve_fulltext_flow.fn(
        project.id, [uploaded.id], user.id, "auto"
    )

    assert result == {"total": 0, "retrieved": 0, "failed": 0}
    assert web.requests == []
