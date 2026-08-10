import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.backend.app.api.v1.router import build_api_router
from src.backend.app.core.config import get_settings
from src.backend.app.integrations.saby.client import SabyClient
from src.backend.app.services.orchestrator import build_orchestrator
from src.backend.app.services.startup_bootstrap import run_startup_bootstrap


import os
from logging.handlers import RotatingFileHandler

def configure_logging(level: str) -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)

    log_formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(log_formatter)

    # Always add the file handler so we get file logs alongside Docker's console logs
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(file_handler)

    # If no handlers exist at all, add a basic console handler
    if not root.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        root.addHandler(console_handler)


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

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        from src.backend.app.core.logging_ws import ws_log_handler
        ws_log_handler.set_loop(asyncio.get_running_loop())
        
        log = logging.getLogger("candy_forecast.startup")
        if settings.startup_bootstrap_enabled and settings.saby_is_configured:

            async def _bootstrap() -> None:
                try:
                    cfg = get_settings()
                    client = SabyClient(settings=cfg)
                    orch = build_orchestrator(client)
                    result = await run_startup_bootstrap(orch, cfg)
                    log.info("startup bootstrap finished: %s", result.get("status"))
                except Exception:
                    log.exception("startup bootstrap failed")

            if settings.startup_bootstrap_fail_fast:
                await _bootstrap()
            else:
                asyncio.create_task(_bootstrap())
        yield

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
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

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.websocket("/api/v1/ws/logs")
    async def websocket_logs(websocket: WebSocket):
        await websocket.accept()
        from src.backend.app.core.logging_ws import ws_log_handler
        ws_log_handler.websockets.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            pass
        finally:
            ws_log_handler.websockets.remove(websocket)

    app.include_router(build_api_router(settings))
    return app


app = create_app()
