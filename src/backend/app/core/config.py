from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# .../src/backend/app/core/config.py -> parents[2] == .../src/backend
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "candy-forecast-api"
    app_env: str = "local"
    app_debug: bool = True
    log_level: str = "INFO"

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

    # Rolling window for sales aggregation in the user-facing view.
    sales_window_days: int = 120
    # Safety overlap on incremental sales sync to cover late-arriving records.
    sales_sync_overlap_days: int = 1

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def saby_is_configured(self) -> bool:
        return bool(
            self.saby_access_token
            or (self.saby_app_client_id and self.saby_app_secret and self.saby_secret_key)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
