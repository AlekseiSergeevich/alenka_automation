"""Юнит-тесты логики бланка заказа без БД."""

from __future__ import annotations

from datetime import datetime, timezone

from src.backend.app.services.order_blank_catalog import (
    OrderBlankReminderState,
    utc_month_start,
)


def test_utc_month_start_january() -> None:
    ref = datetime(2026, 3, 15, 14, 30, tzinfo=timezone.utc)
    start = utc_month_start(ref)
    assert start == datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)


def test_order_blank_attention_when_empty() -> None:
    hint = OrderBlankReminderState(
        product_count=0,
        catalog_empty=True,
        needs_monthly_upload=True,
        last_success_applied_at=None,
    )
    assert hint.needs_order_blank_attention is True


def test_order_blank_attention_when_catalog_nonempty_but_monthly_missing() -> None:
    hint = OrderBlankReminderState(
        product_count=10,
        catalog_empty=False,
        needs_monthly_upload=True,
        last_success_applied_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    assert hint.needs_order_blank_attention is True


def test_order_blank_attention_ok_when_monthly_done() -> None:
    hint = OrderBlankReminderState(
        product_count=10,
        catalog_empty=False,
        needs_monthly_upload=False,
        last_success_applied_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    assert hint.needs_order_blank_attention is False
