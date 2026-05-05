"""Юнит-тесты без Saby и без Postgres: месяцы и разбор ответов Saby."""

from __future__ import annotations

from datetime import date, datetime, timezone

from src.backend.app.ingestion.month_ranges import (
    calendar_days_across_slices,
    utc_calendar_month_slices,
)
from src.backend.app.integrations.saby.schemas import (
    OrderLinePayload,
    ProductBalanceSchema,
    RetailOrderPayload,
    iter_nomenclature_dicts,
    iter_order_dicts,
    iter_sales_point_dicts,
)


def test_utc_calendar_month_slices_three_months_may_2026() -> None:
    now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
    slices = utc_calendar_month_slices(3, now)
    assert len(slices) == 3
    assert slices[0].start == datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert slices[-1].end_exclusive == datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    days = calendar_days_across_slices(slices)
    assert days >= 89


def test_iter_sales_points_prefers_salespoints_key() -> None:
    items = iter_sales_point_dicts({"salesPoints": [{"id": 1, "name": "A"}]})
    assert len(items) == 1 and items[0]["id"] == 1


def test_iter_orders_prefers_orders_key() -> None:
    items = iter_order_dicts({"orders": [{"id": 42}]})
    assert len(items) == 1 and items[0]["id"] == 42


def test_iter_nomenclatures_prefers_key() -> None:
    items = iter_nomenclature_dicts({"nomenclatures": [{"article": "x"}]})
    assert len(items) == 1 and items[0]["article"] == "x"


def test_retail_order_payload_reads_datetime_alias() -> None:
    payload = RetailOrderPayload.model_validate({"datetime": "2026-03-02", "lines": [{}]})
    assert payload.order_lines_raw() == [{}]


def test_product_balance_fallbacks_nom_number() -> None:
    row = ProductBalanceSchema.model_validate(
        {"article": None, "balance": None, "nomNumber": "X4596954"}
    )
    assert row.article == "X4596954"
    assert row.balance == ""
    assert row.nom_number == "X4596954"


def test_product_balance_keeps_vendor_article_and_nom() -> None:
    row = ProductBalanceSchema.model_validate(
        {"article": "СР12667", "nomNumber": "X4924446", "balance": "1.5"}
    )
    assert row.article == "СР12667"
    assert row.nom_number == "X4924446"
    assert row.balance == "1.5"


def test_retail_prefers_sale_nomenclatures_over_lines_empty() -> None:
    payload = RetailOrderPayload.model_validate(
        {
            "lines": [],
            "SaleNomenclatures": [
                {"NomenclatureNumber": "Z1", "Quantity": 1.25, "Name": "Candy"}
            ],
        }
    )
    raw = payload.order_lines_raw()
    assert len(raw) == 1
    line = OrderLinePayload.model_validate(raw[0])
    assert line.article == "Z1"
    assert line.count == 1.25


def test_month_starts_dates() -> None:
    slices = utc_calendar_month_slices(
        2, datetime(2026, 1, 15, tzinfo=timezone.utc)
    )
    assert slices[0].start.date() == date(2025, 12, 1)
    assert slices[1].start.date() == date(2026, 1, 1)
