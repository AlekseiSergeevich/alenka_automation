import pandas as pd                                                                                                      
import numpy as np                                                                                                       
from datetime import datetime, timezone                                                                                  
from sqlalchemy.ext.asyncio import AsyncSession                                                                          
from sqlalchemy import select                                                                                            
from pathlib import Path                                                                                                 
import calendar                                                                                                          
                                                                                                                            
from src.backend.app.models.sales_monthly import SalesMonthly                                                            
from src.backend.app.services.ml_model import forecast_model                                                             
                                                                                                                            
from src.backend.app.models.order_blank_upload import OrderBlankUpload
from src.backend.app.models.order_blank_item import OrderBlankItem
from src.backend.app.services.order_blank_catalog import STATUS_SUCCESS

async def generate_forecast_for_store(session: AsyncSession, store_id: int):                                             
    # 1. Достаем историю продаж за последние 6-7 месяцев из БД                                                           
    stmt = select(SalesMonthly).where(SalesMonthly.store_id == store_id)                                                 
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
                                                                                                                            
    # 3. ЭКСТРАПОЛЯЦИЯ текущего неполного месяца (то, о чем мы говорили!)                                                
    now = datetime.now(timezone.utc)                                                                                     
    current_month_start = pd.Timestamp(now.year, now.month, 1)                                                           
    days_in_month = calendar.monthrange(now.year, now.month)[1]                                                          
                                                                                                                            
    # Умножаем текущие продажи на коэффициент (Дней_в_месяце / Прошло_дней)                                              
    extrapolation_factor = days_in_month / now.day                                                                       
    df.loc[df['month'] == current_month_start, 'qty'] *= extrapolation_factor                                            
                                                                                                                            
    # 4. Подтягиваем статические фичи (из БД, из последнего загруженного бланка)
    latest_upload_id = await session.scalar(
        select(OrderBlankUpload.id)
        .where(OrderBlankUpload.status == STATUS_SUCCESS)
        .order_by(OrderBlankUpload.applied_at.desc())
        .limit(1)
    )

    if not latest_upload_id:
        return {"error": "В системе нет успешных загрузок бланка заказа"}

    active_items = (await session.execute(
        select(OrderBlankItem).where(OrderBlankItem.upload_id == latest_upload_id)
    )).scalars().all()

    if not active_items:
        return {"error": "Последний загруженный бланк заказа не содержит товаров"}

    static_features = pd.DataFrame([{
        "sku": item.sku,
        "is_new": item.is_new,
        "focus": item.focus,
        "abc_group": item.abc_group,
        "item_type": item.item_type,
        "brand": item.brand,
        "base_price": float(item.base_price),
        "shelf_life_days": item.shelf_life_days,
        "weight_gr": float(item.weight_gr),
    } for item in active_items])
                                                                                                                            
    # INNER JOIN оставит только те товары из продаж, которые ЕСТЬ в активном бланке заказа!
    df = df.merge(static_features, on="sku", how="inner")

                                                                                                                            
    # 5. Считаем лаги и скользящие средние (точь-в-точь как в ноутбуке)                                                  
    df = df.sort_values(["sku", "month"]).reset_index(drop=True)                                                         
    qty_group = df.groupby("sku", sort=False)["qty"]                                                                     
                                                                                                                            
    df["history"] = qty_group.shift(0) # Самый свежий месяц (июнь) станет lag_1 для июля
    df["history_non_zero"] = df["history"].where(df["history"] > 0)
    df["history_is_non_zero"] = df["history"].gt(0).astype(float)

    # Так как мы делаем прыжок в будущее, lag_1 для следующего месяца - это текущий месяц
    df["lag_1"] = qty_group.shift(0)
    df["lag_2"] = qty_group.shift(1)
    df["lag_3"] = qty_group.shift(2)                                                                          
                                                                                                                            
    # Функции rolling                                                                                                    
    df["ma3"] = df.groupby("sku")["history"].transform(lambda x: x.rolling(3, min_periods=1).mean())                     
    df["ma6"] = df.groupby("sku")["history"].transform(lambda x: x.rolling(6, min_periods=1).mean())                     
    df["median3"] = df.groupby("sku")["history"].transform(lambda x: x.rolling(3, min_periods=1).median())               
    df["median6"] = df.groupby("sku")["history"].transform(lambda x: x.rolling(6, min_periods=1).median())               
    df["ma3_non_zero"] = df.groupby("sku")["history_non_zero"].transform(lambda x: x.rolling(3, min_periods=1).mean())   
    df["non_zero_share_6"] = df.groupby("sku")["history_is_non_zero"].transform(lambda x: x.rolling(6, min_periods=1).   
mean())                                                                                                                    
                                                                                                                            
    df["lag_1_to_ma3"] = df["lag_1"] / (df["ma3_non_zero"].fillna(df["ma3"]).fillna(0.0) + 1.0)                          
                                                                                                                            
    # Фичи следующего месяца (на который мы прогнозируем)                                                                
    if now.month == 12:
        next_month = 1
        next_year = now.year + 1
    else:
        next_month = now.month + 1
        next_year = now.year
    
    forecast_month = pd.Timestamp(next_year, next_month, 1).date()
    df["month_num"] = next_month                                                                                         
    df["month_sin"] = np.sin(2 * np.pi * df["month_num"] / 12)                                                           
    df["month_cos"] = np.cos(2 * np.pi * df["month_num"] / 12)                                                           
                                                                                                                            
    # 6. Оставляем только самую последнюю строку для каждого SKU (это точка, с которой мы делаем прыжок в будущее)       
    forecast_df = df.groupby("sku").tail(1).copy()                                                                       
                                                                                                                        
    if forecast_df.empty:
        return []                                                                       
                                                                                                                            
    # 7. Заполняем пропуски и выравниваем категории по исходному датасету
    time_cols = ["lag_1", "lag_2", "lag_3", "ma3", "ma6", "median3", "median6", "ma3_non_zero", "non_zero_share_6", "lag_1_to_ma3", "month_num", "month_sin", "month_cos"]
    cat_cols = ["is_new", "focus", "abc_group", "item_type", "brand"]
    num_cols = ["base_price", "shelf_life_days", "weight_gr"]

    forecast_df[time_cols + num_cols] = forecast_df[time_cols + num_cols].fillna(0.0)

    # ВАЖНО: Категории для XGBoost должны в точности совпадать с теми, что были при обучении!
    # Иначе Pandas даст им другие integer коды и модель выдаст бред.
    KNOWN_CATEGORIES_MAP = {
        "is_new": ["-1", "0", "1"],
        "focus": ["Unknown", "ЛА", "Прочее", "ТОП66"],
        "abc_group": ["AA", "AB", "AC", "BA", "BB", "BC", "CB", "CC", "Unknown"],
        "item_type": [
            "Unknown", "БИСКВИТЫ", "ВАФЛИ", "ГАЛЕТЫ И КРЕКЕРЫ, ХЛЕБЦЫ", "ДРАЖЕ", 
            "ЗЕФИР И ПАСТИЛА", "ЗЛАКОВЫЕ ИЗДЕЛИЯ", "ИРИС", "КАРАМЕЛЬ", 
            "КОНФЕТЫ В КОРОБКАХ", "КОНФЕТЫ ВЕСОВЫЕ", "КОФЕ", "Какао", 
            "Мармелад", "ПЕЧЕНЬЕ", "ПРОЧИЕ МУЧНИСТЫЕ", "ПРОЧИЕ САХАРИСТЫЕ", 
            "ПРЯНИКИ И КОВРИЖКИ", "ТОРТЫ", "ХАЛВА", "ШОКОЛАД"
        ],
        "brand": ["Unknown", "ББ", "ВО", "ЙО", "КО", "КР", "НС", "ОК", "ПЗ", "РФ", "СМ", "СР", "ТК", "ЮК", "ЯП"]
    }

    for col in cat_cols:
        # Используем жестко зашитый словарь категорий (эталон из обучения)
        known_categories = KNOWN_CATEGORIES_MAP.get(col, ["Unknown"])
        cat_type = pd.CategoricalDtype(categories=known_categories)
        
        if forecast_df[col].dtype == "float64":
            forecast_df[col] = forecast_df[col].fillna(-1).astype(int).astype(str)
        else:
            forecast_df[col] = forecast_df[col].fillna("Unknown").astype(str)
            
        forecast_df[col] = forecast_df[col].astype(cat_type)

    # 8. Отдаем датафрейм в модель!
    X = forecast_df[time_cols + cat_cols + num_cols]
    if "КО01828" in forecast_df.index:
        X.loc[["КО01828"]].to_csv("/app/logs/debug_ko01828.csv")
    elif "КО01828" in forecast_df["sku"].values if "sku" in forecast_df.columns else False:
        X[forecast_df["sku"] == "КО01828"].to_csv("/app/logs/debug_ko01828.csv")
    else:
        # The index is the original df integer index! sku is a column in forecast_df!
        # wait, forecast_df = df.groupby("sku").tail(1).copy()
        # so forecast_df HAS "sku" column!
        debug_row = forecast_df[forecast_df["sku"] == "КО01828"]
        if not debug_row.empty:
            debug_row[time_cols + cat_cols + num_cols].to_csv("/app/logs/debug_ko01828.csv", index=False)

    predictions = forecast_model.predict(X)
    forecast_df["predicted_qty"] = predictions
    
    # 9. Сохраняем прогноз в БД
    from sqlalchemy import delete
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.backend.app.models.forecast import Forecast
    
    await session.execute(
        delete(Forecast)
        .where(Forecast.store_id == store_id)
        .where(Forecast.month == forecast_month)
    )

    records = []
    for row in forecast_df[["sku", "predicted_qty"]].to_dict(orient="records"):
        records.append({
            "store_id": store_id,
            "month": forecast_month,
            "sku": row["sku"],
            "predicted_qty": row["predicted_qty"]
        })

    if records:
        await session.execute(pg_insert(Forecast).values(records))
    
    await session.flush()
    await session.commit()
    
    # 10. Возвращаем результат в виде словаря
    return records