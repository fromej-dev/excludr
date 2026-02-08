"""
E2E integration tests for project management flow.

Tests cover the complete lifecycle of project operations including CRUD operations,
ownership isolation, pagination, validation, and authentication requirements.
"""

import pytest

from app.core.config import get_settings

settings = get_settings()
API = settings.api_prefix


@pytest.mark.e2e
def test_project_crud_lifecycle(auth_as, faker):
    """
    Test complete CRUD lifecycle: Create → Get → Update → Verify → Delete → Verify 404.

    This test validates the entire project lifecycle from creation through deletion,
    ensuring all operations work correctly and data persists/updates as expected.
    """
    client, user = auth_as()

    # Create project
    create_data = {
        "name": faker.catch_phrase()[:50],
        "description": faker.text(max_nb_chars=200),
        "review_question": "What is the effect of intervention X on outcome Y?",
    }

    create_response = client.post(f"{API}/projects", json=create_data)
    assert create_response.status_code == 201
    created_project = create_response.json()
    assert created_project["name"] == create_data["name"]
    assert created_project["description"] == create_data["description"]
    assert created_project["review_question"] == create_data["review_question"]
    assert created_project["owner_id"] == user.id
    assert "id" in created_project
    assert "created_at" in created_project
    assert "updated_at" in created_project

    project_id = created_project["id"]

    # Get project by ID
    get_response = client.get(f"{API}/projects/{project_id}")
    assert get_response.status_code == 200
    retrieved_project = get_response.json()
    assert retrieved_project["id"] == project_id
    assert retrieved_project["name"] == create_data["name"]
    assert retrieved_project["description"] == create_data["description"]
    assert retrieved_project["review_question"] == create_data["review_question"]

    # Update project
    update_data = {
        "name": faker.catch_phrase()[:50],
        "description": "Updated description for the systematic review",
        "review_question": "What is the updated research question?",
    }

    update_response = client.patch(f"{API}/projects/{project_id}", json=update_data)
    assert update_response.status_code == 200
    updated_project = update_response.json()
    assert updated_project["id"] == project_id
    assert updated_project["name"] == update_data["name"]
    assert updated_project["description"] == update_data["description"]
    assert updated_project["review_question"] == update_data["review_question"]

    # Verify update persisted
    verify_response = client.get(f"{API}/projects/{project_id}")
    assert verify_response.status_code == 200
    verified_project = verify_response.json()
    assert verified_project["name"] == update_data["name"]
    assert verified_project["description"] == update_data["description"]
    assert verified_project["review_question"] == update_data["review_question"]

    # Delete project
    delete_response = client.delete(f"{API}/projects/{project_id}")
    assert delete_response.status_code == 204

    # Verify project is gone (404)
    not_found_response = client.get(f"{API}/projects/{project_id}")
    assert not_found_response.status_code == 404
    assert not_found_response.json()["detail"] == "Project not found"


@pytest.mark.e2e
def test_project_ownership_isolation(auth_as, a_project, faker):
    """
    Test ownership isolation: User A creates project, User B cannot access it.

    Ensures that project access is strictly limited to the owner. Non-owners
    should receive 403 Forbidden for GET, PATCH, and DELETE operations.
    """
    # User A creates a project
    client_a, user_a = auth_as()
    project = a_project(user_a)
    project_id = project.id

    # User A can access their project
    get_response_a = client_a.get(f"{API}/projects/{project_id}")
    assert get_response_a.status_code == 200
    assert get_response_a.json()["id"] == project_id

    # User B tries to access User A's project
    client_b, user_b = auth_as()

    # GET should fail with 403
    get_response_b = client_b.get(f"{API}/projects/{project_id}")
    assert get_response_b.status_code == 403
    assert get_response_b.json()["detail"] == "You are not the owner of the project"

    # PATCH should fail with 403
    update_data = {"name": faker.catch_phrase()[:50]}
    patch_response_b = client_b.patch(f"{API}/projects/{project_id}", json=update_data)
    assert patch_response_b.status_code == 403
    assert patch_response_b.json()["detail"] == "You are not the owner of the project"

    # DELETE should fail with 403
    delete_response_b = client_b.delete(f"{API}/projects/{project_id}")
    assert delete_response_b.status_code == 403
    assert delete_response_b.json()["detail"] == "You are not the owner of the project"

    # Verify User A's project is still intact and User A can still access it
    # Re-authenticate as user_a since auth_as shares the same client
    auth_as(user_a)
    verify_response_a = client_a.get(f"{API}/projects/{project_id}")
    assert verify_response_a.status_code == 200
    assert verify_response_a.json()["name"] == project.name


@pytest.mark.e2e
def test_project_list_pagination(auth_as, a_project):
    """
    Test pagination with 15 projects: default page size 10, page 2 gets remaining 5.

    Validates that pagination metadata is correct and that page boundaries
    work as expected with the default page size.
    """
    client, user = auth_as()

    # Create 15 projects for the user
    projects = [a_project(user) for _ in range(15)]

    # Get first page (default page size is 10)
    page1_response = client.get(f"{API}/projects")
    assert page1_response.status_code == 200
    page1_data = page1_response.json()

    assert len(page1_data["data"]) == 10
    assert page1_data["meta"]["pagination"]["total_items"] == 15
    assert page1_data["meta"]["pagination"]["current_page"] == 1
    assert page1_data["meta"]["pagination"]["per_page"] == 10
    assert page1_data["meta"]["pagination"]["total_pages"] == 2

    # Get second page
    page2_response = client.get(f"{API}/projects?page=2")
    assert page2_response.status_code == 200
    page2_data = page2_response.json()

    assert len(page2_data["data"]) == 5
    assert page2_data["meta"]["pagination"]["total_items"] == 15
    assert page2_data["meta"]["pagination"]["current_page"] == 2
    assert page2_data["meta"]["pagination"]["per_page"] == 10
    assert page2_data["meta"]["pagination"]["total_pages"] == 2

    # Verify no duplicates between pages
    page1_ids = {p["id"] for p in page1_data["data"]}
    page2_ids = {p["id"] for p in page2_data["data"]}
    assert len(page1_ids.intersection(page2_ids)) == 0

    # Verify all 15 projects are accounted for
    all_ids = page1_ids.union(page2_ids)
    assert len(all_ids) == 15
    expected_ids = {p.id for p in projects}
    assert all_ids == expected_ids


@pytest.mark.e2e
def test_project_list_only_own_projects(auth_as, a_project):
    """
    Test project list isolation: User A sees only their projects, User B sees only theirs.

    Ensures that the project list endpoint properly filters projects by ownership
    and does not leak information about other users' projects.
    """
    # User A creates 5 projects
    client_a, user_a = auth_as()
    user_a_projects = [a_project(user_a) for _ in range(5)]
    user_a_project_ids = {p.id for p in user_a_projects}

    # User B creates 3 projects
    client_b, user_b = auth_as()
    user_b_projects = [a_project(user_b) for _ in range(3)]
    user_b_project_ids = {p.id for p in user_b_projects}

    # User A should only see their 5 projects
    # Re-authenticate as user_a since auth_as shares the same client
    auth_as(user_a)
    response_a = client_a.get(f"{API}/projects")
    assert response_a.status_code == 200
    data_a = response_a.json()
    assert len(data_a["data"]) == 5
    assert data_a["meta"]["pagination"]["total_items"] == 5
    returned_ids_a = {p["id"] for p in data_a["data"]}
    assert returned_ids_a == user_a_project_ids

    # User B should only see their 3 projects
    auth_as(user_b)
    response_b = client_b.get(f"{API}/projects")
    assert response_b.status_code == 200
    data_b = response_b.json()
    assert len(data_b["data"]) == 3
    assert data_b["meta"]["pagination"]["total_items"] == 3
    returned_ids_b = {p["id"] for p in data_b["data"]}
    assert returned_ids_b == user_b_project_ids

    # Verify no overlap between user project lists
    assert len(returned_ids_a.intersection(returned_ids_b)) == 0


@pytest.mark.e2e
def test_project_with_review_question(auth_as, faker):
    """
    Test review_question field: create project with it, verify it's returned and updateable.

    The review_question field is core to systematic reviews and should be
    fully supported in create, read, and update operations.
    """
    client, user = auth_as()

    # Create project with review_question
    review_question = "What is the efficacy of cognitive behavioral therapy for treating anxiety disorders in adults?"
    create_data = {
        "name": faker.catch_phrase()[:50],
        "description": faker.text(max_nb_chars=200),
        "review_question": review_question,
    }

    create_response = client.post(f"{API}/projects", json=create_data)
    assert create_response.status_code == 201
    created_project = create_response.json()
    assert created_project["review_question"] == review_question
    project_id = created_project["id"]

    # Verify review_question is returned in GET
    get_response = client.get(f"{API}/projects/{project_id}")
    assert get_response.status_code == 200
    assert get_response.json()["review_question"] == review_question

    # Update only the review_question
    new_review_question = (
        "Updated: What is the long-term effectiveness of CBT for anxiety?"
    )
    update_response = client.patch(
        f"{API}/projects/{project_id}", json={"review_question": new_review_question}
    )
    assert update_response.status_code == 200
    updated_project = update_response.json()
    assert updated_project["review_question"] == new_review_question
    # Verify other fields remain unchanged
    assert updated_project["name"] == create_data["name"]
    assert updated_project["description"] == create_data["description"]

    # Verify update persisted
    verify_response = client.get(f"{API}/projects/{project_id}")
    assert verify_response.status_code == 200
    assert verify_response.json()["review_question"] == new_review_question

    # Create project without review_question (should be None/null)
    minimal_data = {"name": faker.catch_phrase()[:50]}
    minimal_response = client.post(f"{API}/projects", json=minimal_data)
    assert minimal_response.status_code == 201
    assert minimal_response.json()["review_question"] is None


@pytest.mark.e2e
def test_create_project_validation(auth_client, faker):
    """
    Test validation errors: empty name, too long name, missing name all return 422.

    Ensures proper input validation for project creation with clear error messages.
    """
    # Test with name too short (< 3 characters)
    short_name_data = {"name": "ab"}
    short_response = auth_client.post(f"{API}/projects", json=short_name_data)
    assert short_response.status_code == 422
    short_errors = short_response.json()["detail"]
    assert any(
        error["type"] == "string_too_short" and "name" in str(error["loc"])
        for error in short_errors
    )

    # Test with empty name
    empty_name_data = {"name": ""}
    empty_response = auth_client.post(f"{API}/projects", json=empty_name_data)
    assert empty_response.status_code == 422
    empty_errors = empty_response.json()["detail"]
    assert any(
        error["type"] == "string_too_short" and "name" in str(error["loc"])
        for error in empty_errors
    )

    # Test with name too long (> 50 characters)
    long_name = "x" * 51
    long_name_data = {"name": long_name}
    long_response = auth_client.post(f"{API}/projects", json=long_name_data)
    assert long_response.status_code == 422
    long_errors = long_response.json()["detail"]
    assert any(
        error["type"] == "string_too_long" and "name" in str(error["loc"])
        for error in long_errors
    )

    # Test with missing name field entirely
    missing_name_data = {"description": faker.text()}
    missing_response = auth_client.post(f"{API}/projects", json=missing_name_data)
    assert missing_response.status_code == 422
    missing_errors = missing_response.json()["detail"]
    assert any(
        error["type"] == "missing" and "name" in str(error["loc"])
        for error in missing_errors
    )


@pytest.mark.e2e
def test_project_article_count(auth_as, a_project, an_article):
    """
    Test number_of_articles computed field: create project, add articles, verify count.

    The number_of_articles field should accurately reflect the count of articles
    associated with the project.
    """
    client, user = auth_as()
    project = a_project(user)
    project_id = project.id

    # Initially, project should have 0 articles
    response = client.get(f"{API}/projects/{project_id}")
    assert response.status_code == 200
    project_data = response.json()
    assert project_data["number_of_articles"] == 0

    # Add 3 articles to the project
    an_article(project_id=project_id, title="First article")
    an_article(project_id=project_id, title="Second article")
    an_article(project_id=project_id, title="Third article")

    # Verify count is now 3
    response = client.get(f"{API}/projects/{project_id}")
    assert response.status_code == 200
    project_data = response.json()
    assert project_data["number_of_articles"] == 3

    # Add 7 more articles (total 10)
    for i in range(7):
        an_article(project_id=project_id, title=f"Article {i + 4}")

    # Verify count is now 10
    response = client.get(f"{API}/projects/{project_id}")
    assert response.status_code == 200
    project_data = response.json()
    assert project_data["number_of_articles"] == 10

    # Verify count appears in list endpoint as well
    list_response = client.get(f"{API}/projects")
    assert list_response.status_code == 200
    list_data = list_response.json()
    project_in_list = next(p for p in list_data["data"] if p["id"] == project_id)
    assert project_in_list["number_of_articles"] == 10


@pytest.mark.e2e
def test_unauthenticated_project_access(client, a_project, a_user, faker):
    """
    Test that all project endpoints return 401 without authentication.

    Ensures that project operations require authentication and cannot be
    performed by unauthenticated users.
    """
    # Create a project for testing (using fixtures that handle auth internally)
    user = a_user()
    project = a_project(user)
    project_id = project.id

    # GET /projects - list projects
    list_response = client.get(f"{API}/projects")
    assert list_response.status_code == 401
    assert "detail" in list_response.json()

    # GET /projects/{id} - get single project
    get_response = client.get(f"{API}/projects/{project_id}")
    assert get_response.status_code == 401
    assert "detail" in get_response.json()

    # POST /projects - create project
    create_data = {"name": faker.catch_phrase()[:50]}
    post_response = client.post(f"{API}/projects", json=create_data)
    assert post_response.status_code == 401
    assert "detail" in post_response.json()

    # PATCH /projects/{id} - update project
    update_data = {"name": faker.catch_phrase()[:50]}
    patch_response = client.patch(f"{API}/projects/{project_id}", json=update_data)
    assert patch_response.status_code == 401
    assert "detail" in patch_response.json()

    # DELETE /projects/{id} - delete project
    delete_response = client.delete(f"{API}/projects/{project_id}")
    assert delete_response.status_code == 401
    assert "detail" in delete_response.json()
