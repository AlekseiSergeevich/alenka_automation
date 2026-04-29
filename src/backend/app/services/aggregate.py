from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.core.config import get_settings


# All window boundaries are computed in Python as aware datetimes and passed as
# bound parameters — avoids asyncpg/PostgreSQL quirks with `:now - INTERVAL ...`.
_UPSERT_AGG_SQL = """
WITH sales_window AS (
    SELECT
        sl.store_id,
        sl.article,
        SUM(sl.qty) FILTER (WHERE sl.sold_at >= :from_30d) AS qty_30d,
        SUM(sl.qty) FILTER (WHERE sl.sold_at >= :from_90d) AS qty_90d,
        SUM(sl.qty) FILTER (WHERE sl.sold_at >= :from_window) AS qty_window,
        MAX(sl.sold_at) AS last_sale_at
    FROM sale_line sl
    WHERE sl.sold_at >= :from_window
      AND COALESCE(CAST(:store_id AS BIGINT), sl.store_id) = sl.store_id
    GROUP BY sl.store_id, sl.article
),
scope AS (
    SELECT store_id, article FROM stock_current
    WHERE COALESCE(CAST(:store_id AS BIGINT), store_id) = store_id
    UNION
    SELECT store_id, article FROM sales_window
),
combined AS (
    SELECT
        s.store_id,
        s.article,
        COALESCE(store.name, '') AS store_name,
        COALESCE(product.name, '') AS product_name,
        COALESCE(product.unit, '') AS unit,
        COALESCE(sc.balance, 0) AS stock_balance,
        sc.captured_at AS stock_captured_at,
        COALESCE(sw.qty_30d, 0) AS sales_qty_30d,
        COALESCE(sw.qty_90d, 0) AS sales_qty_90d,
        COALESCE(sw.qty_window, 0) AS sales_qty_window,
        sw.last_sale_at AS last_sale_at,
        CASE
            WHEN __WINDOW_DAYS__ > 0
            THEN COALESCE(sw.qty_window, 0) / (__WINDOW_DAYS__ * 1.0)
            ELSE 0
        END AS avg_daily_qty
    FROM scope s
    LEFT JOIN store ON store.id = s.store_id
    LEFT JOIN product ON product.article = s.article
    LEFT JOIN stock_current sc ON sc.store_id = s.store_id AND sc.article = s.article
    LEFT JOIN sales_window sw ON sw.store_id = s.store_id AND sw.article = s.article
)
INSERT INTO agg_store_product (
    store_id, article, store_name, product_name, unit,
    stock_balance, stock_captured_at,
    sales_qty_30d, sales_qty_90d, sales_qty_window,
    avg_daily_qty, last_sale_at, days_of_cover, refreshed_at
)
SELECT
    store_id, article, store_name, product_name, unit,
    stock_balance, stock_captured_at,
    sales_qty_30d, sales_qty_90d, sales_qty_window,
    avg_daily_qty, last_sale_at,
    CASE WHEN avg_daily_qty > 0 THEN stock_balance / avg_daily_qty ELSE NULL END,
    :now
FROM combined
ON CONFLICT (store_id, article) DO UPDATE SET
    store_name = EXCLUDED.store_name,
    product_name = EXCLUDED.product_name,
    unit = EXCLUDED.unit,
    stock_balance = EXCLUDED.stock_balance,
    stock_captured_at = EXCLUDED.stock_captured_at,
    sales_qty_30d = EXCLUDED.sales_qty_30d,
    sales_qty_90d = EXCLUDED.sales_qty_90d,
    sales_qty_window = EXCLUDED.sales_qty_window,
    avg_daily_qty = EXCLUDED.avg_daily_qty,
    last_sale_at = EXCLUDED.last_sale_at,
    days_of_cover = EXCLUDED.days_of_cover,
    refreshed_at = EXCLUDED.refreshed_at
"""


_CLEANUP_AGG_SQL = """
DELETE FROM agg_store_product agg
WHERE COALESCE(CAST(:store_id AS BIGINT), agg.store_id) = agg.store_id
  AND NOT EXISTS (
      SELECT 1 FROM stock_current sc
      WHERE sc.store_id = agg.store_id AND sc.article = agg.article
  )
  AND NOT EXISTS (
      SELECT 1 FROM sale_line sl
      WHERE sl.store_id = agg.store_id
        AND sl.article = agg.article
        AND sl.sold_at >= :from_window
  )
"""


def _window_bounds() -> tuple[datetime, datetime, datetime, datetime, int]:
    settings = get_settings()
    wd = int(settings.sales_window_days)
    if not (1 <= wd <= 3660):
        raise ValueError("sales_window_days must be between 1 and 3660")
    now = datetime.now(timezone.utc)
    from_30d = now - timedelta(days=30)
    from_90d = now - timedelta(days=90)
    from_window = now - timedelta(days=wd)
    return now, from_30d, from_90d, from_window, wd


async def refresh_aggregate(
    session: AsyncSession,
    store_id: int | None = None,
) -> None:
    """Recompute `agg_store_product` from sale_line + stock_current.

    When `store_id` is passed the recomputation is scoped to that store; in
    that case rows for other stores are left untouched. A global call refreshes
    everything. Rows that no longer have any corresponding stock or sales
    inside the rolling window are dropped to keep the view tidy.
    """

    now, from_30d, from_90d, from_window, wd = _window_bounds()
    upsert_sql = _UPSERT_AGG_SQL.replace("__WINDOW_DAYS__", str(wd))
    params = {
        "store_id": store_id,
        "now": now,
        "from_30d": from_30d,
        "from_90d": from_90d,
        "from_window": from_window,
    }
    await session.execute(text(upsert_sql), params)
    await session.execute(text(_CLEANUP_AGG_SQL), params)
