"""Сборка DTO строки overview из ORM-бакета без БД."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from types import SimpleNamespace

from src.backend.app.api.v1.endpoints.overview import AggRow


def test_agg_row_from_plain_namespace() -> None:
    fake = SimpleNamespace(
        store_id=1,
        article="SKU-1",
        store_name="S",
        product_name="P",
        unit="шт",
        stock_balance=Decimal("10"),
        stock_captured_at=None,
        monthly_sales=[
            {"month": "2026-04-01", "qty": "2", "orders_count": 1},
            {"month": "2026-05-01", "qty": 3},
        ],
        sales_qty_3m=Decimal("5"),
        avg_daily_qty=Decimal("0.05"),
        last_sale_at=datetime.now(timezone.utc),
        days_of_cover=Decimal("100"),
        refreshed_at=datetime.now(timezone.utc),
    )

    row = AggRow.from_agg(fake)
    assert row.sales_qty_3m == Decimal("5")
    assert len(row.monthly_sales) == 2
