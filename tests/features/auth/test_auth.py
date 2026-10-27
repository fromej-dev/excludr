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


# --- Refresh tokens / token typing -------------------------------------------------


def _login(client, email, password="test_password"):
    return client.post(
        f"{settings.api_prefix}/auth/token",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def test_login_returns_refresh_token(client, a_user):
    user = a_user()
    body = _login(client, user.email).json()
    assert body["refresh_token"]
    assert body["refresh_token"] != body["access_token"]


def test_refresh_returns_new_working_access_token(client, a_user):
    user = a_user()
    refresh = _login(client, user.email).json()["refresh_token"]
    res = client.post(
        f"{settings.api_prefix}/auth/refresh", json={"refresh_token": refresh}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"] and body["refresh_token"]
    me = client.get(
        f"{settings.api_prefix}/users/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == user.email


def test_refresh_token_rejected_as_access_token(client, a_user):
    user = a_user()
    refresh = _login(client, user.email).json()["refresh_token"]
    res = client.get(
        f"{settings.api_prefix}/users/me",
        headers={"Authorization": f"Bearer {refresh}"},
    )
    assert res.status_code == 401


def test_access_token_rejected_by_refresh_endpoint(client, a_user):
    user = a_user()
    access = _login(client, user.email).json()["access_token"]
    res = client.post(
        f"{settings.api_prefix}/auth/refresh", json={"refresh_token": access}
    )
    assert res.status_code == 401


def test_refresh_with_garbage_token(client):
    res = client.post(
        f"{settings.api_prefix}/auth/refresh", json={"refresh_token": "nope"}
    )
    assert res.status_code == 401


def test_refresh_rejected_for_inactive_user(client, a_user, session):
    user = a_user()
    refresh = _login(client, user.email).json()["refresh_token"]
    user.is_active = False
    session.add(user)
    session.commit()
    res = client.post(
        f"{settings.api_prefix}/auth/refresh", json={"refresh_token": refresh}
    )
    assert res.status_code == 401


def test_expired_refresh_token_rejected(client, a_user):
    from datetime import timedelta

    from app.features.auth.services import create_refresh_token

    user = a_user()
    token = create_refresh_token(
        {"sub": user.email}, expires_delta=timedelta(seconds=-5)
    )
    res = client.post(
        f"{settings.api_prefix}/auth/refresh", json={"refresh_token": token}
    )
    assert res.status_code == 401


# --- Inactive users ------------------------------------------------------------------


def test_inactive_user_cannot_login(client, a_user, session):
    user = a_user()
    user.is_active = False
    session.add(user)
    session.commit()
    res = _login(client, user.email)
    assert res.status_code == 400


def test_inactive_user_token_rejected(client, a_user, token_for, session):
    user = a_user()
    token = token_for(user)
    user.is_active = False
    session.add(user)
    session.commit()
    res = client.get(
        f"{settings.api_prefix}/users/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 401


# --- Login rate limiting -------------------------------------------------------------


def test_login_rate_limited_after_repeated_failures(client, a_user, monkeypatch):
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 3)
    user = a_user()
    for _ in range(3):
        assert _login(client, user.email, "wrong").status_code == 400
    res = _login(client, user.email, "wrong")
    assert res.status_code == 429
    assert "Retry-After" in res.headers
    # Even the right password is blocked while limited
    assert _login(client, user.email).status_code == 429


def test_login_rate_limit_is_per_email(client, a_user, monkeypatch):
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 2)
    a, b = a_user(), a_user()
    for _ in range(2):
        _login(client, a.email, "wrong")
    assert _login(client, a.email, "wrong").status_code == 429
    assert _login(client, b.email).status_code == 200


def test_successful_login_resets_counter(client, a_user, monkeypatch):
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 3)
    user = a_user()
    for _ in range(2):
        _login(client, user.email, "wrong")
    assert _login(client, user.email).status_code == 200
    for _ in range(2):
        assert _login(client, user.email, "wrong").status_code == 400


def test_rate_limiter_window_expires():
    from app.core.rate_limit import SlidingWindowRateLimiter

    now = [1000.0]
    limiter = SlidingWindowRateLimiter(clock=lambda: now[0])
    limiter.record("k", window_seconds=10)
    limiter.record("k", window_seconds=10)
    assert limiter.is_limited("k", max_attempts=2, window_seconds=10)
    now[0] += 11
    assert not limiter.is_limited("k", max_attempts=2, window_seconds=10)
