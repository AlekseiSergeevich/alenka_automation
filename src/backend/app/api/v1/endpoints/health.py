from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from src.backend.app.core.config import get_settings
from src.backend.app.db.session import get_engine


router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/health/ready")
async def health_ready() -> dict[str, str]:
    """Readiness: verifies PostgreSQL connectivity (for orchestrators / load balancers)."""
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except OSError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unavailable",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unavailable",
        ) from None
    return {"status": "ready"}
