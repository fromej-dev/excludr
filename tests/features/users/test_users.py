def test_users(admin_client, a_user, session):
    user = a_user()
    # Unique name so the contains-filter below cannot match random faker names
    user.name = "Zyxwvut Qwerty"
    session.add(user)
    session.commit()
    res = admin_client.get("api/v1/users")
    assert res.status_code == 200
    assert res.json()
    assert len(res.json()["data"]) == 2
    assert res.json()["meta"]["pagination"]["total_items"] == 2
    assert all("hashed_password" not in u for u in res.json()["data"])
    assert all("id" in u for u in res.json()["data"])

    [a_user() for _ in range(10)]

    res = admin_client.get("api/v1/users")
    assert res.status_code == 200
    assert res.json()
    assert len(res.json()["data"]) == 10
    assert res.json()["meta"]["pagination"]["total_items"] == 12

    # test filtering
    res = admin_client.get(
        f"api/v1/users?field=name&operator=contains&value={user.name[2:6]}"
    )
    assert res.status_code == 200
    assert res.json()
    assert len(res.json()["data"]) == 1
    assert res.json()["data"][0]["name"] == user.name
    assert res.json()["meta"]["pagination"]["total_items"] == 1


def test_users_not_authenticated(client, a_user):
    a_user()
    res = client.get("api/v1/users")
    assert res.status_code == 401
    assert res.json()["detail"] == "Not authenticated"


def test_users_not_allowed(auth_client, a_user):
    a_user()
    res = auth_client.get("api/v1/users")
    assert res.status_code == 403
    assert res.json()["detail"] == "Not enough permissions"


def test_user_by_id(admin_client, a_user):
    user = a_user()
    res = admin_client.get(f"api/v1/users/{user.id}")
    assert res.status_code == 200
    assert res.json()
    assert res.json()["id"] == user.id
    assert "hashed_password" not in res.json()


def test_user_by_id_not_found(admin_client):
    res = admin_client.get("api/v1/users/999999")
    assert res.status_code == 404


def test_get_user_me(auth_client):
    res = auth_client.get("api/v1/users/me")
    assert res.status_code == 200
    assert res.json()["email"]


def test_get_user_me_not_authenticated(client):
    res = client.get("api/v1/users/me")
    assert res.status_code == 401
    assert res.json()["detail"] == "Not authenticated"


def test_register_and_me_do_not_leak_password_hash(client, auth_client):
    res = auth_client.get("api/v1/users/me")
    assert "hashed_password" not in res.json()
    assert "id" in res.json()
