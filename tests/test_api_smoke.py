"""Смоук-тесты API (нужен доступ к БД из настроек, см. src/backend/.env)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.backend.app.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def _get_db_route_or_skip(api: TestClient, path: str):
    """Корневые тестовые машины без Postgres должны просто skipped, а не падать."""

    try:
        return api.get(path)
    except OSError as exc:
        pytest.skip(f"PostgreSQL недоступен для смоук-теста: {exc}")


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_overview(client: TestClient) -> None:
    r = _get_db_route_or_skip(client, "/api/v1/overview")
    assert r.status_code == 200
    body = r.json()
    assert "meta" in body and "items" in body
    if body["items"]:
        assert "monthly_sales" in body["items"][0]
        assert "sales_qty_3m" in body["items"][0]


def test_stores(client: TestClient) -> None:
    r = _get_db_route_or_skip(client, "/api/v1/stores")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_sync_status(client: TestClient) -> None:
    r = _get_db_route_or_skip(client, "/api/v1/sync/status")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
