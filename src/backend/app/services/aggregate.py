from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.core.config import get_settings
from src.backend.app.ingestion.month_ranges import (
    calendar_days_across_slices,
    utc_calendar_month_slices,
)


# Границы окна задаются в Python (UTC) и пробрасываются как bind-параметры.
_UPSERT_AGG_SQL = """
WITH sales_monthly_buckets AS (
    SELECT
        sm.store_id,
        sm.article,
        SUM(sm.qty)::numeric AS sales_qty_3m,
        COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'month', sm.month_start,
                    'qty', sm.qty
                )
                ORDER BY sm.month_start
            ),
            '[]'::jsonb
        ) AS monthly_sales
    FROM sales_monthly sm
    WHERE sm.month_start >= :first_month
      AND sm.month_start <= :last_month
      AND (
          CAST(:sales_store_id AS BIGINT) IS NULL
          OR sm.store_id = CAST(:sales_store_id AS BIGINT)
      )
    GROUP BY sm.store_id, sm.article
),
last_sales AS (
    SELECT sl.store_id, sl.article, MAX(sl.sold_at) AS last_sale_at
    FROM sale_line sl
    WHERE sl.sold_at >= :overall_from
      AND sl.sold_at < :overall_to_exclusive
      AND (
          CAST(:sales_store_id AS BIGINT) IS NULL
          OR sl.store_id = CAST(:sales_store_id AS BIGINT)
      )
    GROUP BY sl.store_id, sl.article
),
scope AS (
    SELECT st.id AS store_id, p.article 
    FROM store st
    CROSS JOIN product p
    WHERE (
        CAST(:sales_store_id AS BIGINT) IS NULL
        OR st.id = CAST(:sales_store_id AS BIGINT)
    )
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
        COALESCE(smb.monthly_sales, '[]'::jsonb) AS monthly_sales,
        COALESCE(smb.sales_qty_3m, 0) AS sales_qty_3m,
        CASE
            WHEN __WINDOW_DAYS__ > 0
            THEN COALESCE(smb.sales_qty_3m, 0) / (__WINDOW_DAYS__ * 1.0)
            ELSE 0
        END AS avg_daily_qty,
        ls.last_sale_at AS last_sale_at
    FROM scope s
    LEFT JOIN store ON store.id = s.store_id
    LEFT JOIN product ON product.article = s.article
    LEFT JOIN stock_current sc
        ON sc.store_id = s.store_id AND sc.article = s.article
    LEFT JOIN sales_monthly_buckets smb
        ON smb.store_id = s.store_id AND smb.article = s.article
    LEFT JOIN last_sales ls
        ON ls.store_id = s.store_id AND ls.article = s.article
)
INSERT INTO agg_store_product (
    store_id, article, store_name, product_name, unit,
    stock_balance, stock_captured_at,
    monthly_sales, sales_qty_3m,
    avg_daily_qty, last_sale_at, days_of_cover, refreshed_at
)
SELECT
    store_id, article, store_name, product_name, unit,
    stock_balance, stock_captured_at,
    monthly_sales, sales_qty_3m,
    avg_daily_qty, last_sale_at,
    CASE WHEN avg_daily_qty > 0 THEN stock_balance / avg_daily_qty ELSE NULL END,
    :now_ts
FROM combined
ON CONFLICT (store_id, article) DO UPDATE SET
    store_name = EXCLUDED.store_name,
    product_name = EXCLUDED.product_name,
    unit = EXCLUDED.unit,
    stock_balance = EXCLUDED.stock_balance,
    stock_captured_at = EXCLUDED.stock_captured_at,
    monthly_sales = EXCLUDED.monthly_sales,
    sales_qty_3m = EXCLUDED.sales_qty_3m,
    avg_daily_qty = EXCLUDED.avg_daily_qty,
    last_sale_at = EXCLUDED.last_sale_at,
    days_of_cover = EXCLUDED.days_of_cover,
    refreshed_at = EXCLUDED.refreshed_at
"""


_CLEANUP_AGG_SQL = """
DELETE FROM agg_store_product agg
WHERE (
      CAST(:sales_store_id AS BIGINT) IS NULL
      OR agg.store_id = CAST(:sales_store_id AS BIGINT)
)
  AND NOT EXISTS (
      SELECT 1 FROM product p
      WHERE p.article = agg.article
  )
"""


def _rollup_params(store_id: int | None) -> dict:
    settings = get_settings()
    months = int(settings.sales_months_back)
    if months < 1:
        raise ValueError("sales_months_back must be >= 1")
    slices = utc_calendar_month_slices(months)
    window_days = calendar_days_across_slices(slices)

    now = datetime.now(timezone.utc)
    return {
        "sales_store_id": store_id,
        "overall_from": slices[0].start,
        "overall_to_exclusive": slices[-1].end_exclusive,
        "first_month": slices[0].start.date(),
        "last_month": slices[-1].start.date(),
        "window_days": window_days,
        "now_ts": now,
    }


async def refresh_aggregate(
    session: AsyncSession,
    store_id: int | None = None,
) -> None:
    params = _rollup_params(store_id)
    wd = int(params["window_days"])
    upsert_sql = _UPSERT_AGG_SQL.replace("__WINDOW_DAYS__", str(wd))
    await session.execute(text(upsert_sql), params)
    await session.execute(text(_CLEANUP_AGG_SQL), params)
