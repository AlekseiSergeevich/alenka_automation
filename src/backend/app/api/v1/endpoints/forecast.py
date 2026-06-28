from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.backend.app.db.session import get_sessionmaker
from src.backend.app.services.forecast_service import generate_forecast_for_store

router = APIRouter()

async def get_db_session():
    async with get_sessionmaker()() as session:
        yield session

@router.get("/{store_id}")
async def get_forecast(store_id: int, session: AsyncSession = Depends(get_db_session)):
    """Эндпоинт для запуска ML пайплайна и получения прогноза"""
    # Вызываем нашу бизнес-логику для конкретного магазина
    result = await generate_forecast_for_store(session, store_id)
    return {"store_id": store_id, "forecast": result}