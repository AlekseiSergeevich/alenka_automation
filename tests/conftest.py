"""Сброс кэшированного async-движка между тестами: у TestClient свой event loop."""

from __future__ import annotations

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
