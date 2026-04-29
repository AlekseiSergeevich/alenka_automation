from fastapi import APIRouter

from src.backend.app.api.v1.endpoints import health, overview, saby, sync

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(overview.router, prefix="/api/v1", tags=["overview"])
api_router.include_router(sync.router, prefix="/api/v1", tags=["sync"])
# Saby proxy endpoints are kept for debugging/admin inspection only.
api_router.include_router(saby.router, prefix="/api/v1/saby", tags=["saby-debug"])
