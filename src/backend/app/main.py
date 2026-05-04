import logging
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.backend.app.api.v1.router import build_api_router
from src.backend.app.core.config import get_settings


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(getattr(logging, level.upper(), logging.INFO))
        return
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Adds X-Request-ID to each request/response (for log correlation)."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    docs_url = "/docs" if settings.enable_api_docs else None
    redoc_url = "/redoc" if settings.enable_api_docs else None
    openapi_url = "/openapi.json" if settings.enable_openapi_json else None

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    app.add_middleware(RequestIdMiddleware)
    if settings.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": exc.detail,
                    "request_id": rid,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": exc.errors(),
                    "request_id": rid,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log = logging.getLogger("candy_forecast.api")
        rid = getattr(request.state, "request_id", None)
        log.exception("Unhandled error request_id=%s", rid)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Internal server error",
                    "request_id": rid,
                }
            },
        )

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "message": "Candy Forecast API is running",
            "docs": "/docs",
            "health": "/health",
            "health_ready": "/health/ready",
        }

    app.include_router(build_api_router(settings))
    return app


app = create_app()
