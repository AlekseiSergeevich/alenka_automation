#!/usr/bin/env python3
"""Первичная загрузка через API: POST /api/v1/sync/bootstrap (points → все точки → stock + sales).

Требуется запущенный API и настроенный Saby (см. scripts/check_env.py).

Пример:
  .venv/bin/python scripts/bootstrap_sync.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Базовый URL API (без завершающего /)",
    )
    p.add_argument(
        "--token",
        default=os.environ.get("CF_TOKEN"),
        help=(
            "Bearer token для Authorization (если включён AUTH_ENABLED). "
            "Либо переменная окружения CF_TOKEN."
        ),
    )
    args = p.parse_args()
    base = args.base_url.rstrip("/")

    headers: dict[str, str] = {}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    with httpx.Client(timeout=900.0) as client_http:
        r = client_http.post(
            f"{base}/api/v1/sync/bootstrap",
            params={"mode": "force"},
            headers=headers,
        )
        if r.status_code != 200:
            print(f"sync bootstrap failed: {r.status_code} {r.text}", file=sys.stderr)
            return 1
        print(r.json())

    print("Bootstrap sync finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
