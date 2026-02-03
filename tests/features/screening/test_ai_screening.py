"""Tests for AI screening endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.features.research.models import Article, ArticleStatus, ScreeningStage
from app.features.criteria.models import Criterion, CriterionType
from app.features.screening.models import (
    ScreeningDecision,
    ScreeningDecisionType,
    DecisionSource,
)

BASE_API = "api/v1/projects"


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


def test_screen_single_article_success(auth_as, a_project, a_article, a_criterion, monkeypatch):
    """Test successful AI screening of a single article."""
    client, user = auth_as()
    project = a_project(user)
    project.review_question = "What is the effect of intervention X?"
    article = a_article(project.id)
    criterion = a_criterion(project.id)

    # Mock the screen_article function
    async def mock_screen_article(article, criteria, review_question, session, reviewer_id=None):
        decision = ScreeningDecision(
            article_id=article.id,
            reviewer_id=reviewer_id,
            stage=ScreeningStage.title_abstract,
            decision=ScreeningDecisionType.include,
            source=DecisionSource.ai_agent,
            confidence_score=0.85,
            reasoning="Article meets all inclusion criteria",
            criteria_evaluations={"I1": {"met": True, "confidence": 0.85, "reasoning": "Test"}},
        )
        session.add(decision)
        session.commit()
        session.refresh(decision)
        return decision

    monkeypatch.setattr(
        "app.features.screening.routers.screen_article",
        mock_screen_article,
    )

    res = client.post(f"{BASE_API}/{project.id}/screening/articles/{article.id}/screen-ai")

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

    res = client.post(f"{BASE_API}/{project.id}/screening/articles/{article.id}/screen-ai")

    assert res.status_code == 400
    assert "No active criteria" in res.json()["detail"]


def test_screen_single_article_not_found(auth_as, a_project):
    """Test screening a non-existent article returns 404."""
    client, user = auth_as()
    project = a_project(user)

    res = client.post(f"{BASE_API}/{project.id}/screening/articles/99999/screen-ai")

    assert res.status_code == 404
    assert "Article not found" in res.json()["detail"]


def test_screen_single_article_wrong_project(auth_as, a_project, a_article, a_criterion):
    """Test screening an article from a different project returns 404."""
    client, user = auth_as()
    project1 = a_project(user)
    project2 = a_project(user)
    article = a_article(project2.id)
    a_criterion(project1.id)

    res = client.post(f"{BASE_API}/{project1.id}/screening/articles/{article.id}/screen-ai")

    assert res.status_code == 404
    assert "Article not found" in res.json()["detail"]


def test_screen_single_article_unauthorized(client, a_project, a_article, a_user, a_criterion):
    """Test that unauthenticated users cannot screen articles."""
    user = a_user()
    project = a_project(user)
    article = a_article(project.id)
    a_criterion(project.id)

    res = client.post(f"{BASE_API}/{project.id}/screening/articles/{article.id}/screen-ai")

    assert res.status_code == 401


def test_screen_single_article_wrong_owner(auth_as, a_project, a_user, a_article, a_criterion):
    """Test that users cannot screen articles in projects they don't own."""
    client, user = auth_as()
    other_user = a_user()
    project = a_project(other_user)
    article = a_article(project.id)
    a_criterion(project.id)

    res = client.post(f"{BASE_API}/{project.id}/screening/articles/{article.id}/screen-ai")

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

    res = client.get(f"{BASE_API}/{project.id}/screening/articles/{article.id}/ai-decision")

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

    res = client.get(f"{BASE_API}/{project.id}/screening/articles/{article.id}/ai-decision")

    assert res.status_code == 404
    assert "No AI decision found" in res.json()["detail"]


def test_get_ai_decision_only_returns_ai_decisions(auth_as, a_project, a_article, session):
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

    res = client.get(f"{BASE_API}/{project.id}/screening/articles/{article.id}/ai-decision")

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


def test_batch_ai_screening_no_eligible_articles(auth_as, a_project, a_article, a_criterion, session):
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
        a_article(project.id, title=f"Article {i+1}")
    a_criterion(project.id)

    res = client.post(f"{BASE_API}/{project.id}/screening/run-ai?limit=2")

    assert res.status_code == 200
    result = res.json()
    assert result["message"] == "AI screening started"
    assert result["article_count"] == 2


def test_batch_ai_screening_with_stage_filter(auth_as, a_project, a_article, a_criterion):
    """Test batch screening with stage filter."""
    client, user = auth_as()
    project = a_project(user)

    # Create articles at different stages
    a_article(project.id, title="Title/Abstract Article", current_stage=ScreeningStage.title_abstract)
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


def test_batch_ai_screening_only_active_criteria(auth_as, a_project, a_article, a_criterion):
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
