#!/usr/bin/env python3
"""Проверка локального окружения: DATABASE_URL (без пароля) и наличие настроек Saby.

Запуск из корня репозитория:
  .venv/bin/python scripts/check_env.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backend.app.core.config import get_settings  # noqa: E402


def _mask_database_url(url: str) -> str:
    # postgresql+asyncpg://user:pass@host:port/db -> ...@host:port/db
    if "@" not in url:
        return url
    return re.sub(r":[^:@/]+@", ":****@", url, count=1)


def main() -> int:
    s = get_settings()
    print(f"DATABASE_URL: {_mask_database_url(s.database_url)}")
    print(f"Saby configured: {s.saby_is_configured}")
    if not s.saby_is_configured:
        print(
            "Добавьте в src/backend/.env: SABY_APP_CLIENT_ID, SABY_APP_SECRET, "
            "SABY_SECRET_KEY или SABY_ACCESS_TOKEN (см. src/backend/.env.example).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
