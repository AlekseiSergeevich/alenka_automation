"""Смоук-тесты API (нужен доступ к БД из настроек, см. src/backend/.env)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.backend.app.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_overview(client: TestClient) -> None:
    r = client.get("/api/v1/overview")
    assert r.status_code == 200
    body = r.json()
    assert "meta" in body and "items" in body


def test_stores(client: TestClient) -> None:
    r = client.get("/api/v1/stores")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_sync_status(client: TestClient) -> None:
    r = client.get("/api/v1/sync/status")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
