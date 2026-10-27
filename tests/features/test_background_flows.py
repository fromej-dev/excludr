"""Regression tests: background endpoints must actually run their Prefect flows.

A Prefect ``Flow`` object is not detected as a coroutine function by Starlette, so
passing it straight to ``BackgroundTasks.add_task`` runs it in a thread and the
returned coroutine is never awaited. These tests use real Prefect flows (not
``AsyncMock``, which hides the problem).
"""

import pytest
from prefect import flow

from app.features.criteria.models import Criterion, CriterionType
from app.features.research.models import Article, ArticleStatus
from app.features.screening.models import ScreeningStage

BASE_API = "api/v1/projects"


@pytest.fixture
def calls():
    return []


@pytest.fixture
def recording_flow(calls):
    @flow(name="recording_flow")
    async def _recording_flow(project_id: int, article_ids: list[int], user_id: int):
        calls.append((project_id, sorted(article_ids), user_id))

    return _recording_flow


def test_run_ai_executes_flow(
    auth_as, a_project, session, monkeypatch, recording_flow, calls
):
    from app.core.config import Settings

    monkeypatch.setattr(
        "app.features.research.agent.get_settings",
        lambda: Settings(_env_file=None, secret_key="x", anthropic_api_key="k"),
    )
    monkeypatch.setattr(
        "app.features.screening.routers.batch_ai_screening_flow", recording_flow
    )
    client, user = auth_as()
    project = a_project(user)
    session.add(
        Criterion(
            project_id=project.id,
            type=CriterionType.inclusion,
            code="I1",
            description="Adults",
        )
    )
    article = Article(
        project_id=project.id,
        title="A",
        status=ArticleStatus.screening,
        current_stage=ScreeningStage.title_abstract,
    )
    session.add(article)
    session.commit()

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai")

    assert res.status_code == 200
    assert res.json()["article_count"] == 1
    assert calls == [(project.id, [article.id], user.id)]


def test_bulk_fulltext_retrieval_executes_flow(
    auth_as, a_project, session, monkeypatch, recording_flow, calls
):
    monkeypatch.setattr(
        "app.features.research.routers.retrieve_fulltext_flow", recording_flow
    )
    client, user = auth_as()
    project = a_project(user)
    article = Article(
        project_id=project.id,
        title="B",
        doi="10.1/b",
        status=ArticleStatus.awaiting_full_text,
        current_stage=ScreeningStage.full_text,
    )
    session.add(article)
    session.commit()

    res = client.post(f"{BASE_API}/{project.id}/articles/retrieve-fulltext")

    assert res.status_code == 200
    assert res.json()["count"] == 1
    assert calls == [(project.id, [article.id], user.id)]
