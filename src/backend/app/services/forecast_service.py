import pandas as pd                                                                                                      
import numpy as np                                                                                                       
from datetime import datetime, timezone                                                                                  
from sqlalchemy.ext.asyncio import AsyncSession                                                                          
from sqlalchemy import select                                                                                            
from pathlib import Path                                                                                                 
import calendar                                                                                                          
                                                                                                                            
from src.backend.app.models.sales_monthly import SalesMonthly                                                            
from src.backend.app.services.ml_model import forecast_model                                                             
                                                                                                                            
STATIC_FEATURES_PATH = Path(__file__).resolve().parents[4] / "data" / "clean" / "final_ml_dataset.csv"                   
                                                                                                                            
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
                                                                                                                            
    # 4. Подтягиваем статические фичи (категории, бренд, цена) из вашего файла                                           
    static_features = pd.read_csv(STATIC_FEATURES_PATH)                                                                  
    static_features = static_features[['УКП', 'is_new', 'focus', 'abc_group', 'item_type', 'brand', 'base_price',        
'shelf_life_days', 'weight_gr']].drop_duplicates()                                                                         
                                                                                                                            
    df = df.merge(static_features, left_on="sku", right_on="УКП", how="left")                                            
                                                                                                                            
    # 5. Считаем лаги и скользящие средние (точь-в-точь как в ноутбуке)                                                  
    df = df.sort_values(["sku", "month"]).reset_index(drop=True)                                                         
    qty_group = df.groupby("sku", sort=False)["qty"]                                                                     
                                                                                                                            
    df["history"] = qty_group.shift(0) # В бэкенде текущий месяц УЖЕ является lag_1 для прогноза следующего              
    df["history_non_zero"] = df["history"].where(df["history"] > 0)                                                      
    df["history_is_non_zero"] = df["history"].gt(0).astype(float)                                                        
                                                                                                                            
    for lag in [1, 2, 3]:                                                                                                
        df[f"lag_{lag}"] = qty_group.shift(lag)                                                                          
                                                                                                                            
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
    next_month = now.month + 1 if now.month < 12 else 1                                                                  
    df["month_num"] = next_month                                                                                         
    df["month_sin"] = np.sin(2 * np.pi * df["month_num"] / 12)                                                           
    df["month_cos"] = np.cos(2 * np.pi * df["month_num"] / 12)                                                           
                                                                                                                            
    # 6. Оставляем только самую последнюю строку для каждого SKU (это точка, с которой мы делаем прыжок в будущее)       
    forecast_df = df.groupby("sku").tail(1).copy()                                                                       
                                                                                                                            
    # 7. Заполняем пропуски и конвертируем типы категорий                                                                
    time_cols = ["lag_1", "lag_2", "lag_3", "ma3", "ma6", "median3", "median6", "ma3_non_zero", "non_zero_share_6",      
"lag_1_to_ma3", "month_num", "month_sin", "month_cos"]                                                                     
    cat_cols = ["is_new", "focus", "abc_group", "item_type", "brand"]                                                    
    num_cols = ["base_price", "shelf_life_days", "weight_gr"]                                                            
                                                                                                                            
    forecast_df[time_cols + num_cols] = forecast_df[time_cols + num_cols].fillna(0.0)                                    
    for col in cat_cols:                                                                                                 
        forecast_df[col] = forecast_df[col].fillna("Unknown").astype("category")                                         
                                                                                                                            
    # 8. Отдаем датафрейм в модель!                                                                                      
    predictions = forecast_model.predict(forecast_df[time_cols + cat_cols + num_cols])                                   
    forecast_df["predicted_qty"] = predictions                                                                           
                                                                                                                            
    # 9. Возвращаем результат в виде словаря                                                                             
    return forecast_df[["sku", "predicted_qty"]].to_dict(orient="records")