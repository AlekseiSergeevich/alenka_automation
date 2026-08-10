"""Календарные интервалы для синхронизации продаж помесячно (UTC)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import NamedTuple


class MonthSlice(NamedTuple):
    start: datetime
    end_exclusive: datetime


def _subtract_months(year: int, month: int, delta: int) -> tuple[int, int]:
    m = month - delta
    y = year
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return y, m


def utc_month_start(year: int, month: int) -> datetime:
    return datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)


def utc_next_month_start(year: int, month: int) -> datetime:
    if month == 12:
        return datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def utc_calendar_month_slices(
    months_back: int,
    now: datetime | None = None,
) -> list[MonthSlice]:
    """Последние `months_back` полных календарных месяцев в UTC, включая текущий.

    Каждый интервал: [первое число месяца 00:00 UTC, первое число след. месяца 00:00 UTC).
    От старых месяцев к новым.
    """

    if months_back < 1:
        raise ValueError("months_back must be >= 1")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    y_end, m_end = now.year, now.month
    slices: list[MonthSlice] = []

    for i in range(months_back - 1, -1, -1):
        y, m = _subtract_months(y_end, m_end, i)
        start = utc_month_start(y, m)
        end_exc = utc_next_month_start(y, m)
        slices.append(MonthSlice(start=start, end_exclusive=end_exc))

    return slices


def calendar_days_across_slices(slices: list[MonthSlice]) -> int:
    """Суммарная «длина» интервалов в днях (для средних продаж за период)."""

    total = sum(max(1, (s.end_exclusive - s.start).days) for s in slices)
    return max(1, total)


def month_starts_from_slices(slices: list[MonthSlice]) -> list[date]:
    return sorted({s.start.date() for s in slices})
