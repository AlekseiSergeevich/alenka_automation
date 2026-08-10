from fastapi import APIRouter

from src.backend.app.api.v1.endpoints import auth, health, order_blank, overview, saby, sync, forecast
from src.backend.app.core.config import Settings


def build_api_router(settings: Settings) -> APIRouter:
    """Assemble v1 routes; Saby debug is optional (production should disable it)."""
    api_router = APIRouter()
    api_router.include_router(health.router, tags=["health"])
    api_router.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    api_router.include_router(overview.router, prefix="/api/v1", tags=["overview"])
    api_router.include_router(order_blank.router, prefix="/api/v1", tags=["order-blank"])
    api_router.include_router(sync.router, prefix="/api/v1", tags=["sync"])
    api_router.include_router(forecast.router, prefix="/api/v1/forecast", tags=["forecast"])
    if settings.enable_saby_debug_api:
        api_router.include_router(saby.router, prefix="/api/v1/saby", tags=["saby-debug"])
    return api_router
