"""Health/readiness and router feature flags."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.backend.app.core.config import get_settings
from src.backend.app.db.session import get_engine, get_sessionmaker


def test_health_ready_returns_status() -> None:
    from src.backend.app.main import app

    with TestClient(app) as client:
        r = client.get("/health/ready")
    assert r.status_code in (200, 503)
    body = r.json()
    if r.status_code == 200:
        assert body.get("status") == "ready"
    else:
        assert "error" in body


def test_saby_router_disabled_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_SABY_DEBUG_API", "false")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    from src.backend.app.main import create_app

    with TestClient(create_app()) as client:
        r = client.get("/api/v1/saby/status")
    assert r.status_code == 404


def test_http_error_envelope() -> None:
    from src.backend.app.main import app

    with TestClient(app) as client:
        r = client.get("/api/v1/overview")
        assert r.status_code == 200
        r2 = client.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
    assert r2.status_code == 400
    body = r2.json()
    assert "error" in body
    assert body["error"]["code"] == "HTTP_400"
