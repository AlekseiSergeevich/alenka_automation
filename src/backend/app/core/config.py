from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# .../src/backend/app/core/config.py -> parents[2] == .../src/backend
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _parse_csv_origins(v: str | list[str] | None) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [x.strip() for x in v if str(x).strip()]
    s = v.strip()
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


class Settings(BaseSettings):
    app_name: str = "candy-forecast-api"
    app_env: str = "local"
    app_debug: bool = False
    log_level: str = "INFO"

    # When false, all routes behave as authenticated admin (local dev only).
    auth_enabled: bool = False
    # Required when auth_enabled (generate: python -c "from src.backend.app.core.security import generate_secret_key; print(generate_secret_key())")
    session_secret: str | None = Field(default=None)
    session_cookie_name: str = "cf_session"
    session_max_age_seconds: int = Field(default=7 * 24 * 60 * 60, ge=60)
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    auth_admin_username: str | None = Field(default=None)
    auth_admin_password_hash: str | None = Field(default=None)
    auth_viewer_username: str | None = Field(default=None)
    auth_viewer_password_hash: str | None = Field(default=None)

    enable_api_docs: bool = True
    enable_openapi_json: bool = True

    # Comma-separated list, e.g. https://app.example.com,http://localhost:5173
    cors_allowed_origins: str = ""

    # Mount Saby debug proxy (admin-only when auth is on).
    enable_saby_debug_api: bool = True

    saby_auth_url: str = "https://online.sbis.ru/oauth/service/"
    saby_api_base_url: str = "https://api.sbis.ru"
    # JSON-RPC service API (e.g. sabyWarehouse.List), POST application/json-rpc
    saby_service_url: str = "https://online.sbis.ru/service/"
    saby_app_client_id: str | None = Field(default=None)
    saby_app_secret: str | None = Field(default=None)
    saby_secret_key: str | None = Field(default=None)
    saby_access_token: str | None = Field(default=None)

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/candy_forecast",
        description="Async SQLAlchemy DSN, e.g. postgresql+asyncpg://user:pass@host:5432/db",
    )
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 5

    # How long cached data is considered fresh, in seconds.
    ttl_points_seconds: int = 24 * 60 * 60
    ttl_stock_seconds: int = 15 * 60
    ttl_sales_seconds: int = 30 * 60

    # Последние N календарных месяцев для помесячной статистики и агрегата.
    sales_months_back: int = Field(default=3, ge=1, le=120)
    # Устарело: раньше скользящее окно; оставлено для совместимости .env.
    sales_window_days: int = 120
    # Safety overlap on incremental sales sync to cover late-arriving records.
    sales_sync_overlap_days: int = 1

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _strip_cors(cls, v: object) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @model_validator(mode="after")
    def _auth_required_fields(self) -> Self:
        if not self.auth_enabled:
            return self
        if not self.session_secret or len(self.session_secret) < 16:
            msg = "SESSION_SECRET must be set (>=16 chars) when AUTH_ENABLED=true"
            raise ValueError(msg)
        has_admin = bool(self.auth_admin_username and self.auth_admin_password_hash)
        has_viewer = bool(self.auth_viewer_username and self.auth_viewer_password_hash)
        if not has_admin and not has_viewer:
            msg = (
                "When AUTH_ENABLED=true, set AUTH_ADMIN_* or AUTH_VIEWER_* "
                "(username + bcrypt password hash)."
            )
            raise ValueError(msg)
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return _parse_csv_origins(self.cors_allowed_origins)

    @property
    def saby_is_configured(self) -> bool:
        return bool(
            self.saby_access_token
            or (self.saby_app_client_id and self.saby_app_secret and self.saby_secret_key)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
