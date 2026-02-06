"""
E2E integration tests for article management flow.

Tests the complete article lifecycle including:
- CRUD operations (list, get, delete)
- Filtering by status and stage
- Statistics aggregation
- Start screening workflow
- Authorization and ownership isolation
"""

import pytest

from app.core.config import get_settings
from app.features.research.models import ArticleStatus
from app.features.screening.models import ScreeningStage

settings = get_settings()
API = settings.api_prefix


@pytest.mark.e2e
def test_article_lifecycle(auth_as, a_project, an_article):
    """
    Test the complete article CRUD lifecycle.

    - Create articles via fixture
    - List all articles
    - Get individual article
    - Delete one article
    - Verify count decreased
    """
    # Setup: Create project with articles
    client, user = auth_as()
    project = a_project(user)
    article1 = an_article(project.id, title="First Article")
    article2 = an_article(project.id, title="Second Article")
    an_article(project.id, title="Third Article")

    # List all articles
    response = client.get(f"{API}/projects/{project.id}/articles")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 3
    assert data["meta"]["pagination"]["total"] == 3

    # Get individual article
    response = client.get(f"{API}/projects/{project.id}/articles/{article1.id}")
    assert response.status_code == 200
    article_data = response.json()
    assert article_data["id"] == article1.id
    assert article_data["title"] == "First Article"
    assert article_data["project_id"] == project.id
    assert "authors" in article_data
    assert "abstract" in article_data
    assert article_data["status"] == ArticleStatus.imported.value
    assert article_data["current_stage"] == ScreeningStage.title_abstract.value

    # Delete one article
    response = client.delete(f"{API}/projects/{project.id}/articles/{article2.id}")
    assert response.status_code == 204

    # Verify count decreased
    response = client.get(f"{API}/projects/{project.id}/articles")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["meta"]["pagination"]["total"] == 2

    # Verify deleted article no longer accessible
    response = client.get(f"{API}/projects/{project.id}/articles/{article2.id}")
    assert response.status_code == 404


@pytest.mark.e2e
def test_article_list_with_status_filter(auth_as, a_project, an_article):
    """
    Test article list filtering by status query parameter.

    Creates articles with different statuses and verifies that filtering
    returns only matching articles.
    """
    client, user = auth_as()
    project = a_project(user)

    # Create articles with different statuses
    imported_article1 = an_article(project.id, status=ArticleStatus.imported)
    imported_article2 = an_article(project.id, status=ArticleStatus.imported)
    screening_article = an_article(project.id, status=ArticleStatus.screening)
    included_article = an_article(project.id, status=ArticleStatus.included)
    an_article(project.id, status=ArticleStatus.excluded)

    # Filter by imported status
    response = client.get(
        f"{API}/projects/{project.id}/articles",
        params={"status": ArticleStatus.imported.value}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    article_ids = [a["id"] for a in data["data"]]
    assert imported_article1.id in article_ids
    assert imported_article2.id in article_ids
    assert screening_article.id not in article_ids

    # Filter by screening status
    response = client.get(
        f"{API}/projects/{project.id}/articles",
        params={"status": ArticleStatus.screening.value}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == screening_article.id
    assert data["data"][0]["status"] == ArticleStatus.screening.value

    # Filter by included status
    response = client.get(
        f"{API}/projects/{project.id}/articles",
        params={"status": ArticleStatus.included.value}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == included_article.id

    # No filter - get all articles
    response = client.get(f"{API}/projects/{project.id}/articles")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 5


@pytest.mark.e2e
def test_article_list_with_stage_filter(auth_as, a_project, an_article):
    """
    Test article list filtering by screening stage query parameter.

    Creates articles at different screening stages and verifies filtering.
    """
    client, user = auth_as()
    project = a_project(user)

    # Create articles at different stages
    title_abstract_article1 = an_article(
        project.id,
        stage=ScreeningStage.title_abstract
    )
    title_abstract_article2 = an_article(
        project.id,
        stage=ScreeningStage.title_abstract
    )
    full_text_article = an_article(
        project.id,
        stage=ScreeningStage.full_text
    )
    completed_article = an_article(
        project.id,
        stage=ScreeningStage.completed
    )

    # Filter by title_abstract stage
    response = client.get(
        f"{API}/projects/{project.id}/articles",
        params={"stage": ScreeningStage.title_abstract.value}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    article_ids = [a["id"] for a in data["data"]]
    assert title_abstract_article1.id in article_ids
    assert title_abstract_article2.id in article_ids
    assert full_text_article.id not in article_ids

    # Filter by full_text stage
    response = client.get(
        f"{API}/projects/{project.id}/articles",
        params={"stage": ScreeningStage.full_text.value}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == full_text_article.id
    assert data["data"][0]["current_stage"] == ScreeningStage.full_text.value

    # Filter by completed stage
    response = client.get(
        f"{API}/projects/{project.id}/articles",
        params={"stage": ScreeningStage.completed.value}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == completed_article.id

    # No filter - get all articles
    response = client.get(f"{API}/projects/{project.id}/articles")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 4


@pytest.mark.e2e
def test_article_stats(auth_as, a_project, an_article):
    """
    Test the article statistics endpoint.

    Creates articles with various statuses and stages, then verifies
    the stats endpoint returns correct aggregated counts.
    """
    client, user = auth_as()
    project = a_project(user)

    # Create articles with various statuses and stages
    an_article(project.id, status=ArticleStatus.imported, stage=ScreeningStage.title_abstract)
    an_article(project.id, status=ArticleStatus.imported, stage=ScreeningStage.title_abstract)
    an_article(project.id, status=ArticleStatus.screening, stage=ScreeningStage.title_abstract)
    an_article(project.id, status=ArticleStatus.screening, stage=ScreeningStage.full_text)
    an_article(project.id, status=ArticleStatus.included, stage=ScreeningStage.completed)
    an_article(project.id, status=ArticleStatus.excluded, stage=ScreeningStage.completed)
    an_article(project.id, status=ArticleStatus.excluded, stage=ScreeningStage.completed)

    # Get stats
    response = client.get(f"{API}/projects/{project.id}/articles/stats")
    assert response.status_code == 200
    stats = response.json()

    # Verify total count
    assert stats["total"] == 7

    # Verify by_status counts
    assert stats["by_status"][ArticleStatus.imported.value] == 2
    assert stats["by_status"][ArticleStatus.screening.value] == 2
    assert stats["by_status"][ArticleStatus.included.value] == 1
    assert stats["by_status"][ArticleStatus.excluded.value] == 2

    # Verify by_stage counts
    assert stats["by_stage"][ScreeningStage.title_abstract.value] == 3
    assert stats["by_stage"][ScreeningStage.full_text.value] == 1
    assert stats["by_stage"][ScreeningStage.completed.value] == 3


@pytest.mark.e2e
def test_start_screening_flow(auth_as, a_project, an_article):
    """
    Test the start-screening workflow.

    - Create imported articles
    - Call start-screening endpoint
    - Verify all moved to screening status
    - Verify stats reflect the change
    """
    client, user = auth_as()
    project = a_project(user)

    # Create imported articles
    article1 = an_article(project.id, status=ArticleStatus.imported)
    article2 = an_article(project.id, status=ArticleStatus.imported)
    article3 = an_article(project.id, status=ArticleStatus.imported)

    # Also create one that's already screening (should not be affected)
    an_article(project.id, status=ArticleStatus.screening)

    # Verify initial stats
    response = client.get(f"{API}/projects/{project.id}/articles/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["by_status"][ArticleStatus.imported.value] == 3
    assert stats["by_status"][ArticleStatus.screening.value] == 1

    # Start screening
    response = client.post(f"{API}/projects/{project.id}/articles/start-screening")
    assert response.status_code == 200
    result = response.json()
    assert result["count"] == 3
    assert "message" in result

    # Verify all imported articles moved to screening
    response = client.get(f"{API}/projects/{project.id}/articles/{article1.id}")
    assert response.status_code == 200
    assert response.json()["status"] == ArticleStatus.screening.value

    response = client.get(f"{API}/projects/{project.id}/articles/{article2.id}")
    assert response.status_code == 200
    assert response.json()["status"] == ArticleStatus.screening.value

    response = client.get(f"{API}/projects/{project.id}/articles/{article3.id}")
    assert response.status_code == 200
    assert response.json()["status"] == ArticleStatus.screening.value

    # Verify stats updated
    response = client.get(f"{API}/projects/{project.id}/articles/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["by_status"].get(ArticleStatus.imported.value, 0) == 0
    assert stats["by_status"][ArticleStatus.screening.value] == 4


@pytest.mark.e2e
def test_start_screening_idempotent(auth_as, a_project, an_article):
    """
    Test that start-screening is idempotent.

    Calling start-screening twice should result in the second call
    returning count=0 (no more imported articles to move).
    """
    client, user = auth_as()
    project = a_project(user)

    # Create imported articles
    an_article(project.id, status=ArticleStatus.imported)
    an_article(project.id, status=ArticleStatus.imported)

    # First call - should move 2 articles
    response = client.post(f"{API}/projects/{project.id}/articles/start-screening")
    assert response.status_code == 200
    result = response.json()
    assert result["count"] == 2

    # Second call - should move 0 articles (none left in imported status)
    response = client.post(f"{API}/projects/{project.id}/articles/start-screening")
    assert response.status_code == 200
    result = response.json()
    assert result["count"] == 0

    # Verify stats show all in screening
    response = client.get(f"{API}/projects/{project.id}/articles/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["by_status"].get(ArticleStatus.imported.value, 0) == 0
    assert stats["by_status"][ArticleStatus.screening.value] == 2


@pytest.mark.e2e
def test_article_ownership_isolation(auth_as, a_user, a_project, an_article):
    """
    Test that articles are properly isolated by project ownership.

    User A's project articles should not be accessible by User B.
    """
    # Create User A with a project and articles
    client_a, user_a = auth_as()
    project_a = a_project(user_a)
    article_a = an_article(project_a.id, title="User A's Article")

    # Create User B with their own project
    user_b = a_user()
    a_project(user_b)

    # User B attempts to access User A's article
    client_b, _ = auth_as(user_b)

    # Try to get User A's article
    response = client_b.get(f"{API}/projects/{project_a.id}/articles/{article_a.id}")
    assert response.status_code == 403

    # Try to list User A's articles
    response = client_b.get(f"{API}/projects/{project_a.id}/articles")
    assert response.status_code == 403

    # Try to delete User A's article
    response = client_b.delete(f"{API}/projects/{project_a.id}/articles/{article_a.id}")
    assert response.status_code == 403

    # Try to get stats for User A's project
    response = client_b.get(f"{API}/projects/{project_a.id}/articles/stats")
    assert response.status_code == 403

    # Try to start screening for User A's project
    response = client_b.post(f"{API}/projects/{project_a.id}/articles/start-screening")
    assert response.status_code == 403

    # Verify User A can still access their own articles
    response = client_a.get(f"{API}/projects/{project_a.id}/articles/{article_a.id}")
    assert response.status_code == 200
    assert response.json()["title"] == "User A's Article"


@pytest.mark.e2e
def test_article_not_found(auth_as, a_project):
    """
    Test that accessing non-existent articles returns 404.

    Tests both GET and DELETE operations on articles that don't exist.
    """
    client, user = auth_as()
    project = a_project(user)

    # Non-existent article ID
    non_existent_id = 999999

    # Try to get non-existent article
    response = client.get(f"{API}/projects/{project.id}/articles/{non_existent_id}")
    assert response.status_code == 404

    # Try to delete non-existent article
    response = client.delete(f"{API}/projects/{project.id}/articles/{non_existent_id}")
    assert response.status_code == 404


@pytest.mark.e2e
def test_article_wrong_project(auth_as, a_project, an_article):
    """
    Test that articles cannot be accessed via wrong project URL.

    Article exists in project A, but attempting to access it via
    project B's URL should return 404 (not found in that project context).
    """
    client, user = auth_as()

    # Create two projects for the same user
    project_a = a_project(user)
    project_b = a_project(user)

    # Create article in project A
    article_in_a = an_article(project_a.id, title="Article in Project A")

    # Try to access article via project B's URL
    response = client.get(f"{API}/projects/{project_b.id}/articles/{article_in_a.id}")
    assert response.status_code == 404

    # Try to delete article via project B's URL
    response = client.delete(f"{API}/projects/{project_b.id}/articles/{article_in_a.id}")
    assert response.status_code == 404

    # Verify article is accessible via correct project URL
    response = client.get(f"{API}/projects/{project_a.id}/articles/{article_in_a.id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Article in Project A"
    assert response.json()["project_id"] == project_a.id
