import pandas as pd
import numpy as np
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path

from src.backend.app.models.sales_monthly import SalesMonthly
from src.backend.app.models.stock import StockCurrent
from src.backend.app.models.order_blank_upload import OrderBlankUpload
from src.backend.app.models.order_blank_item import OrderBlankItem
from src.backend.app.services.order_blank_catalog import STATUS_SUCCESS

async def generate_forecast_for_store(session: AsyncSession, store_id: int):
    now = datetime.now(timezone.utc)
    current_month_start = pd.Timestamp(now.year, now.month, 1).date()

    # 1. Достаем историю продаж (исключая текущий неполный месяц)
    stmt = (
        select(SalesMonthly)
        .where(SalesMonthly.store_id == store_id)
        .where(SalesMonthly.month_start < current_month_start)
    )
    result = await session.execute(stmt)
    sales = result.scalars().all()

    if not sales:
        return {"error": "Нет исторических данных по этому магазину"}

    # 2. Конвертируем в Pandas DataFrame
    df = pd.DataFrame([{
        "sku": s.article,
        "qty": float(s.qty),
        "month": pd.to_datetime(s.month_start)
    } for s in sales])

    # 3. Считаем скользящее среднее (MA3)
    df = df.sort_values(["sku", "month"]).reset_index(drop=True)
    df["ma3"] = df.groupby("sku")["qty"].transform(lambda x: x.rolling(3, min_periods=1).mean())

    # 4. Оставляем только последнюю строку для каждого SKU
    forecast_df = df.groupby("sku").tail(1).copy()

    if forecast_df.empty:
        return []

    # 5. Достаем текущие остатки (Stock)
    stock_stmt = select(StockCurrent.article, StockCurrent.balance).where(StockCurrent.store_id == store_id)
    stock_result = await session.execute(stock_stmt)
    stock_data = [{"sku": row.article, "stock": float(row.balance)} for row in stock_result.all()]
    
    if stock_data:
        stock_df = pd.DataFrame(stock_data)
        forecast_df = forecast_df.merge(stock_df, on="sku", how="left")
    else:
        forecast_df["stock"] = 0.0
        
    forecast_df["stock"] = forecast_df["stock"].fillna(0.0)

    # 6. Считаем прогноз и рекомендованный заказ
    # Формула: max(0, MA3 * 1.1 - текущий остаток)
    forecast_df["predicted_qty"] = forecast_df["ma3"]
    forecast_df["recommended_qty"] = np.maximum(0.0, forecast_df["ma3"] * 1.2 - forecast_df["stock"])

    # 7. Определяем месяц прогноза (следующий месяц)
    if now.month == 12:
        next_month = 1
        next_year = now.year + 1
    else:
        next_month = now.month + 1
        next_year = now.year
    
    forecast_month = pd.Timestamp(next_year, next_month, 1).date()

    # 8. Сохраняем результат в БД
    from sqlalchemy import delete
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.backend.app.models.forecast import Forecast
    
    await session.execute(
        delete(Forecast)
        .where(Forecast.store_id == store_id)
        .where(Forecast.month == forecast_month)
    )

    records = []
    for row in forecast_df[["sku", "predicted_qty", "recommended_qty"]].to_dict(orient="records"):
        records.append({
            "store_id": store_id,
            "month": forecast_month,
            "sku": row["sku"],
            "predicted_qty": row["predicted_qty"],
            "recommended_qty": row["recommended_qty"]
        })

    if records:
        await session.execute(pg_insert(Forecast).values(records))
    
    await session.flush()
    await session.commit()
    
    # 9. Возвращаем результат в виде словаря
    return records