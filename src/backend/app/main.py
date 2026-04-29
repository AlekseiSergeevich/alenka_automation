from fastapi import FastAPI

from src.backend.app.api.v1.router import api_router
from src.backend.app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "message": "Candy Forecast API is running",
            "docs": "/docs",
            "health": "/health",
        }

    app.include_router(api_router)
    return app


app = create_app()
