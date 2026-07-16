from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.app.db.session import get_sessionmaker
from src.backend.app.services.forecast_service import generate_forecast_for_store

router = APIRouter()

async def get_db_session():
    async with get_sessionmaker()() as session:
        yield session

@router.post("/{store_id}/generate")
async def generate_forecast(store_id: int, session: AsyncSession = Depends(get_db_session)):
    """Эндпоинт для генерации прогноза и сохранения его в БД"""
    result = await generate_forecast_for_store(session, store_id)
    return {"store_id": store_id, "status": "success", "forecast": result}

@router.get("/{store_id}")
async def get_forecast(store_id: int, session: AsyncSession = Depends(get_db_session)):
    """Эндпоинт для получения уже рассчитанного прогноза из БД"""
    from sqlalchemy import select
    from src.backend.app.models.forecast import Forecast
    
    stmt = select(Forecast).where(Forecast.store_id == store_id).order_by(Forecast.sku)
    result = await session.execute(stmt)
    forecasts = result.scalars().all()
    
    return {
        "store_id": store_id, 
        "forecast": [
            {
                "sku": f.sku, 
                "predicted_qty": float(f.predicted_qty),
                "recommended_qty": float(f.recommended_qty),
                "month": f.month.isoformat()
            } for f in forecasts
        ]
    }