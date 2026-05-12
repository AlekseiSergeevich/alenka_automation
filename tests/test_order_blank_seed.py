"""Тесты безопасного seed бланка без БД (моки сессии)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.backend.app.ingestion.order_blank import (
    OrderBlankSeedStatus,
    seed_products_from_order_blank_if_empty,
)


@pytest.mark.asyncio
async def test_seed_skips_when_product_nonempty() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=5)

    result = await seed_products_from_order_blank_if_empty(
        session,
        None,
        project_root=MagicMock(),
    )

    assert result.status == OrderBlankSeedStatus.skipped_nonempty
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_seed_skips_when_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=0)

    monkeypatch.setattr(
        "src.backend.app.ingestion.order_blank.find_latest_order_blank_xls",
        lambda project_root: None,
    )

    result = await seed_products_from_order_blank_if_empty(
        session,
        None,
        project_root=MagicMock(),
    )

    assert result.status == OrderBlankSeedStatus.skipped_no_file
