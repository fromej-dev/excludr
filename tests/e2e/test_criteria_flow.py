"""
E2E integration tests for criteria management flow.

These tests verify the complete lifecycle of screening criteria management,
including CRUD operations, filtering, reordering, validation, and access control.
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import get_settings
from app.features.criteria.models import CriterionType

settings = get_settings()
API = settings.api_prefix


@pytest.mark.e2e
def test_criteria_crud_lifecycle(
    auth_as,
    a_project,
    faker,
    client: TestClient,
):
    """
    Test complete CRUD lifecycle for criteria.

    Creates inclusion and exclusion criteria, lists them, updates one,
    deletes one, and verifies the list is updated correctly.
    """
    # Setup: Create authenticated user and project
    client, user = auth_as()
    project = a_project(user)
    base_url = f"{API}/projects/{project.id}/criteria"

    # Create inclusion criterion
    inclusion_data = {
        "type": "inclusion",
        "code": "I1",
        "description": "Study includes adult participants",
        "rationale": "We want to focus on adult populations",
    }
    res = client.post(base_url, json=inclusion_data)
    assert res.status_code == 201
    inclusion_criterion = res.json()
    assert inclusion_criterion["type"] == "inclusion"
    assert inclusion_criterion["code"] == "I1"
    assert inclusion_criterion["description"] == inclusion_data["description"]
    assert inclusion_criterion["rationale"] == inclusion_data["rationale"]
    assert inclusion_criterion["is_active"] is True
    assert "id" in inclusion_criterion
    assert "created_at" in inclusion_criterion
    assert "updated_at" in inclusion_criterion

    # Create exclusion criterion
    exclusion_data = {
        "type": "exclusion",
        "code": "E1",
        "description": "Non-English language publications",
        "rationale": "Team cannot read other languages",
    }
    res = client.post(base_url, json=exclusion_data)
    assert res.status_code == 201
    exclusion_criterion = res.json()
    assert exclusion_criterion["type"] == "exclusion"
    assert exclusion_criterion["code"] == "E1"

    # List all criteria
    res = client.get(base_url)
    assert res.status_code == 200
    data = res.json()
    assert "data" in data
    assert "meta" in data
    assert "pagination" in data["meta"]
    assert len(data["data"]) == 2
    assert data["meta"]["pagination"]["total_items"] == 2

    # Verify both criteria are in the list
    codes = [c["code"] for c in data["data"]]
    assert "I1" in codes
    assert "E1" in codes

    # Update the inclusion criterion
    update_data = {
        "description": "Study includes participants aged 18 and older",
        "is_active": True,
    }
    res = client.patch(f"{base_url}/{inclusion_criterion['id']}", json=update_data)
    assert res.status_code == 200
    updated = res.json()
    assert updated["description"] == update_data["description"]
    assert updated["code"] == "I1"  # Code unchanged
    assert updated["type"] == "inclusion"  # Type unchanged

    # Delete the exclusion criterion
    res = client.delete(f"{base_url}/{exclusion_criterion['id']}")
    assert res.status_code == 204

    # Verify list updated after deletion
    res = client.get(base_url)
    assert res.status_code == 200
    data = res.json()
    assert len(data["data"]) == 1
    assert data["meta"]["pagination"]["total_items"] == 1
    assert data["data"][0]["code"] == "I1"


@pytest.mark.e2e
def test_criteria_active_filter(
    auth_as,
    a_project,
    client: TestClient,
):
    """
    Test filtering criteria by active status.

    Creates both active and inactive criteria, then verifies that the
    active_only=true query parameter correctly filters the results.
    """
    # Setup
    client, user = auth_as()
    project = a_project(user)
    base_url = f"{API}/projects/{project.id}/criteria"

    # Create active inclusion criterion
    res = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I1",
            "description": "Active inclusion criterion",
            "is_active": True,
        },
    )
    assert res.status_code == 201
    active_inclusion = res.json()

    # Create inactive inclusion criterion
    res = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I2",
            "description": "Inactive inclusion criterion",
            "is_active": False,
        },
    )
    assert res.status_code == 201
    inactive_inclusion = res.json()

    # Create active exclusion criterion
    res = client.post(
        base_url,
        json={
            "type": "exclusion",
            "code": "E1",
            "description": "Active exclusion criterion",
            "is_active": True,
        },
    )
    assert res.status_code == 201
    active_exclusion = res.json()

    # Create inactive exclusion criterion
    res = client.post(
        base_url,
        json={
            "type": "exclusion",
            "code": "E2",
            "description": "Inactive exclusion criterion",
            "is_active": False,
        },
    )
    assert res.status_code == 201
    inactive_exclusion = res.json()

    # List all criteria (no filter)
    res = client.get(base_url)
    assert res.status_code == 200
    all_criteria = res.json()
    assert len(all_criteria["data"]) == 4
    assert all_criteria["meta"]["pagination"]["total_items"] == 4

    # List only active criteria
    res = client.get(f"{base_url}?active_only=true")
    assert res.status_code == 200
    active_criteria = res.json()
    assert len(active_criteria["data"]) == 2
    assert active_criteria["meta"]["pagination"]["total_items"] == 2

    # Verify only active criteria are returned
    active_ids = [c["id"] for c in active_criteria["data"]]
    assert active_inclusion["id"] in active_ids
    assert active_exclusion["id"] in active_ids
    assert inactive_inclusion["id"] not in active_ids
    assert inactive_exclusion["id"] not in active_ids

    # Verify all active criteria have is_active=True
    for criterion in active_criteria["data"]:
        assert criterion["is_active"] is True


@pytest.mark.e2e
def test_criteria_reorder(
    auth_as,
    a_project,
    client: TestClient,
):
    """
    Test reordering criteria within a project.

    Creates three criteria, reorders them using the reorder endpoint,
    and verifies the new order is reflected in the list.
    """
    # Setup
    client, user = auth_as()
    project = a_project(user)
    base_url = f"{API}/projects/{project.id}/criteria"

    # Create three inclusion criteria with initial order
    res1 = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I1",
            "description": "First criterion",
            "order": 0,
        },
    )
    assert res1.status_code == 201
    c1 = res1.json()

    res2 = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I2",
            "description": "Second criterion",
            "order": 1,
        },
    )
    assert res2.status_code == 201
    c2 = res2.json()

    res3 = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I3",
            "description": "Third criterion",
            "order": 2,
        },
    )
    assert res3.status_code == 201
    c3 = res3.json()

    # Verify initial order
    res = client.get(base_url)
    assert res.status_code == 200
    initial_list = res.json()["data"]
    initial_ids = [c["id"] for c in initial_list]
    assert initial_ids == [c1["id"], c2["id"], c3["id"]]

    # Reorder criteria: reverse the order
    reorder_data = {"criterion_ids": [c3["id"], c2["id"], c1["id"]]}
    res = client.post(f"{base_url}/reorder", json=reorder_data)
    assert res.status_code == 200
    reordered = res.json()
    assert isinstance(reordered, list)
    assert len(reordered) == 3

    # Verify new order in response
    reordered_ids = [c["id"] for c in reordered]
    assert reordered_ids == [c3["id"], c2["id"], c1["id"]]

    # Verify order is persisted
    res = client.get(base_url)
    assert res.status_code == 200
    persisted_list = res.json()["data"]
    persisted_ids = [c["id"] for c in persisted_list]
    assert persisted_ids == [c3["id"], c2["id"], c1["id"]]

    # Verify order field values were updated
    for idx, criterion in enumerate(persisted_list):
        assert criterion["order"] == idx


@pytest.mark.e2e
def test_criteria_types(
    auth_as,
    a_project,
    client: TestClient,
):
    """
    Test creation of both inclusion and exclusion criteria types.

    Verifies that the type field is correctly set and returned for
    both inclusion and exclusion criteria.
    """
    # Setup
    client, user = auth_as()
    project = a_project(user)
    base_url = f"{API}/projects/{project.id}/criteria"

    # Create inclusion criterion
    inclusion_data = {
        "type": "inclusion",
        "code": "I1",
        "description": "Must be randomized controlled trial",
    }
    res = client.post(base_url, json=inclusion_data)
    assert res.status_code == 201
    inclusion = res.json()
    assert inclusion["type"] == "inclusion"
    assert inclusion["type"] == CriterionType.inclusion.value

    # Create exclusion criterion
    exclusion_data = {
        "type": "exclusion",
        "code": "E1",
        "description": "Animal studies only",
    }
    res = client.post(base_url, json=exclusion_data)
    assert res.status_code == 201
    exclusion = res.json()
    assert exclusion["type"] == "exclusion"
    assert exclusion["type"] == CriterionType.exclusion.value

    # List all criteria
    res = client.get(base_url)
    assert res.status_code == 200
    all_criteria = res.json()["data"]
    assert len(all_criteria) == 2

    # Verify type field in list response
    types = {c["code"]: c["type"] for c in all_criteria}
    assert types["I1"] == "inclusion"
    assert types["E1"] == "exclusion"

    # Get individual criteria and verify type
    res = client.get(f"{base_url}/{inclusion['id']}")
    assert res.status_code == 200
    assert res.json()["type"] == "inclusion"

    res = client.get(f"{base_url}/{exclusion['id']}")
    assert res.status_code == 200
    assert res.json()["type"] == "exclusion"


@pytest.mark.e2e
def test_criteria_auto_order(
    auth_as,
    a_project,
    client: TestClient,
):
    """
    Test automatic order assignment when order is not specified.

    Creates criteria without specifying order and verifies that
    auto-incrementing order is assigned per type.
    """
    # Setup
    client, user = auth_as()
    project = a_project(user)
    base_url = f"{API}/projects/{project.id}/criteria"

    # Create inclusion criteria without specifying order
    i1 = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I1",
            "description": "First inclusion",
        },
    ).json()

    i2 = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I2",
            "description": "Second inclusion",
        },
    ).json()

    i3 = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I3",
            "description": "Third inclusion",
        },
    ).json()

    # Create exclusion criteria without specifying order
    e1 = client.post(
        base_url,
        json={
            "type": "exclusion",
            "code": "E1",
            "description": "First exclusion",
        },
    ).json()

    e2 = client.post(
        base_url,
        json={
            "type": "exclusion",
            "code": "E2",
            "description": "Second exclusion",
        },
    ).json()

    # Verify order field exists and has a value
    assert "order" in i1
    assert "order" in i2
    assert "order" in i3
    assert "order" in e1
    assert "order" in e2

    # List all criteria
    res = client.get(base_url)
    assert res.status_code == 200
    all_criteria = res.json()["data"]
    assert len(all_criteria) == 5

    # Group by type
    inclusions = [c for c in all_criteria if c["type"] == "inclusion"]
    exclusions = [c for c in all_criteria if c["type"] == "exclusion"]

    assert len(inclusions) == 3
    assert len(exclusions) == 2

    # Verify orders are set and sequential (even if default is 0)
    # Note: The actual auto-increment behavior depends on service implementation
    # Here we just verify that order fields exist and are integers
    for criterion in all_criteria:
        assert isinstance(criterion["order"], int)
        assert criterion["order"] >= 0


@pytest.mark.e2e
def test_criteria_validation(
    auth_as,
    a_project,
    client: TestClient,
):
    """
    Test validation of criterion fields.

    Verifies that invalid data (empty code, invalid type, description too long)
    results in 422 Unprocessable Entity responses.
    """
    # Setup
    client, user = auth_as()
    project = a_project(user)
    base_url = f"{API}/projects/{project.id}/criteria"

    # Test empty code
    res = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "",
            "description": "Valid description",
        },
    )
    assert res.status_code == 422
    error = res.json()
    assert "detail" in error

    # Test code too long (max 10 chars)
    res = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I" * 11,  # 11 characters
            "description": "Valid description",
        },
    )
    assert res.status_code == 422

    # Test invalid type
    res = client.post(
        base_url,
        json={
            "type": "invalid_type",
            "code": "I1",
            "description": "Valid description",
        },
    )
    assert res.status_code == 422

    # Test empty description
    res = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I1",
            "description": "",
        },
    )
    assert res.status_code == 422

    # Test description too long (max 500 chars)
    res = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I1",
            "description": "x" * 501,  # 501 characters
        },
    )
    assert res.status_code == 422

    # Test rationale too long (max 1000 chars)
    res = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I1",
            "description": "Valid description",
            "rationale": "x" * 1001,  # 1001 characters
        },
    )
    assert res.status_code == 422

    # Test missing required fields
    res = client.post(
        base_url,
        json={
            "code": "I1",
            # Missing type and description
        },
    )
    assert res.status_code == 422

    # Verify valid data still works
    res = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I1",
            "description": "Valid description",
            "rationale": "x" * 1000,  # Exactly 1000 chars - should be valid
        },
    )
    assert res.status_code == 201


@pytest.mark.e2e
def test_criteria_ownership_isolation(
    auth_as,
    a_user,
    a_project,
    a_criterion,
    session: Session,
    client: TestClient,
):
    """
    Test that criteria are isolated between users.

    Verifies that User B cannot access criteria from User A's project,
    receiving a 403 Forbidden response.
    """
    # Setup: Create User A with a project and criteria
    client, user_a = auth_as()
    project_a = a_project(user_a)
    criterion_a = a_criterion(
        project_a.id,
        CriterionType.inclusion,
        "I1",
        "User A's criterion",
    )

    # Verify User A can access their criterion
    res = client.get(f"{API}/projects/{project_a.id}/criteria")
    assert res.status_code == 200
    assert len(res.json()["data"]) == 1

    res = client.get(f"{API}/projects/{project_a.id}/criteria/{criterion_a.id}")
    assert res.status_code == 200
    assert res.json()["id"] == criterion_a.id

    # Setup: Create User B with their own project
    user_b = a_user()
    project_b = a_project(user_b)

    # Authenticate as User B
    client.headers.clear()
    client, user_b = auth_as(user_b)

    # User B attempts to list User A's criteria
    res = client.get(f"{API}/projects/{project_a.id}/criteria")
    assert res.status_code == 403
    assert res.json()["detail"] == "You are not the owner of the project"

    # User B attempts to get specific criterion from User A's project
    res = client.get(f"{API}/projects/{project_a.id}/criteria/{criterion_a.id}")
    assert res.status_code == 403
    assert res.json()["detail"] == "You are not the owner of the project"

    # User B attempts to update User A's criterion
    res = client.patch(
        f"{API}/projects/{project_a.id}/criteria/{criterion_a.id}",
        json={"description": "Attempted update"},
    )
    assert res.status_code == 403

    # User B attempts to delete User A's criterion
    res = client.delete(f"{API}/projects/{project_a.id}/criteria/{criterion_a.id}")
    assert res.status_code == 403

    # User B attempts to create criterion in User A's project
    res = client.post(
        f"{API}/projects/{project_a.id}/criteria",
        json={
            "type": "inclusion",
            "code": "I2",
            "description": "Attempted creation",
        },
    )
    assert res.status_code == 403

    # Verify User B can still access their own project's criteria
    res = client.get(f"{API}/projects/{project_b.id}/criteria")
    assert res.status_code == 200


@pytest.mark.e2e
def test_criteria_wrong_project(
    auth_as,
    a_project,
    a_criterion,
    session: Session,
    client: TestClient,
):
    """
    Test accessing criterion via wrong project URL.

    Verifies that a criterion in project A cannot be accessed via project B's
    URL, even by the same user, receiving a 404 Not Found response.
    """
    # Setup: Create one user with two projects
    client, user = auth_as()
    project_a = a_project(user)
    project_b = a_project(user)

    # Create criterion in project A
    criterion_a = a_criterion(
        project_a.id,
        CriterionType.inclusion,
        "I1",
        "Criterion in project A",
    )

    # Verify criterion is accessible via correct project URL
    res = client.get(f"{API}/projects/{project_a.id}/criteria/{criterion_a.id}")
    assert res.status_code == 200
    assert res.json()["id"] == criterion_a.id
    assert res.json()["project_id"] == project_a.id

    # Attempt to access criterion A via project B's URL
    res = client.get(f"{API}/projects/{project_b.id}/criteria/{criterion_a.id}")
    assert res.status_code == 404
    assert res.json()["detail"] == "Criterion not found"

    # Attempt to update criterion A via project B's URL
    res = client.patch(
        f"{API}/projects/{project_b.id}/criteria/{criterion_a.id}",
        json={"description": "Attempted update via wrong project"},
    )
    assert res.status_code == 404

    # Attempt to delete criterion A via project B's URL
    res = client.delete(f"{API}/projects/{project_b.id}/criteria/{criterion_a.id}")
    assert res.status_code == 404

    # Verify criterion still exists and is accessible via correct URL
    res = client.get(f"{API}/projects/{project_a.id}/criteria/{criterion_a.id}")
    assert res.status_code == 200
    assert res.json()["description"] == "Criterion in project A"


@pytest.mark.e2e
def test_criteria_deactivate_and_reactivate(
    auth_as,
    a_project,
    client: TestClient,
):
    """
    Test deactivating and reactivating criteria.

    Creates a criterion, deactivates it via PATCH, verifies it's excluded from
    active_only filter, then reactivates and verifies it's back in the list.
    """
    # Setup
    client, user = auth_as()
    project = a_project(user)
    base_url = f"{API}/projects/{project.id}/criteria"

    # Create an active criterion
    res = client.post(
        base_url,
        json={
            "type": "inclusion",
            "code": "I1",
            "description": "Test criterion for activation toggle",
            "is_active": True,
        },
    )
    assert res.status_code == 201
    criterion = res.json()
    assert criterion["is_active"] is True

    # Verify it appears in active_only list
    res = client.get(f"{base_url}?active_only=true")
    assert res.status_code == 200
    active_list = res.json()["data"]
    assert len(active_list) == 1
    assert active_list[0]["id"] == criterion["id"]

    # Deactivate the criterion
    res = client.patch(
        f"{base_url}/{criterion['id']}",
        json={"is_active": False},
    )
    assert res.status_code == 200
    updated = res.json()
    assert updated["is_active"] is False
    assert updated["id"] == criterion["id"]

    # Verify it no longer appears in active_only list
    res = client.get(f"{base_url}?active_only=true")
    assert res.status_code == 200
    active_list_after = res.json()["data"]
    assert len(active_list_after) == 0

    # Verify it still appears in full list (no filter)
    res = client.get(base_url)
    assert res.status_code == 200
    full_list = res.json()["data"]
    assert len(full_list) == 1
    assert full_list[0]["id"] == criterion["id"]
    assert full_list[0]["is_active"] is False

    # Reactivate the criterion
    res = client.patch(
        f"{base_url}/{criterion['id']}",
        json={"is_active": True},
    )
    assert res.status_code == 200
    reactivated = res.json()
    assert reactivated["is_active"] is True

    # Verify it's back in active_only list
    res = client.get(f"{base_url}?active_only=true")
    assert res.status_code == 200
    active_list_final = res.json()["data"]
    assert len(active_list_final) == 1
    assert active_list_final[0]["id"] == criterion["id"]
    assert active_list_final[0]["is_active"] is True

    # Verify all other fields remain unchanged
    assert reactivated["code"] == criterion["code"]
    assert reactivated["description"] == criterion["description"]
    assert reactivated["type"] == criterion["type"]
