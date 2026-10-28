"""Tests for AI screening endpoints."""

from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.features.screening import inflight
from app.features.screening.routers import _run_batch_and_release
from app.features.research.models import Article, ArticleStatus, ScreeningStage
from app.features.criteria.models import Criterion, CriterionType
from app.features.screening.models import (
    ScreeningDecision,
    ScreeningDecisionType,
    DecisionSource,
)

BASE_API = "api/v1/projects"


@pytest.fixture(autouse=True)
def _ai_configured(monkeypatch):
    """Pretend an Anthropic key is configured and never start the real flow."""
    monkeypatch.setattr(
        "app.features.research.agent.get_settings",
        lambda: Settings(_env_file=None, secret_key="x", anthropic_api_key="k"),
    )
    flow_mock = AsyncMock()
    monkeypatch.setattr(
        "app.features.screening.routers.batch_ai_screening_flow", flow_mock
    )
    inflight.clear()
    yield flow_mock
    inflight.clear()


@pytest.fixture
def a_article(session):
    """Factory fixture to create articles."""

    def _create_article(project_id, **kwargs):
        defaults = {
            "title": "Test Article",
            "abstract": "This is a test article abstract",
            "status": ArticleStatus.screening,
            "current_stage": ScreeningStage.title_abstract,
            "project_id": project_id,
        }
        defaults.update(kwargs)
        article = Article(**defaults)
        session.add(article)
        session.commit()
        session.refresh(article)
        return article

    return _create_article


@pytest.fixture
def a_criterion(session):
    """Factory fixture to create criteria."""

    def _create_criterion(project_id, **kwargs):
        defaults = {
            "type": CriterionType.inclusion,
            "code": "I1",
            "description": "Test inclusion criterion",
            "rationale": "This is a test rationale",
            "is_active": True,
            "project_id": project_id,
        }
        defaults.update(kwargs)
        criterion = Criterion(**defaults)
        session.add(criterion)
        session.commit()
        session.refresh(criterion)
        return criterion

    return _create_criterion


def test_screen_single_article_success(
    auth_as, a_project, a_article, a_criterion, monkeypatch
):
    """Test successful AI screening of a single article."""
    client, user = auth_as()
    project = a_project(user)
    project.review_question = "What is the effect of intervention X?"
    article = a_article(project.id)
    a_criterion(project.id)

    # Mock the screen_article function
    async def mock_screen_article(
        article, criteria, review_question, session, reviewer_id=None
    ):
        decision = ScreeningDecision(
            article_id=article.id,
            reviewer_id=reviewer_id,
            stage=ScreeningStage.title_abstract,
            decision=ScreeningDecisionType.include,
            source=DecisionSource.ai_agent,
            confidence_score=0.85,
            reasoning="Article meets all inclusion criteria",
            criteria_evaluations={
                "I1": {"met": True, "confidence": 0.85, "reasoning": "Test"}
            },
        )
        session.add(decision)
        session.commit()
        session.refresh(decision)
        return decision

    monkeypatch.setattr(
        "app.features.screening.routers.screen_article",
        mock_screen_article,
    )

    res = client.post(
        f"{BASE_API}/{project.id}/screening/articles/{article.id}/screen-ai"
    )

    assert res.status_code == 200
    result = res.json()
    assert result["decision"] == "include"
    assert result["confidence_score"] == 0.85
    assert result["source"] == "ai_agent"


def test_screen_single_article_no_criteria(auth_as, a_project, a_article):
    """Test that screening without criteria returns an error."""
    client, user = auth_as()
    project = a_project(user)
    article = a_article(project.id)

    res = client.post(
        f"{BASE_API}/{project.id}/screening/articles/{article.id}/screen-ai"
    )

    assert res.status_code == 400
    assert "No active criteria" in res.json()["detail"]


def test_screen_single_article_not_found(auth_as, a_project):
    """Test screening a non-existent article returns 404."""
    client, user = auth_as()
    project = a_project(user)

    res = client.post(f"{BASE_API}/{project.id}/screening/articles/99999/screen-ai")

    assert res.status_code == 404
    assert "Article not found" in res.json()["detail"]


def test_screen_single_article_wrong_project(
    auth_as, a_project, a_article, a_criterion
):
    """Test screening an article from a different project returns 404."""
    client, user = auth_as()
    project1 = a_project(user)
    project2 = a_project(user)
    article = a_article(project2.id)
    a_criterion(project1.id)

    res = client.post(
        f"{BASE_API}/{project1.id}/screening/articles/{article.id}/screen-ai"
    )

    assert res.status_code == 404
    assert "Article not found" in res.json()["detail"]


def test_screen_single_article_unauthorized(
    client, a_project, a_article, a_user, a_criterion
):
    """Test that unauthenticated users cannot screen articles."""
    user = a_user()
    project = a_project(user)
    article = a_article(project.id)
    a_criterion(project.id)

    res = client.post(
        f"{BASE_API}/{project.id}/screening/articles/{article.id}/screen-ai"
    )

    assert res.status_code == 401


def test_screen_single_article_wrong_owner(
    auth_as, a_project, a_user, a_article, a_criterion
):
    """Test that users cannot screen articles in projects they don't own."""
    client, user = auth_as()
    other_user = a_user()
    project = a_project(other_user)
    article = a_article(project.id)
    a_criterion(project.id)

    res = client.post(
        f"{BASE_API}/{project.id}/screening/articles/{article.id}/screen-ai"
    )

    assert res.status_code == 403


def test_get_ai_decision_success(auth_as, a_project, a_article, session):
    """Test retrieving an existing AI decision."""
    client, user = auth_as()
    project = a_project(user)
    article = a_article(project.id)

    # Create an AI decision
    decision = ScreeningDecision(
        article_id=article.id,
        stage=ScreeningStage.title_abstract,
        decision=ScreeningDecisionType.include,
        source=DecisionSource.ai_agent,
        confidence_score=0.9,
        reasoning="Test reasoning",
    )
    session.add(decision)
    session.commit()

    res = client.get(
        f"{BASE_API}/{project.id}/screening/articles/{article.id}/ai-decision"
    )

    assert res.status_code == 200
    result = res.json()
    assert result["decision"] == "include"
    assert result["confidence_score"] == 0.9
    assert result["source"] == "ai_agent"


def test_get_ai_decision_not_found(auth_as, a_project, a_article):
    """Test retrieving AI decision when none exists returns 404."""
    client, user = auth_as()
    project = a_project(user)
    article = a_article(project.id)

    res = client.get(
        f"{BASE_API}/{project.id}/screening/articles/{article.id}/ai-decision"
    )

    assert res.status_code == 404
    assert "No AI decision found" in res.json()["detail"]


def test_get_ai_decision_only_returns_ai_decisions(
    auth_as, a_project, a_article, session
):
    """Test that get_ai_decision only returns AI decisions, not human ones."""
    client, user = auth_as()
    project = a_project(user)
    article = a_article(project.id)

    # Create a human decision
    human_decision = ScreeningDecision(
        article_id=article.id,
        reviewer_id=user.id,
        stage=ScreeningStage.title_abstract,
        decision=ScreeningDecisionType.exclude,
        source=DecisionSource.human,
        reasoning="Human reasoning",
    )
    session.add(human_decision)
    session.commit()

    res = client.get(
        f"{BASE_API}/{project.id}/screening/articles/{article.id}/ai-decision"
    )

    assert res.status_code == 404
    assert "No AI decision found" in res.json()["detail"]


def test_batch_ai_screening_success(auth_as, a_project, a_article, a_criterion):
    """Test batch AI screening endpoint returns immediately."""
    client, user = auth_as()
    project = a_project(user)
    project.review_question = "What is the effect of intervention X?"

    # Create multiple articles
    a_article(project.id, title="Article 1")
    a_article(project.id, title="Article 2")
    a_article(project.id, title="Article 3")
    a_criterion(project.id)

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai")

    assert res.status_code == 200
    result = res.json()
    assert result["message"] == "AI screening started"
    assert result["article_count"] == 3


def test_batch_ai_screening_no_eligible_articles(
    auth_as, a_project, a_article, a_criterion, session
):
    """Test batch screening when all articles already have AI decisions."""
    client, user = auth_as()
    project = a_project(user)
    article = a_article(project.id)
    a_criterion(project.id)

    # Create an AI decision for the article
    decision = ScreeningDecision(
        article_id=article.id,
        stage=ScreeningStage.title_abstract,
        decision=ScreeningDecisionType.include,
        source=DecisionSource.ai_agent,
        confidence_score=0.9,
    )
    session.add(decision)
    session.commit()

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai")

    assert res.status_code == 200
    result = res.json()
    assert result["message"] == "No eligible articles to screen"
    assert result["article_count"] == 0


def test_batch_ai_screening_with_limit(auth_as, a_project, a_article, a_criterion):
    """Test batch screening with limit parameter."""
    client, user = auth_as()
    project = a_project(user)

    # Create 5 articles
    for i in range(5):
        a_article(project.id, title=f"Article {i + 1}")
    a_criterion(project.id)

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai?limit=2")

    assert res.status_code == 200
    result = res.json()
    assert result["message"] == "AI screening started"
    assert result["article_count"] == 2


def test_batch_ai_screening_with_stage_filter(
    auth_as, a_project, a_article, a_criterion
):
    """Test batch screening with stage filter."""
    client, user = auth_as()
    project = a_project(user)

    # Create articles at different stages
    a_article(
        project.id,
        title="Title/Abstract Article",
        current_stage=ScreeningStage.title_abstract,
    )
    a_article(
        project.id,
        title="Full Text Article",
        current_stage=ScreeningStage.full_text,
        status=ArticleStatus.full_text_retrieved,
    )
    a_criterion(project.id)

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai?stage=title_abstract")

    assert res.status_code == 200
    result = res.json()
    assert result["message"] == "AI screening started"
    assert result["article_count"] == 1


def test_batch_ai_screening_no_criteria(auth_as, a_project, a_article):
    """Test batch screening without criteria returns an error."""
    client, user = auth_as()
    project = a_project(user)
    a_article(project.id)

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai")

    assert res.status_code == 400
    assert "No active criteria" in res.json()["detail"]


def test_batch_ai_screening_only_active_criteria(
    auth_as, a_project, a_article, a_criterion
):
    """Test that batch screening only uses active criteria."""
    client, user = auth_as()
    project = a_project(user)
    a_article(project.id)

    # Create active and inactive criteria
    a_criterion(project.id, code="I1", is_active=True)
    a_criterion(project.id, code="I2", is_active=False)

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai")

    assert res.status_code == 200
    result = res.json()
    assert result["article_count"] == 1


def test_batch_schedules_flow_with_primitive_ids_only(
    auth_as, a_project, a_article, a_criterion, _ai_configured
):
    """The flow gets ids only: no request-scoped session or ORM objects."""
    client, user = auth_as()
    project = a_project(user)
    project.review_question = "Q?"
    a1 = a_article(project.id, title="A1")
    a2 = a_article(project.id, title="A2")
    a_criterion(project.id)

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai")

    assert res.status_code == 200
    _ai_configured.assert_awaited_once()
    args = _ai_configured.await_args
    values = list(args.args) + list(args.kwargs.values())
    assert all(isinstance(v, (int, str, list)) for v in values)
    assert project.id in values
    assert user.id in values
    assert [a1.id, a2.id] in values


def test_batch_eligibility_ignores_ai_decision_at_other_stage(
    auth_as, a_project, a_article, a_criterion, session
):
    client, user = auth_as()
    project = a_project(user)
    article = a_article(project.id, current_stage=ScreeningStage.title_abstract)
    a_criterion(project.id)
    session.add(
        ScreeningDecision(
            article_id=article.id,
            stage=ScreeningStage.full_text,
            decision=ScreeningDecisionType.include,
            source=DecisionSource.ai_agent,
        )
    )
    # A human decision at the same stage must not count either
    session.add(
        ScreeningDecision(
            article_id=article.id,
            stage=ScreeningStage.title_abstract,
            decision=ScreeningDecisionType.include,
            source=DecisionSource.human,
        )
    )
    session.commit()

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai")
    assert res.json()["article_count"] == 1


def test_batch_skips_full_text_stage_articles_without_content(
    auth_as, a_project, a_article, a_criterion
):
    client, user = auth_as()
    project = a_project(user)
    a_criterion(project.id)
    a_article(
        project.id,
        current_stage=ScreeningStage.full_text,
        status=ArticleStatus.full_text_retrieved,
    )
    with_text = a_article(
        project.id,
        current_stage=ScreeningStage.full_text,
        status=ArticleStatus.full_text_retrieved,
        full_text_content="text",
    )

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai")
    assert res.json()["article_count"] == 1
    assert with_text.id


def test_batch_returns_503_when_not_configured(
    auth_as, a_project, a_article, a_criterion, monkeypatch
):
    monkeypatch.setattr(
        "app.features.research.agent.get_settings",
        lambda: Settings(_env_file=None, secret_key="x", anthropic_api_key=None),
    )
    client, user = auth_as()
    project = a_project(user)
    a_article(project.id)
    a_criterion(project.id)
    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai")
    assert res.status_code == 503
    assert "not configured" in res.json()["detail"]


def test_screen_ai_error_does_not_leak_details(
    auth_as, a_project, a_article, a_criterion, monkeypatch, caplog
):
    client, user = auth_as()
    project = a_project(user)
    article = a_article(project.id)
    a_criterion(project.id)

    async def boom(**kwargs):
        raise RuntimeError("secret-internal-detail sk-ant-123")

    monkeypatch.setattr("app.features.screening.routers.screen_article", boom)
    with caplog.at_level("ERROR"):
        res = client.post(
            f"{BASE_API}/{project.id}/screening/articles/{article.id}/screen-ai"
        )
    assert res.status_code == 500
    assert "secret-internal-detail" not in res.text
    assert "sk-ant-123" not in res.text
    assert "secret-internal-detail" in caplog.text  # logged server-side


def test_screen_ai_returns_503_when_not_configured(
    auth_as, a_project, a_article, a_criterion, monkeypatch
):
    monkeypatch.setattr(
        "app.features.research.agent.get_settings",
        lambda: Settings(_env_file=None, secret_key="x", anthropic_api_key=None),
    )
    client, user = auth_as()
    project = a_project(user)
    article = a_article(project.id)
    a_criterion(project.id)
    res = client.post(
        f"{BASE_API}/{project.id}/screening/articles/{article.id}/screen-ai"
    )
    assert res.status_code == 503
    assert res.json()["detail"] == "AI screening is not configured"


# --- run-ai with an explicit article subset (screening-view lookahead) ---------


def _run_ai_subset(client, project_id, ids, **params):
    return client.post(
        f"{BASE_API}/{project_id}/screening/run-ai",
        json={"article_ids": ids},
        params=params,
    )


def test_subset_screens_only_requested_articles(
    auth_as, a_project, a_article, a_criterion, _ai_configured
):
    client, user = auth_as()
    project = a_project(user)
    a_criterion(project.id)
    arts = [a_article(project.id, title=f"A{i}") for i in range(5)]
    wanted = [arts[3].id, arts[1].id, arts[2].id]

    res = _run_ai_subset(client, project.id, wanted)

    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "AI screening started"
    assert body["article_count"] == 3
    assert body["article_ids"] == sorted(wanted)
    _ai_configured.assert_awaited_once()
    args = _ai_configured.await_args.args
    assert args[0] == project.id
    assert args[1] == sorted(wanted)
    assert args[2] == user.id
    assert args[3] is True  # targeted: events are tagged for the UI


def test_subset_skips_ineligible_foreign_and_screened_ids(
    auth_as, a_project, a_article, a_criterion, session, _ai_configured
):
    client, user = auth_as()
    project = a_project(user)
    other = a_project(user)
    a_criterion(project.id)
    ok = a_article(project.id, title="ok")
    screened = a_article(project.id, title="screened")
    session.add(
        ScreeningDecision(
            article_id=screened.id,
            stage=ScreeningStage.title_abstract,
            decision=ScreeningDecisionType.include,
            source=DecisionSource.ai_agent,
        )
    )
    session.commit()
    imported = a_article(project.id, title="imported", status=ArticleStatus.imported)
    no_text = a_article(
        project.id,
        title="no text",
        current_stage=ScreeningStage.full_text,
        status=ArticleStatus.full_text_retrieved,
    )
    foreign = a_article(other.id, title="foreign")

    res = _run_ai_subset(
        client,
        project.id,
        [ok.id, screened.id, imported.id, no_text.id, foreign.id, 999_999],
    )

    assert res.status_code == 200
    assert res.json()["article_ids"] == [ok.id]
    assert _ai_configured.await_args.args[1] == [ok.id]


def test_subset_with_nothing_eligible_returns_zero(
    auth_as, a_project, a_article, a_criterion, _ai_configured
):
    client, user = auth_as()
    project = a_project(user)
    other = a_project(user)
    a_criterion(project.id)
    foreign = a_article(other.id)

    res = _run_ai_subset(client, project.id, [foreign.id])

    assert res.status_code == 200
    assert res.json() == {
        "message": "No eligible articles to screen",
        "article_count": 0,
        "article_ids": [],
    }
    _ai_configured.assert_not_awaited()


def test_subset_skips_articles_already_in_flight(
    auth_as, a_project, a_article, a_criterion, _ai_configured
):
    client, user = auth_as()
    project = a_project(user)
    a_criterion(project.id)
    busy = a_article(project.id, title="busy")
    free = a_article(project.id, title="free")
    # A running batch (lookahead or manual) has `busy` queued at this stage
    inflight.claim([(project.id, busy.id, ScreeningStage.title_abstract.value)])

    res = _run_ai_subset(client, project.id, [busy.id, free.id])

    assert res.json()["article_ids"] == [free.id]
    # The other batch's claim is left alone
    assert inflight.is_in_flight(
        (project.id, busy.id, ScreeningStage.title_abstract.value)
    )


def test_full_batch_also_skips_in_flight_articles(
    auth_as, a_project, a_article, a_criterion
):
    client, user = auth_as()
    project = a_project(user)
    a_criterion(project.id)
    busy = a_article(project.id, title="busy")
    a_article(project.id, title="free")
    inflight.claim([(project.id, busy.id, ScreeningStage.title_abstract.value)])

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai")

    assert res.json()["article_count"] == 1
    assert busy.id not in res.json()["article_ids"]


def test_overlapping_requests_do_not_queue_twice(
    auth_as, a_project, a_article, a_criterion, _ai_configured, monkeypatch
):
    """While the first batch still runs, a second request skips its articles."""
    client, user = auth_as()
    project = a_project(user)
    a_criterion(project.id)
    a1 = a_article(project.id, title="A1")
    a2 = a_article(project.id, title="A2")
    a3 = a_article(project.id, title="A3")
    second: dict = {}

    async def first_flow(project_id, article_ids, user_id, targeted=False):
        # Runs as the first request's background task: its claims are still held
        second["res"] = _run_ai_subset(client, project.id, [a1.id, a2.id, a3.id])

    monkeypatch.setattr(
        "app.features.screening.routers.batch_ai_screening_flow", first_flow
    )
    res = _run_ai_subset(client, project.id, [a1.id, a2.id])

    assert res.json()["article_ids"] == [a1.id, a2.id]
    assert second["res"].json()["article_ids"] == [a3.id]
    # Everything is released once the flows finished
    for a in (a1, a2, a3):
        key = (project.id, a.id, ScreeningStage.title_abstract.value)
        assert not inflight.is_in_flight(key)


def test_claims_released_after_flow(auth_as, a_project, a_article, a_criterion):
    client, user = auth_as()
    project = a_project(user)
    a_criterion(project.id)
    art = a_article(project.id)

    assert _run_ai_subset(client, project.id, [art.id]).json()["article_count"] == 1
    assert not inflight.is_in_flight(
        (project.id, art.id, ScreeningStage.title_abstract.value)
    )
    # ...so the article can be queued again (it still has no AI decision)
    assert _run_ai_subset(client, project.id, [art.id]).json()["article_count"] == 1


@pytest.mark.asyncio
async def test_claims_released_when_flow_fails():
    key = (1, 2, ScreeningStage.title_abstract.value)
    assert inflight.claim([key]) == [key]
    boom = AsyncMock(side_effect=RuntimeError("model down"))

    with pytest.raises(RuntimeError):
        await _run_batch_and_release([key], boom, 1, [2], 3, True)

    assert not inflight.is_in_flight(key)


def test_claims_released_when_scheduling_fails(
    auth_as, a_project, a_article, a_criterion, monkeypatch
):
    client, user = auth_as()
    project = a_project(user)
    a_criterion(project.id)
    art = a_article(project.id)

    def broken(*args, **kwargs):
        raise RuntimeError("audit down")

    monkeypatch.setattr("app.features.screening.routers.audit.record_event", broken)
    with pytest.raises(RuntimeError):
        _run_ai_subset(client, project.id, [art.id])
    assert not inflight.is_in_flight(
        (project.id, art.id, ScreeningStage.title_abstract.value)
    )


def test_subset_respects_stage_filter(auth_as, a_project, a_article, a_criterion):
    client, user = auth_as()
    project = a_project(user)
    a_criterion(project.id)
    ta = a_article(project.id)
    ft = a_article(
        project.id,
        current_stage=ScreeningStage.full_text,
        status=ArticleStatus.full_text_retrieved,
        full_text_content="text",
    )

    res = _run_ai_subset(client, project.id, [ta.id, ft.id], stage="full_text")

    assert res.json()["article_ids"] == [ft.id]


def test_subset_too_many_or_empty_ids_rejected(auth_as, a_project, a_criterion):
    client, user = auth_as()
    project = a_project(user)
    a_criterion(project.id)

    assert _run_ai_subset(client, project.id, list(range(1, 12))).status_code == 422
    assert _run_ai_subset(client, project.id, []).status_code == 422


def test_subset_without_criteria_returns_400(auth_as, a_project, a_article):
    client, user = auth_as()
    project = a_project(user)
    art = a_article(project.id)

    res = _run_ai_subset(client, project.id, [art.id])

    assert res.status_code == 400
    assert "No active criteria" in res.json()["detail"]
    assert not inflight.is_in_flight(
        (project.id, art.id, ScreeningStage.title_abstract.value)
    )


def test_subset_returns_503_when_not_configured(
    auth_as, a_project, a_article, a_criterion, monkeypatch
):
    monkeypatch.setattr(
        "app.features.research.agent.get_settings",
        lambda: Settings(_env_file=None, secret_key="x", anthropic_api_key=None),
    )
    client, user = auth_as()
    project = a_project(user)
    art = a_article(project.id)
    a_criterion(project.id)

    res = _run_ai_subset(client, project.id, [art.id])

    assert res.status_code == 503
    assert "not configured" in res.json()["detail"]


def test_subset_requires_reviewer_role(auth_as, a_project, a_article, a_criterion):
    owner_client, owner = auth_as()
    project = a_project(owner)
    a_criterion(project.id)
    art = a_article(project.id)
    stranger_client, _ = auth_as()

    res = _run_ai_subset(stranger_client, project.id, [art.id])

    assert res.status_code in (403, 404)
