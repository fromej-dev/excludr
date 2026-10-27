import logging

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app, warn_if_weak_secret


def test_cors_allows_configured_origin():
    origin = get_settings().cors_origins[0]
    res = TestClient(app).options(
        "/ping",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert res.headers["access-control-allow-origin"] == origin


def test_cors_rejects_unknown_origin():
    res = TestClient(app).options(
        "/ping",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in res.headers


def test_default_cors_origins():
    assert Settings(secret_key="x").cors_origins == ["http://localhost:5173"]


def test_short_secret_key_logs_warning(caplog):
    with caplog.at_level(logging.WARNING):
        warn_if_weak_secret(Settings(secret_key="short"))
    assert "SECRET_KEY" in caplog.text


def test_long_secret_key_no_warning(caplog):
    with caplog.at_level(logging.WARNING):
        warn_if_weak_secret(Settings(secret_key="k" * 32))
    assert "SECRET_KEY" not in caplog.text


def test_no_hardcoded_admin_email_default():
    assert not hasattr(Settings(secret_key="x"), "admin_email")
