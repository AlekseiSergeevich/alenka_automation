"""Security tests with AUTH_ENABLED (isolated app factory per fixture)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.backend.app.core.config import get_settings
from src.backend.app.db.session import get_engine, get_sessionmaker

# Precomputed bcrypt hashes (passwords: "secret" / "viewerpass")
_ADMIN_HASH = (
    "$2b$12$4GEbtf.3HlZShnCAwz2HveqY1xUUCDIg3ZwdRhkHByxAgzAglrjGO"
)
_VIEWER_HASH = (
    "$2b$12$6zGnvlycQFONuo531UOVBuK5pnZLxf2gee56JQuCoTAKVZhgAwtPS"
)


@pytest.fixture
def client_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-key-32chars!!")
    monkeypatch.setenv("AUTH_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("AUTH_ADMIN_PASSWORD_HASH", _ADMIN_HASH)
    monkeypatch.setenv("AUTH_VIEWER_USERNAME", "viewer")
    monkeypatch.setenv("AUTH_VIEWER_PASSWORD_HASH", _VIEWER_HASH)
    monkeypatch.setenv("ENABLE_SABY_DEBUG_API", "true")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    from src.backend.app.main import create_app

    return TestClient(create_app())


def test_overview_requires_auth(client_auth_enabled: TestClient) -> None:
    r = client_auth_enabled.get("/api/v1/overview")
    assert r.status_code == 401
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "HTTP_401"


def test_login_and_cookie_access(client_auth_enabled: TestClient) -> None:
    r = client_auth_enabled.post(
        "/api/v1/auth/login",
        json={"username": "viewer", "password": "viewerpass"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["role"] == "viewer"
    assert "access_token" in data

    r2 = client_auth_enabled.get("/api/v1/auth/me", cookies=r.cookies)
    assert r2.status_code == 200
    assert r2.json()["username"] == "viewer"


def test_bearer_token_access(client_auth_enabled: TestClient) -> None:
    r = client_auth_enabled.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "secret"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    r2 = client_auth_enabled.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["role"] == "admin"


def test_viewer_cannot_sync_bootstrap(client_auth_enabled: TestClient) -> None:
    r = client_auth_enabled.post(
        "/api/v1/auth/login",
        json={"username": "viewer", "password": "viewerpass"},
    )
    assert r.status_code == 200
    r2 = client_auth_enabled.post(
        "/api/v1/sync/bootstrap?mode=force",
        cookies=r.cookies,
    )
    assert r2.status_code == 403


def test_saby_requires_admin(client_auth_enabled: TestClient) -> None:
    r = client_auth_enabled.post(
        "/api/v1/auth/login",
        json={"username": "viewer", "password": "viewerpass"},
    )
    r2 = client_auth_enabled.get("/api/v1/saby/status", cookies=r.cookies)
    assert r2.status_code == 403
