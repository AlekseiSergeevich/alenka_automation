"""Тесты: price_list_id из Saby для номенклатуры и кэш в store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.backend.app.integrations.saby.schemas import first_price_list_id, iter_price_list_dicts
from src.backend.app.ingestion.stock import (
    ensure_store_price_list_id,
    sync_stock,
    sync_stock_for_existing_products,
)


def test_iter_price_list_dicts_price_lists_key() -> None:
    rows = iter_price_list_dicts({"priceLists": [{"id": 1, "name": "A"}]})
    assert len(rows) == 1
    assert rows[0]["id"] == 1


def test_first_price_list_id_from_various_payloads() -> None:
    assert first_price_list_id({"priceLists": [{"id": 123}]}) == 123
    assert first_price_list_id({"items": [{"Id": 5}]}) == 5
    assert first_price_list_id({"list": [{"id": "7"}]}) == 7
    assert first_price_list_id({}) is None


@pytest.mark.asyncio
async def test_ensure_store_price_list_id_uses_cache() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=42)
    client = AsyncMock()
    out = await ensure_store_price_list_id(session, client, 10)
    assert out == 42
    client.price_list.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_store_price_list_id_fetches_and_persists() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    client = AsyncMock()
    client.price_list = AsyncMock(return_value={"priceLists": [{"id": 777}]})
    out = await ensure_store_price_list_id(session, client, 3)
    assert out == 777
    client.price_list.assert_awaited_once()
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_stock_passes_price_list_id_to_list_products() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=999)
    list_calls: list[dict] = []

    async def list_products(**kwargs: object) -> dict:
        list_calls.append(dict(kwargs))
        return {"nomenclatures": []}

    client = AsyncMock()
    client.list_products = AsyncMock(side_effect=list_products)

    await sync_stock(session, client, 1)

    assert len(list_calls) >= 1
    assert list_calls[0].get("price_list_id") == 999


@pytest.mark.asyncio
async def test_sync_stock_for_existing_products_passes_price_list_id() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=88)

    articles_result = MagicMock()
    articles_result.all = MagicMock(return_value=[("P1",)])
    session.execute = AsyncMock(side_effect=[articles_result, MagicMock()])

    list_calls: list[dict] = []

    async def list_products(**kwargs: object) -> dict:
        list_calls.append(dict(kwargs))
        return {"nomenclatures": []}

    client = AsyncMock()
    client.list_products = AsyncMock(side_effect=list_products)

    n = await sync_stock_for_existing_products(session, client, 2)
    assert n == 0
    assert list_calls and list_calls[0].get("price_list_id") == 88
