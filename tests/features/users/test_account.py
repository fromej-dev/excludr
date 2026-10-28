"""Tests for a user managing their own account (``/users/me``)."""

from app.core.security import verify_password

ME = "api/v1/users/me"


def test_update_name(auth_as):
    client, user = auth_as()
    res = client.patch(ME, json={"name": "  Ada Lovelace "})
    assert res.status_code == 200
    assert res.json()["name"] == "Ada Lovelace"
    assert client.get(ME).json()["name"] == "Ada Lovelace"


def test_update_name_rejects_blank(auth_as):
    client, _ = auth_as()
    assert client.patch(ME, json={"name": "   "}).status_code == 422
    assert client.patch(ME, json={"name": ""}).status_code == 422


def test_account_changes_need_login(client):
    assert client.patch(ME, json={"name": "x"}).status_code == 401
    assert (
        client.put(
            f"{ME}/password", json={"current_password": "a", "new_password": "b" * 8}
        ).status_code
        == 401
    )


def test_change_password(auth_as, session):
    client, user = auth_as()
    res = client.put(
        f"{ME}/password",
        json={"current_password": "test_password", "new_password": "new-secret-1"},
    )
    assert res.status_code == 204
    session.refresh(user)
    assert verify_password("new-secret-1", user.hashed_password)

    login = client.post(
        "api/v1/auth/token", data={"username": user.email, "password": "new-secret-1"}
    )
    assert login.status_code == 200


def test_change_password_checks_current_password(auth_as, session):
    client, user = auth_as()
    res = client.put(
        f"{ME}/password",
        json={"current_password": "wrong", "new_password": "new-secret-1"},
    )
    assert res.status_code == 400
    session.refresh(user)
    assert verify_password("test_password", user.hashed_password)


def test_change_password_requires_minimum_length(auth_as):
    client, _ = auth_as()
    res = client.put(
        f"{ME}/password",
        json={"current_password": "test_password", "new_password": "short"},
    )
    assert res.status_code == 422


def test_wrong_current_password_is_throttled(auth_as):
    client, _ = auth_as()
    body = {"current_password": "wrong", "new_password": "new-secret-1"}
    codes = [client.put(f"{ME}/password", json=body).status_code for _ in range(11)]
    assert codes[-1] == 429
    assert set(codes[:-1]) <= {400, 429}


def test_change_email_returns_working_tokens(auth_as, session):
    client, user = auth_as()
    old_email = user.email
    res = client.put(
        f"{ME}/email",
        json={"email": "new.address@example.org", "current_password": "test_password"},
    )
    assert res.status_code == 200
    tokens = res.json()
    session.refresh(user)
    assert user.email == "new.address@example.org"

    # The old token names the old email, so it no longer works...
    assert client.get(ME).status_code == 401
    # ...but the new one does
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    assert client.get(ME).json()["email"] == "new.address@example.org"
    login = client.post(
        "api/v1/auth/token", data={"username": old_email, "password": "test_password"}
    )
    assert login.status_code == 400


def test_change_email_rejects_taken_address(auth_as, a_user):
    other = a_user()
    client, _ = auth_as()
    res = client.put(
        f"{ME}/email", json={"email": other.email, "current_password": "test_password"}
    )
    assert res.status_code == 409


def test_change_email_checks_password_and_format(auth_as):
    client, _ = auth_as()
    wrong_password = client.put(
        f"{ME}/email", json={"email": "a@example.org", "current_password": "wrong"}
    )
    assert wrong_password.status_code == 400
    bad_email = client.put(
        f"{ME}/email",
        json={"email": "not-an-email", "current_password": "test_password"},
    )
    assert bad_email.status_code == 422
