"""
E2E integration tests for the screening workflow.

Tests the complete screening flow from article creation through decision-making,
covering title/abstract screening, full-text screening, and statistics tracking.
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import get_settings
from app.features.research.models import Article, ArticleStatus, FinalDecision
from app.features.screening.models import (
    ScreeningStage,
)

settings = get_settings()
API = settings.api_prefix


@pytest.mark.e2e
def test_screening_stats_empty_project(client: TestClient, auth_as, a_project):
    """
    Verify that screening stats for a new project with no articles show zeros.

    Tests that the stats endpoint correctly reports zero for all metrics when
    a project has no articles.
    """
    # Arrange
    authed_client, user = auth_as()
    project = a_project(user)

    # Act
    response = authed_client.get(f"{API}/projects/{project.id}/screening/stats")

    # Assert
    assert response.status_code == 200
    stats = response.json()
    assert stats["total_articles"] == 0
    assert stats["screened_title_abstract"] == 0
    assert stats["screened_full_text"] == 0
    assert stats["included"] == 0
    assert stats["excluded"] == 0
    assert stats["uncertain"] == 0
    assert stats["awaiting_screening"] == 0
    assert stats["awaiting_full_text"] == 0


@pytest.mark.e2e
def test_title_abstract_include_flow(
    client: TestClient, session: Session, screening_ready_project
):
    """
    Test complete flow of including an article at title/abstract stage.

    Verifies that when an article is included during title/abstract screening:
    - Article status transitions to awaiting_full_text
    - Article stage transitions to full_text
    - Decision is recorded and retrievable
    - Statistics are updated correctly
    """
    # Arrange
    project, user, articles, criteria = screening_ready_project()
    token = _get_token(user)
    client.headers["Authorization"] = f"Bearer {token}"

    # Act - Get next article to screen
    response = client.get(
        f"{API}/projects/{project.id}/screening/next",
        params={"stage": "title_abstract"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["article"] is not None
    article_id = data["article"]["id"]

    # Act - Include the article
    decision_payload = {
        "stage": "title_abstract",
        "decision": "include",
        "source": "human",
        "confidence_score": 0.9,
        "reasoning": "Meets all inclusion criteria for title/abstract stage",
    }
    decision_response = client.post(
        f"{API}/projects/{project.id}/screening/articles/{article_id}/decisions",
        json=decision_payload,
    )

    # Assert - Decision created successfully
    assert decision_response.status_code == 201

    # Assert - Article status updated
    session.expire_all()
    article = session.get(Article, article_id)
    assert article.status == ArticleStatus.awaiting_full_text
    assert article.current_stage == ScreeningStage.full_text

    # Assert - Decision retrievable via decisions list
    decisions_response = client.get(
        f"{API}/projects/{project.id}/screening/articles/{article_id}/decisions"
    )
    assert decisions_response.status_code == 200
    decisions_data = decisions_response.json()
    assert decisions_data["meta"]["pagination"]["total_items"] == 1
    assert decisions_data["data"][0]["decision"] == "include"

    # Assert - Stats updated
    stats_response = client.get(f"{API}/projects/{project.id}/screening/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["total_articles"] == 3
    assert stats["screened_title_abstract"] == 1
    assert stats["awaiting_full_text"] == 1


@pytest.mark.e2e
def test_title_abstract_exclude_flow(
    client: TestClient, session: Session, screening_ready_project
):
    """
    Test complete flow of excluding an article at title/abstract stage.

    Verifies that when an article is excluded during title/abstract screening:
    - Article status transitions to excluded
    - Article stage transitions to completed
    - Final decision is set to excluded
    - Statistics reflect the exclusion
    """
    # Arrange
    project, user, articles, criteria = screening_ready_project()
    token = _get_token(user)
    client.headers["Authorization"] = f"Bearer {token}"

    # Act - Get next article
    response = client.get(
        f"{API}/projects/{project.id}/screening/next",
        params={"stage": "title_abstract"}
    )
    assert response.status_code == 200
    article_id = response.json()["article"]["id"]

    # Act - Exclude the article
    decision_payload = {
        "stage": "title_abstract",
        "decision": "exclude",
        "source": "human",
        "reasoning": "Non-English language",
        "primary_exclusion_reason": "E1",
    }
    decision_response = client.post(
        f"{API}/projects/{project.id}/screening/articles/{article_id}/decisions",
        json=decision_payload,
    )

    # Assert - Decision created
    assert decision_response.status_code == 201

    # Assert - Article status updated correctly
    session.expire_all()
    article = session.get(Article, article_id)
    assert article.status == ArticleStatus.excluded
    assert article.current_stage == ScreeningStage.completed
    assert article.final_decision == FinalDecision.excluded

    # Assert - Stats reflect exclusion
    stats_response = client.get(f"{API}/projects/{project.id}/screening/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["excluded"] == 1
    assert stats["screened_title_abstract"] == 1


@pytest.mark.e2e
def test_title_abstract_uncertain_flow(
    client: TestClient, session: Session, screening_ready_project
):
    """
    Test uncertain decision flow at title/abstract stage.

    Verifies that when an article is marked as uncertain:
    - Article remains in screening status (not moved forward)
    - Article can be retrieved again as "next" article
    - Decision is recorded for tracking purposes
    """
    # Arrange
    project, user, articles, criteria = screening_ready_project()
    token = _get_token(user)
    client.headers["Authorization"] = f"Bearer {token}"

    # Act - Get next article
    first_response = client.get(
        f"{API}/projects/{project.id}/screening/next",
        params={"stage": "title_abstract"}
    )
    assert first_response.status_code == 200
    first_article_id = first_response.json()["article"]["id"]

    # Act - Mark as uncertain
    decision_payload = {
        "stage": "title_abstract",
        "decision": "uncertain",
        "source": "human",
        "reasoning": "Unclear if inclusion criteria are met from abstract alone",
    }
    decision_response = client.post(
        f"{API}/projects/{project.id}/screening/articles/{first_article_id}/decisions",
        json=decision_payload,
    )

    # Assert - Decision created
    assert decision_response.status_code == 201

    # Assert - Article still in screening status
    session.expire_all()
    article = session.get(Article, first_article_id)
    assert article.status == ArticleStatus.screening
    assert article.current_stage == ScreeningStage.title_abstract

    # Assert - Articles still available for screening (uncertain doesn't remove from queue)
    second_response = client.get(
        f"{API}/projects/{project.id}/screening/next",
        params={"stage": "title_abstract"}
    )
    assert second_response.status_code == 200
    assert second_response.json()["article"] is not None


@pytest.mark.e2e
def test_full_text_screening_flow(
    client: TestClient, session: Session, an_article, a_project, auth_as, a_criterion
):
    """
    Test screening an article at full-text stage.

    Verifies that when an article at full-text stage is included:
    - Article status transitions to included
    - Article stage transitions to completed
    - Final decision is set to included
    """
    # Arrange
    authed_client, user = auth_as()
    project = a_project(user)

    # Create criteria
    a_criterion(project.id, code="I1", description="Inclusion criterion 1")
    a_criterion(project.id, code="E1", description="Exclusion criterion 1")

    # Create article ready for full-text screening
    article = an_article(
        project.id,
        status=ArticleStatus.full_text_retrieved,
        stage=ScreeningStage.full_text,
    )

    # Act - Include at full-text stage
    decision_payload = {
        "stage": "full_text",
        "decision": "include",
        "source": "human",
        "confidence_score": 0.95,
        "reasoning": "All inclusion criteria met after full-text review",
    }
    decision_response = authed_client.post(
        f"{API}/projects/{project.id}/screening/articles/{article.id}/decisions",
        json=decision_payload,
    )

    # Assert - Decision created
    assert decision_response.status_code == 201

    # Assert - Article moved to final included state
    session.expire_all()
    updated_article = session.get(Article, article.id)
    assert updated_article.status == ArticleStatus.included
    assert updated_article.current_stage == ScreeningStage.completed
    assert updated_article.final_decision == FinalDecision.included


@pytest.mark.e2e
def test_complete_screening_pipeline(
    client: TestClient, session: Session, screening_ready_project
):
    """
    Test complete screening pipeline with multiple articles and decision types.

    Creates a scenario with multiple articles and screens them with different
    decisions to verify that all status transitions work correctly and statistics
    accurately reflect the screening progress.
    """
    # Arrange
    project, user, articles, criteria = screening_ready_project(article_count=5)
    token = _get_token(user)
    client.headers["Authorization"] = f"Bearer {token}"

    # Act - Screen first article: include at title/abstract
    response1 = client.get(
        f"{API}/projects/{project.id}/screening/next",
        params={"stage": "title_abstract"}
    )
    article1_id = response1.json()["article"]["id"]
    client.post(
        f"{API}/projects/{project.id}/screening/articles/{article1_id}/decisions",
        json={
            "stage": "title_abstract",
            "decision": "include",
            "source": "human",
        },
    )

    # Act - Screen second article: exclude at title/abstract
    response2 = client.get(
        f"{API}/projects/{project.id}/screening/next",
        params={"stage": "title_abstract"}
    )
    article2_id = response2.json()["article"]["id"]
    client.post(
        f"{API}/projects/{project.id}/screening/articles/{article2_id}/decisions",
        json={
            "stage": "title_abstract",
            "decision": "exclude",
            "source": "human",
            "primary_exclusion_reason": "E1",
        },
    )

    # Assert - Verify final stats
    stats_response = client.get(f"{API}/projects/{project.id}/screening/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()

    assert stats["total_articles"] == 5
    assert stats["screened_title_abstract"] == 2
    assert stats["excluded"] == 1
    assert stats["awaiting_full_text"] == 1
    assert stats["awaiting_screening"] == 3  # 3 articles still not screened

    # Assert - Verify article states
    session.expire_all()
    article1 = session.get(Article, article1_id)
    assert article1.status == ArticleStatus.awaiting_full_text

    article2 = session.get(Article, article2_id)
    assert article2.status == ArticleStatus.excluded
    assert article2.final_decision == FinalDecision.excluded


@pytest.mark.e2e
def test_get_next_article_none_remaining(
    client: TestClient, screening_ready_project
):
    """
    Test get next article when all articles have been screened.

    Verifies that when all articles have been screened, the next endpoint
    returns null for the article with an appropriate message.
    """
    # Arrange
    project, user, articles, criteria = screening_ready_project(article_count=2)
    token = _get_token(user)
    client.headers["Authorization"] = f"Bearer {token}"

    # Act - Screen all articles
    for _ in range(2):
        response = client.get(
            f"{API}/projects/{project.id}/screening/next",
            params={"stage": "title_abstract"}
        )
        article_id = response.json()["article"]["id"]
        client.post(
            f"{API}/projects/{project.id}/screening/articles/{article_id}/decisions",
            json={
                "stage": "title_abstract",
                "decision": "exclude",
                "source": "human",
            },
        )

    # Act - Try to get next article
    response = client.get(
        f"{API}/projects/{project.id}/screening/next",
        params={"stage": "title_abstract"}
    )

    # Assert - No article available
    assert response.status_code == 200
    data = response.json()
    assert data["article"] is None
    assert "message" in data


@pytest.mark.e2e
def test_screening_ownership_isolation(
    client: TestClient, screening_ready_project, a_user, token_for
):
    """
    Test that screening endpoints enforce project ownership.

    Verifies that User B cannot access screening endpoints for User A's project,
    ensuring proper authorization and data isolation.
    """
    # Arrange - Create project for User A
    project, user_a, articles, criteria = screening_ready_project()

    # Arrange - Create User B and authenticate as them
    user_b = a_user()
    token_b = token_for(user_b)
    client.headers["Authorization"] = f"Bearer {token_b}"

    # Act & Assert - User B cannot access User A's screening stats
    stats_response = client.get(f"{API}/projects/{project.id}/screening/stats")
    assert stats_response.status_code == 403

    # Act & Assert - User B cannot get next article from User A's project
    next_response = client.get(
        f"{API}/projects/{project.id}/screening/next",
        params={"stage": "title_abstract"}
    )
    assert next_response.status_code == 403

    # Act & Assert - User B cannot create decisions for User A's articles
    article_id = articles[0].id
    decision_response = client.post(
        f"{API}/projects/{project.id}/screening/articles/{article_id}/decisions",
        json={
            "stage": "title_abstract",
            "decision": "include",
            "source": "human",
        },
    )
    assert decision_response.status_code == 403

    # Act & Assert - User B cannot view decisions for User A's articles
    decisions_response = client.get(
        f"{API}/projects/{project.id}/screening/articles/{article_id}/decisions"
    )
    assert decisions_response.status_code == 403


@pytest.mark.e2e
def test_multiple_decisions_per_article(
    client: TestClient, session: Session, screening_ready_project
):
    """
    Test that multiple decisions can be recorded for the same article.

    Verifies that an article can have multiple screening decisions (e.g., first
    uncertain, then include) and all decisions are properly recorded and retrievable.
    This is important for tracking the decision-making process and reviewer consensus.
    """
    # Arrange
    project, user, articles, criteria = screening_ready_project()
    token = _get_token(user)
    client.headers["Authorization"] = f"Bearer {token}"

    # Get an article to screen
    response = client.get(
        f"{API}/projects/{project.id}/screening/next",
        params={"stage": "title_abstract"}
    )
    article_id = response.json()["article"]["id"]

    # Act - Create first decision: uncertain
    decision1_payload = {
        "stage": "title_abstract",
        "decision": "uncertain",
        "source": "human",
        "reasoning": "Need more information",
    }
    decision1_response = client.post(
        f"{API}/projects/{project.id}/screening/articles/{article_id}/decisions",
        json=decision1_payload,
    )
    assert decision1_response.status_code == 201

    # Act - Create second decision: include (after review)
    decision2_payload = {
        "stage": "title_abstract",
        "decision": "include",
        "source": "human",
        "reasoning": "After further review, inclusion criteria are met",
        "confidence_score": 0.8,
    }
    decision2_response = client.post(
        f"{API}/projects/{project.id}/screening/articles/{article_id}/decisions",
        json=decision2_payload,
    )
    assert decision2_response.status_code == 201

    # Assert - Both decisions retrievable
    decisions_response = client.get(
        f"{API}/projects/{project.id}/screening/articles/{article_id}/decisions"
    )
    assert decisions_response.status_code == 200
    decisions_data = decisions_response.json()

    assert decisions_data["meta"]["pagination"]["total_items"] == 2
    decisions = decisions_data["data"]

    # Verify both decisions exist (order may vary depending on created_at)
    decision_types = {d["decision"] for d in decisions}
    assert "uncertain" in decision_types
    assert "include" in decision_types

    # Assert - Article status reflects most recent include decision
    session.expire_all()
    article = session.get(Article, article_id)
    assert article.status == ArticleStatus.awaiting_full_text
    assert article.current_stage == ScreeningStage.full_text


# Helper functions

def _get_token(user) -> str:
    """Generate access token for a user."""
    from app.features.auth.services import create_access_token
    return create_access_token(data={"sub": user.email})
