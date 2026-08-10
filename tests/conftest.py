"""Сброс кэшированного async-движка между тестами: у TestClient свой event loop."""

from __future__ import annotations

import os
from pathlib import Path


def _rewrite_database_url_for_host_pytest() -> None:
    """Хост из Docker Compose — ``db``; с машины он не резолвится.

    Если pytest запускается **не** внутри контейнера, подменяем ``db`` на
    ``127.0.0.1`` (порт Postgres проброшен на хост). Явный ``DATABASE_URL``
    в окружении не трогаем, если он уже без ``@db:``.

    Значение из ``src/backend/.env`` подмешиваем в ``os.environ`` до любого
    импорта приложения, иначе pydantic прочитает файл с ``db`` напрямую.
    """

    if Path("/.dockerenv").exists():
        return

    def rewrite(url: str) -> str:
        return url.replace("@db:", "@127.0.0.1:")

    cur = os.environ.get("DATABASE_URL")
    if cur and "@db:" in cur:
        os.environ["DATABASE_URL"] = rewrite(cur)
        return

    if cur:
        return

    env_file = Path(__file__).resolve().parents[1] / "src" / "backend" / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("DATABASE_URL="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            if "@db:" in val:
                os.environ["DATABASE_URL"] = rewrite(val)
            break


_rewrite_database_url_for_host_pytest()

import pytest

from src.backend.app.core.config import get_settings
from src.backend.app.db.session import get_engine, get_sessionmaker


@pytest.fixture(autouse=True)
def _reset_db_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
