from app.core.config import get_settings

settings = get_settings()


def test_register(client, faker):
    data = {"email": faker.email(), "name": faker.name(), "password": faker.password()}
    res = client.post(f"{settings.api_prefix}/auth/register", json=data)
    assert res.status_code == 201
    assert res.json()["email"] == data["email"]


def test_login(client, a_user):
    user = a_user()
    data = {"username": user.email, "password": "test_password"}
    res = client.post(
        f"{settings.api_prefix}/auth/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 200
    assert res.json()["access_token"]
