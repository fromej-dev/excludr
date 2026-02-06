"""
E2E integration tests for the authentication flow.

These tests verify the complete authentication lifecycle including:
- User registration
- Login (token acquisition)
- Protected endpoint access
- Error handling for various authentication scenarios
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings

settings = get_settings()
API = settings.api_prefix


@pytest.mark.e2e
def test_register_and_login_flow(client: TestClient, faker):
    """
    Test the complete registration and login flow.

    Steps:
    1. Register a new user
    2. Login with those credentials
    3. Verify token is returned
    4. Use token to access /users/me
    """
    # Register a new user
    registration_data = {
        "email": faker.email(),
        "name": faker.name(),
        "password": "secure_password_123",
    }

    register_response = client.post(
        f"{API}/auth/register",
        json=registration_data,
    )

    assert register_response.status_code == 201
    user_data = register_response.json()
    assert user_data["email"] == registration_data["email"]
    assert user_data["name"] == registration_data["name"]
    assert "password" not in user_data
    assert "hashed_password" not in user_data

    # Login with the registered credentials
    login_data = {
        "username": registration_data["email"],
        "password": registration_data["password"],
    }

    token_response = client.post(
        f"{API}/auth/token",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert token_response.status_code == 200
    token_data = token_response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    access_token = token_data["access_token"]

    # Use the token to access protected endpoint
    me_response = client.get(
        f"{API}/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["email"] == registration_data["email"]
    assert me_data["name"] == registration_data["name"]
    assert me_data["is_active"] is True
    assert me_data["is_superuser"] is False
    assert me_data["is_verified"] is False


@pytest.mark.e2e
def test_register_duplicate_email(client: TestClient, faker):
    """
    Test that registering with a duplicate email returns an error.

    Steps:
    1. Register a user
    2. Try to register again with the same email
    3. Expect error response
    """
    email = faker.email()
    registration_data = {
        "email": email,
        "name": faker.name(),
        "password": "password123",
    }

    # First registration should succeed
    first_response = client.post(
        f"{API}/auth/register",
        json=registration_data,
    )
    assert first_response.status_code == 201

    # Second registration with same email should fail
    duplicate_data = {
        "email": email,  # Same email
        "name": faker.name(),  # Different name
        "password": "different_password",
    }

    second_response = client.post(
        f"{API}/auth/register",
        json=duplicate_data,
    )

    assert second_response.status_code in [400, 409, 422]  # Bad request or conflict
    assert "detail" in second_response.json()


@pytest.mark.e2e
def test_login_wrong_password(client: TestClient, a_user):
    """
    Test that logging in with wrong password fails.

    Steps:
    1. Create a user (password is "test_password")
    2. Attempt login with wrong password
    3. Expect 400 error
    """
    user = a_user()

    login_data = {
        "username": user.email,
        "password": "wrong_password",
    }

    response = client.post(
        f"{API}/auth/token",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 400
    assert "detail" in response.json()
    assert "incorrect" in response.json()["detail"].lower()


@pytest.mark.e2e
def test_login_nonexistent_user(client: TestClient, faker):
    """
    Test that logging in with non-existent email fails.

    Steps:
    1. Attempt login with email that doesn't exist
    2. Expect 400 error
    """
    login_data = {
        "username": faker.email(),  # Non-existent email
        "password": "any_password",
    }

    response = client.post(
        f"{API}/auth/token",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 400
    assert "detail" in response.json()
    assert "incorrect" in response.json()["detail"].lower()


@pytest.mark.e2e
def test_access_protected_endpoint_without_token(client: TestClient):
    """
    Test that accessing protected endpoint without token fails.

    Steps:
    1. Hit /users/me without Authorization header
    2. Expect 401 Unauthorized
    """
    response = client.get(f"{API}/users/me")

    assert response.status_code == 401
    assert "detail" in response.json()
    assert "not authenticated" in response.json()["detail"].lower()


@pytest.mark.e2e
def test_access_protected_endpoint_with_invalid_token(client: TestClient):
    """
    Test that accessing protected endpoint with invalid token fails.

    Steps:
    1. Hit /users/me with garbage token
    2. Expect 401 Unauthorized
    """
    response = client.get(
        f"{API}/users/me",
        headers={"Authorization": "Bearer invalid_garbage_token_12345"},
    )

    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.e2e
def test_register_invalid_data(client: TestClient, faker):
    """
    Test that registering with missing or invalid fields fails.

    Steps:
    1. Try to register with missing required fields
    2. Expect 422 Unprocessable Entity
    """
    # Missing email
    invalid_data_no_email = {
        "name": faker.name(),
        "password": "password123",
    }

    response = client.post(
        f"{API}/auth/register",
        json=invalid_data_no_email,
    )

    assert response.status_code == 422
    assert "detail" in response.json()

    # Missing password
    invalid_data_no_password = {
        "email": faker.email(),
        "name": faker.name(),
    }

    response = client.post(
        f"{API}/auth/register",
        json=invalid_data_no_password,
    )

    assert response.status_code == 422
    assert "detail" in response.json()

    # Missing name
    invalid_data_no_name = {
        "email": faker.email(),
        "password": "password123",
    }

    response = client.post(
        f"{API}/auth/register",
        json=invalid_data_no_name,
    )

    assert response.status_code == 422
    assert "detail" in response.json()

    # Empty JSON
    response = client.post(
        f"{API}/auth/register",
        json={},
    )

    assert response.status_code == 422
    assert "detail" in response.json()


@pytest.mark.e2e
def test_full_auth_lifecycle(client: TestClient, faker):
    """
    Test the complete authentication lifecycle from registration to access.

    This comprehensive test verifies:
    1. User registration
    2. Login to obtain token
    3. Access protected endpoint with token
    4. Verify all user data matches throughout the flow
    """
    # Step 1: Register a new user
    user_credentials = {
        "email": faker.email(),
        "name": faker.name(),
        "password": "my_secure_password_789",
    }

    register_response = client.post(
        f"{API}/auth/register",
        json=user_credentials,
    )

    assert register_response.status_code == 201, f"Registration failed: {register_response.json()}"

    registered_user = register_response.json()
    assert registered_user["email"] == user_credentials["email"]
    assert registered_user["name"] == user_credentials["name"]
    assert registered_user["is_active"] is True
    assert registered_user["is_superuser"] is False
    assert registered_user["is_verified"] is False
    assert "created_at" in registered_user
    assert "updated_at" in registered_user
    assert "password" not in registered_user
    assert "hashed_password" not in registered_user

    # Step 2: Login to obtain access token
    login_credentials = {
        "username": user_credentials["email"],
        "password": user_credentials["password"],
    }

    login_response = client.post(
        f"{API}/auth/token",
        data=login_credentials,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert login_response.status_code == 200, f"Login failed: {login_response.json()}"

    token_data = login_response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert len(token_data["access_token"]) > 0

    access_token = token_data["access_token"]

    # Step 3: Access protected endpoint with the token
    me_response = client.get(
        f"{API}/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert me_response.status_code == 200, f"Failed to access /users/me: {me_response.json()}"

    current_user = me_response.json()

    # Step 4: Verify all user data matches
    assert current_user["email"] == user_credentials["email"]
    assert current_user["name"] == user_credentials["name"]
    assert current_user["is_active"] is True
    assert current_user["is_superuser"] is False
    assert current_user["is_verified"] is False

    # Verify data consistency between registration and /me endpoint
    assert current_user["email"] == registered_user["email"]
    assert current_user["name"] == registered_user["name"]
    assert current_user["is_active"] == registered_user["is_active"]
    assert current_user["is_superuser"] == registered_user["is_superuser"]
    assert current_user["is_verified"] == registered_user["is_verified"]

    # Verify sensitive data is not exposed
    assert "password" not in current_user
    assert "hashed_password" not in current_user

    # Step 5: Verify token can be reused for subsequent requests
    second_me_response = client.get(
        f"{API}/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert second_me_response.status_code == 200
    assert second_me_response.json()["email"] == user_credentials["email"]
