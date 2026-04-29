#!/usr/bin/env python3
"""Первичная загрузка: sync points, затем для каждой точки — stock и sales (mode=force).

Требуется запущенный API и настроенный Saby (см. scripts/check_env.py).

Пример:
  .venv/bin/python scripts/bootstrap_sync.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Базовый URL API (без завершающего /)",
    )
    args = p.parse_args()
    base = args.base_url.rstrip("/")

    with httpx.Client(timeout=600.0) as client:
        r = client.post(f"{base}/api/v1/sync/points", params={"mode": "force"})
        if r.status_code != 202:
            print(f"sync points failed: {r.status_code} {r.text}", file=sys.stderr)
            return 1

        r = client.get(f"{base}/api/v1/stores")
        if r.status_code != 200:
            print(f"GET stores failed: {r.status_code} {r.text}", file=sys.stderr)
            return 1
        stores = r.json()
        ids = [s["id"] for s in stores]
        print(f"Stores: {len(ids)} — {ids}")

        for sid in ids:
            for entity in ("stock", "sales"):
                rr = client.post(
                    f"{base}/api/v1/sync/{entity}",
                    params={"store_id": sid, "mode": "force"},
                )
                if rr.status_code != 202:
                    print(
                        f"sync {entity} store={sid} failed: {rr.status_code} {rr.text}",
                        file=sys.stderr,
                    )
                    return 1
                print(f"OK {entity} store_id={sid}")

    print("Bootstrap sync finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
