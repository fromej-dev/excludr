"""
End-to-end integration tests for the complete Excludr workflow.

These tests simulate a researcher's complete journey through the application,
from registration to screening decisions.
"""

import pytest
from faker import Faker
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import get_settings
from app.features.research.models import ArticleStatus, FinalDecision
from app.features.screening.models import ScreeningStage

settings = get_settings()
API = settings.api_prefix


@pytest.mark.e2e
def test_complete_researcher_workflow(
    client: TestClient,
    session: Session,
    faker: Faker,
    an_article,
):
    """
    Test the complete researcher workflow from registration to screening decisions.

    This test covers:
    - User registration and authentication
    - Project creation with review question
    - Adding inclusion and exclusion criteria
    - Article import and verification
    - Starting the screening process
    - Making screening decisions at title/abstract stage
    - Verifying status transitions and statistics
    """
    # Step 1: Register a new user
    user_email = faker.email()
    user_password = "TestPassword123!"
    user_name = faker.name()

    register_response = client.post(
        f"{API}/auth/register",
        json={
            "email": user_email,
            "name": user_name,
            "password": user_password,
        },
    )
    assert register_response.status_code == 201
    user_data = register_response.json()
    assert user_data["email"] == user_email
    assert user_data["name"] == user_name

    # Step 2: Login to get access token
    login_response = client.post(
        f"{API}/auth/token",
        data={
            "username": user_email,
            "password": user_password,
        },
    )
    assert login_response.status_code == 200
    token_data = login_response.json()
    access_token = token_data["access_token"]
    assert access_token is not None

    # Set authorization header for subsequent requests
    headers = {"Authorization": f"Bearer {access_token}"}

    # Step 3: Create a project with review question
    project_name = faker.catch_phrase()[:50]
    review_question = "What is the effect of exercise on mental health?"

    project_response = client.post(
        f"{API}/projects",
        json={
            "name": project_name,
            "description": "A systematic review of exercise interventions",
            "review_question": review_question,
        },
        headers=headers,
    )
    assert project_response.status_code == 201
    project = project_response.json()
    project_id = project["id"]
    assert project["name"] == project_name
    assert project["review_question"] == review_question

    # Step 4: Add criteria (2 inclusion, 2 exclusion)
    criteria_to_create = [
        {
            "type": "inclusion",
            "code": "I1",
            "description": "Population includes adults aged 18+",
            "rationale": "Focus on adult population",
            "order": 0,
        },
        {
            "type": "inclusion",
            "code": "I2",
            "description": "Study is a randomized controlled trial",
            "rationale": "Ensure high quality evidence",
            "order": 1,
        },
        {
            "type": "exclusion",
            "code": "E1",
            "description": "Non-English language publications",
            "rationale": "Resource constraints for translation",
            "order": 0,
        },
        {
            "type": "exclusion",
            "code": "E2",
            "description": "Animal studies only",
            "rationale": "Focus on human subjects",
            "order": 1,
        },
    ]

    created_criteria = []
    for criterion_data in criteria_to_create:
        criterion_response = client.post(
            f"{API}/projects/{project_id}/criteria",
            json=criterion_data,
            headers=headers,
        )
        assert criterion_response.status_code == 201
        criterion = criterion_response.json()
        assert criterion["code"] == criterion_data["code"]
        assert criterion["description"] == criterion_data["description"]
        created_criteria.append(criterion)

    assert len(created_criteria) == 4

    # Step 5: Create articles via fixture (5 articles in imported status)
    articles = []
    for i in range(5):
        article = an_article(
            project_id=project_id,
            status=ArticleStatus.imported,
            stage=ScreeningStage.title_abstract,
            title=f"Article {i+1}: {faker.sentence()}",
            abstract=faker.paragraph(nb_sentences=5),
        )
        articles.append(article)

    # Step 6: Verify articles appear in list endpoint
    articles_response = client.get(
        f"{API}/projects/{project_id}/articles",
        headers=headers,
    )
    assert articles_response.status_code == 200
    articles_data = articles_response.json()
    assert "data" in articles_data
    assert len(articles_data["data"]) == 5
    assert all(a["status"] == "imported" for a in articles_data["data"])

    # Step 7: Start screening
    start_screening_response = client.post(
        f"{API}/projects/{project_id}/articles/start-screening",
        headers=headers,
    )
    assert start_screening_response.status_code == 200
    start_data = start_screening_response.json()
    assert start_data["count"] == 5

    # Step 8: Verify article stats show all in screening
    stats_response = client.get(
        f"{API}/projects/{project_id}/articles/stats",
        headers=headers,
    )
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["total"] == 5
    assert stats["by_status"]["screening"] == 5

    # Step 9: Screen 3 articles at title_abstract stage
    # Include 2, exclude 1
    screening_decisions = [
        {
            "article_index": 0,
            "decision": "include",
            "reasoning": "Meets all inclusion criteria",
        },
        {
            "article_index": 1,
            "decision": "include",
            "reasoning": "RCT with adult population",
        },
        {
            "article_index": 2,
            "decision": "exclude",
            "reasoning": "Animal study only",
        },
    ]

    # Refresh articles from DB to get updated status
    from app.features.research.models import Article
    from sqlmodel import select

    for decision_data in screening_decisions:
        article = session.exec(
            select(Article)
            .where(Article.id == articles[decision_data["article_index"]].id)
        ).first()

        decision_response = client.post(
            f"{API}/projects/{project_id}/screening/articles/{article.id}/decisions",
            json={
                "stage": "title_abstract",
                "decision": decision_data["decision"],
                "source": "human",
                "confidence_score": 0.95,
                "reasoning": decision_data["reasoning"],
            },
            headers=headers,
        )
        assert decision_response.status_code == 201
        decision = decision_response.json()
        assert decision["decision"] == decision_data["decision"]
        assert decision["stage"] == "title_abstract"
        assert decision["source"] == "human"

    # Step 10: Verify screening stats are updated correctly
    screening_stats_response = client.get(
        f"{API}/projects/{project_id}/screening/stats",
        headers=headers,
    )
    assert screening_stats_response.status_code == 200
    screening_stats = screening_stats_response.json()
    assert screening_stats["total_articles"] == 5
    assert screening_stats["screened_title_abstract"] == 3

    # Step 11: Verify excluded article has final_decision = excluded and status = excluded
    excluded_article = session.exec(
        select(Article).where(Article.id == articles[2].id)
    ).first()
    assert excluded_article.final_decision == FinalDecision.excluded
    assert excluded_article.status == ArticleStatus.excluded
    assert excluded_article.current_stage == ScreeningStage.completed

    # Step 12: Verify included articles moved to awaiting_full_text
    for idx in [0, 1]:
        included_article = session.exec(
            select(Article).where(Article.id == articles[idx].id)
        ).first()
        assert included_article.status == ArticleStatus.awaiting_full_text
        assert included_article.current_stage == ScreeningStage.full_text
        assert included_article.final_decision == FinalDecision.pending


@pytest.mark.e2e
def test_multi_user_isolation(
    client: TestClient,
    session: Session,
    faker: Faker,
    an_article,
    a_criterion,
):
    """
    Test that two users working independently cannot access each other's data.

    This test verifies:
    - Each user can only see their own projects
    - Each user can only access their own articles
    - Each user can only create decisions for their own projects
    - Proper 403/404 responses when accessing other users' resources
    """
    # Register and authenticate User A
    user_a_email = faker.email()
    user_a_password = "PasswordA123!"

    client.post(
        f"{API}/auth/register",
        json={
            "email": user_a_email,
            "name": "User A",
            "password": user_a_password,
        },
    )

    token_a_response = client.post(
        f"{API}/auth/token",
        data={"username": user_a_email, "password": user_a_password},
    )
    token_a = token_a_response.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register and authenticate User B
    user_b_email = faker.email()
    user_b_password = "PasswordB123!"

    client.post(
        f"{API}/auth/register",
        json={
            "email": user_b_email,
            "name": "User B",
            "password": user_b_password,
        },
    )

    token_b_response = client.post(
        f"{API}/auth/token",
        data={"username": user_b_email, "password": user_b_password},
    )
    token_b = token_b_response.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates a project
    project_a_response = client.post(
        f"{API}/projects",
        json={
            "name": "User A Project",
            "description": "Project for User A",
            "review_question": "Research question A",
        },
        headers=headers_a,
    )
    project_a = project_a_response.json()
    project_a_id = project_a["id"]

    # User B creates a project
    project_b_response = client.post(
        f"{API}/projects",
        json={
            "name": "User B Project",
            "description": "Project for User B",
            "review_question": "Research question B",
        },
        headers=headers_b,
    )
    project_b = project_b_response.json()
    project_b_id = project_b["id"]

    # Each user creates criteria and articles for their projects
    # User A: Add criterion
    client.post(
        f"{API}/projects/{project_a_id}/criteria",
        json={
            "type": "inclusion",
            "code": "I1",
            "description": "Criterion A",
            "rationale": "Rationale A",
        },
        headers=headers_a,
    )

    # User B: Add criterion
    client.post(
        f"{API}/projects/{project_b_id}/criteria",
        json={
            "type": "inclusion",
            "code": "I1",
            "description": "Criterion B",
            "rationale": "Rationale B",
        },
        headers=headers_b,
    )

    # User A: Add articles
    article_a = an_article(
        project_id=project_a_id,
        status=ArticleStatus.screening,
        title="Article for User A",
    )

    # User B: Add articles
    article_b = an_article(
        project_id=project_b_id,
        status=ArticleStatus.screening,
        title="Article for User B",
    )

    # User A screens their article
    decision_a_response = client.post(
        f"{API}/projects/{project_a_id}/screening/articles/{article_a.id}/decisions",
        json={
            "stage": "title_abstract",
            "decision": "include",
            "source": "human",
            "reasoning": "Good article",
        },
        headers=headers_a,
    )
    assert decision_a_response.status_code == 201

    # User B screens their article
    decision_b_response = client.post(
        f"{API}/projects/{project_b_id}/screening/articles/{article_b.id}/decisions",
        json={
            "stage": "title_abstract",
            "decision": "exclude",
            "source": "human",
            "reasoning": "Not relevant",
        },
        headers=headers_b,
    )
    assert decision_b_response.status_code == 201

    # Verify User A cannot access User B's project
    forbidden_project_response = client.get(
        f"{API}/projects/{project_b_id}",
        headers=headers_a,
    )
    assert forbidden_project_response.status_code == 403

    # Verify User B cannot access User A's articles
    forbidden_articles_response = client.get(
        f"{API}/projects/{project_a_id}/articles",
        headers=headers_b,
    )
    assert forbidden_articles_response.status_code == 403

    # Verify User A cannot create decisions for User B's articles
    forbidden_decision_response = client.post(
        f"{API}/projects/{project_b_id}/screening/articles/{article_b.id}/decisions",
        json={
            "stage": "title_abstract",
            "decision": "include",
            "source": "human",
        },
        headers=headers_a,
    )
    assert forbidden_decision_response.status_code == 403

    # Verify User B cannot access User A's screening stats
    forbidden_stats_response = client.get(
        f"{API}/projects/{project_a_id}/screening/stats",
        headers=headers_b,
    )
    assert forbidden_stats_response.status_code == 403

    # Verify each user can only see their own projects in the list
    projects_a_response = client.get(f"{API}/projects", headers=headers_a)
    projects_a = projects_a_response.json()
    assert len(projects_a["data"]) == 1
    assert projects_a["data"][0]["id"] == project_a_id

    projects_b_response = client.get(f"{API}/projects", headers=headers_b)
    projects_b = projects_b_response.json()
    assert len(projects_b["data"]) == 1
    assert projects_b["data"][0]["id"] == project_b_id


@pytest.mark.e2e
def test_project_teardown(
    client: TestClient,
    session: Session,
    faker: Faker,
    an_article,
):
    """
    Test that deleting a project properly removes all associated data.

    This test verifies:
    - A fully set-up project can be deleted
    - After deletion, the project cannot be retrieved (404)
    - Associated resources are cleaned up
    """
    # Register and authenticate a user
    user_email = faker.email()
    user_password = "Password123!"

    client.post(
        f"{API}/auth/register",
        json={
            "email": user_email,
            "name": faker.name(),
            "password": user_password,
        },
    )

    token_response = client.post(
        f"{API}/auth/token",
        data={"username": user_email, "password": user_password},
    )
    token = token_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a project
    project_response = client.post(
        f"{API}/projects",
        json={
            "name": "Project to Delete",
            "description": "This will be deleted",
            "review_question": "Will this be deleted?",
        },
        headers=headers,
    )
    project = project_response.json()
    project_id = project["id"]

    # Add criteria
    for i in range(2):
        client.post(
            f"{API}/projects/{project_id}/criteria",
            json={
                "type": "inclusion" if i == 0 else "exclusion",
                "code": f"{'I' if i == 0 else 'E'}{i+1}",
                "description": f"Criterion {i+1}",
                "rationale": "Test rationale",
            },
            headers=headers,
        )

    # Add articles
    for i in range(3):
        an_article(
            project_id=project_id,
            status=ArticleStatus.imported,
            title=f"Article {i+1}",
        )

    # Verify project exists
    get_response = client.get(f"{API}/projects/{project_id}", headers=headers)
    assert get_response.status_code == 200

    # Delete the project
    delete_response = client.delete(f"{API}/projects/{project_id}", headers=headers)
    assert delete_response.status_code == 204

    # Verify project is gone
    not_found_response = client.get(f"{API}/projects/{project_id}", headers=headers)
    assert not_found_response.status_code == 404

    # Verify articles endpoint returns 404
    articles_response = client.get(
        f"{API}/projects/{project_id}/articles",
        headers=headers,
    )
    assert articles_response.status_code == 404

    # Verify criteria endpoint returns 404
    criteria_response = client.get(
        f"{API}/projects/{project_id}/criteria",
        headers=headers,
    )
    assert criteria_response.status_code == 404


@pytest.mark.e2e
def test_screening_with_criteria_changes(
    client: TestClient,
    session: Session,
    faker: Faker,
    an_article,
):
    """
    Test that adding criteria mid-workflow doesn't affect past decisions.

    This test verifies:
    - Initial criteria can be created
    - Decisions can be made with initial criteria
    - New criteria can be added after decisions are made
    - Past decisions remain unchanged
    - New screening continues with updated criteria set
    """
    # Register and authenticate a user
    user_email = faker.email()
    user_password = "Password123!"

    client.post(
        f"{API}/auth/register",
        json={
            "email": user_email,
            "name": faker.name(),
            "password": user_password,
        },
    )

    token_response = client.post(
        f"{API}/auth/token",
        data={"username": user_email, "password": user_password},
    )
    token = token_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a project
    project_response = client.post(
        f"{API}/projects",
        json={
            "name": "Dynamic Criteria Project",
            "description": "Testing criteria changes",
            "review_question": "Can criteria change mid-workflow?",
        },
        headers=headers,
    )
    project = project_response.json()
    project_id = project["id"]

    # Add initial criteria
    initial_criteria = [
        {
            "type": "inclusion",
            "code": "I1",
            "description": "Initial inclusion criterion",
            "rationale": "First criterion",
        },
        {
            "type": "exclusion",
            "code": "E1",
            "description": "Initial exclusion criterion",
            "rationale": "First exclusion",
        },
    ]

    for criterion_data in initial_criteria:
        response = client.post(
            f"{API}/projects/{project_id}/criteria",
            json=criterion_data,
            headers=headers,
        )
        assert response.status_code == 201

    # Create articles
    article_1 = an_article(
        project_id=project_id,
        status=ArticleStatus.screening,
        title="Article 1",
    )
    article_2 = an_article(
        project_id=project_id,
        status=ArticleStatus.screening,
        title="Article 2",
    )

    # Screen first article with initial criteria
    decision_1_response = client.post(
        f"{API}/projects/{project_id}/screening/articles/{article_1.id}/decisions",
        json={
            "stage": "title_abstract",
            "decision": "include",
            "source": "human",
            "confidence_score": 0.9,
            "reasoning": "Meets I1, does not meet E1",
        },
        headers=headers,
    )
    assert decision_1_response.status_code == 201
    decision_1 = decision_1_response.json()
    decision_1_id = decision_1["id"]

    # Verify initial screening stats
    stats_before_response = client.get(
        f"{API}/projects/{project_id}/screening/stats",
        headers=headers,
    )
    stats_before = stats_before_response.json()
    assert stats_before["screened_title_abstract"] == 1

    # Add more criteria
    new_criteria = [
        {
            "type": "inclusion",
            "code": "I2",
            "description": "Additional inclusion criterion",
            "rationale": "Added later",
        },
        {
            "type": "exclusion",
            "code": "E2",
            "description": "Additional exclusion criterion",
            "rationale": "Added after screening started",
        },
    ]

    for criterion_data in new_criteria:
        response = client.post(
            f"{API}/projects/{project_id}/criteria",
            json=criterion_data,
            headers=headers,
        )
        assert response.status_code == 201

    # Verify criteria count
    criteria_response = client.get(
        f"{API}/projects/{project_id}/criteria",
        headers=headers,
    )
    criteria = criteria_response.json()
    assert len(criteria["data"]) == 4

    # Verify past decision is unchanged
    decisions_response = client.get(
        f"{API}/projects/{project_id}/screening/articles/{article_1.id}/decisions",
        headers=headers,
    )
    decisions = decisions_response.json()
    assert len(decisions["data"]) == 1
    assert decisions["data"][0]["id"] == decision_1_id
    assert decisions["data"][0]["reasoning"] == "Meets I1, does not meet E1"

    # Continue screening with new criteria
    decision_2_response = client.post(
        f"{API}/projects/{project_id}/screening/articles/{article_2.id}/decisions",
        json={
            "stage": "title_abstract",
            "decision": "exclude",
            "source": "human",
            "confidence_score": 0.95,
            "reasoning": "Meets E2 (new criterion)",
        },
        headers=headers,
    )
    assert decision_2_response.status_code == 201

    # Verify screening stats updated
    stats_after_response = client.get(
        f"{API}/projects/{project_id}/screening/stats",
        headers=headers,
    )
    stats_after = stats_after_response.json()
    assert stats_after["screened_title_abstract"] == 2
    assert stats_after["excluded"] == 1

    # Verify articles endpoint shows correct statuses
    articles_response = client.get(
        f"{API}/projects/{project_id}/articles",
        headers=headers,
    )
    articles = articles_response.json()

    # Find the two articles in the response
    article_statuses = {a["id"]: a["status"] for a in articles["data"]}
    assert article_statuses[article_1.id] == "awaiting_full_text"
    assert article_statuses[article_2.id] == "excluded"
