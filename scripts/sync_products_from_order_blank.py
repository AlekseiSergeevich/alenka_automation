#!/usr/bin/env python3
"""Синхронизация справочника product из бланка заказа (.xls «Бланк заказа»).

Читает строки таблицы после шапки (колонки как в выгрузке SHAB SRS).
Артикул в БД по умолчанию берётся из колонки «УКП»; если один и тот же УКП
встречается в нескольких строках (разные фасовки), для этих строк используется
уникальный «КОД Продаж».

При каждом запуске: upsert всех позиций из файла, затем удаление из product
записей, которых нет в файле (остальные таблицы чистятся по CASCADE).

Зависимости: pip install -r requirements-dev.txt (нужен xlrd для .xls).

Примеры:
  python scripts/sync_products_from_order_blank.py \\
    --file "data/raw/SHAB SRS 17_04_2026  Бланк заказа - Апрель 2026 (ОКС, ТК, КП).xls"

  python scripts/sync_products_from_order_blank.py   # последний .xls с «Бланк заказа» в имени в data/raw/
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from src.backend.app.db.session import get_sessionmaker  # noqa: E402
from src.backend.app.ingestion.order_blank import (  # noqa: E402
    DEFAULT_NAME_SUBSTR,
    find_latest_order_blank_xls,
    parse_order_blank,
)
from src.backend.app.models import Product  # noqa: E402
from src.backend.app.services.order_blank_catalog import apply_order_blank_full_sync  # noqa: E402


def _pick_default_xls() -> Path:
    p = find_latest_order_blank_xls(ROOT)
    if p is None:
        msg = (
            f"Нет каталога {ROOT / 'data' / 'raw'} или *.xls с «{DEFAULT_NAME_SUBSTR}»; "
            "укажите --file"
        )
        raise FileNotFoundError(msg)
    return p


async def _async_main(
    rows: list[dict],
    articles: list[str],
    *,
    truncate_all: bool,
) -> None:
    factory = get_sessionmaker()
    async with factory() as session:
        async with session.begin():
            if truncate_all:
                await session.execute(delete(Product))
                return
            await apply_order_blank_full_sync(session, rows, articles)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--file",
        "-f",
        type=Path,
        default=None,
        help=f"Путь к .xls (по умолчанию: последний data/raw/*{DEFAULT_NAME_SUBSTR}*.xls)",
    )
    p.add_argument(
        "--allow-empty-file",
        action="store_true",
        help="Разрешить пустой список товаров (удалит все строки product — только если осознанно).",
    )
    args = p.parse_args()

    path = args.file
    if path is None:
        try:
            path = _pick_default_xls()
        except FileNotFoundError as e:
            print(e, file=sys.stderr)
            return 1
    path = path.resolve()
    if not path.is_file():
        print(f"Файл не найден: {path}", file=sys.stderr)
        return 1

    try:
        rows, articles = parse_order_blank(path)
    except (OSError, ValueError, Exception) as e:
        print(f"Ошибка чтения {path}: {e}", file=sys.stderr)
        return 1

    if not articles and not args.allow_empty_file:
        print(
            "Нет позиций с УКП — выход без изменений БД "
            "(используйте --allow-empty-file чтобы удалить весь справочник).",
            file=sys.stderr,
        )
        return 1

    truncate_all = bool(not articles and args.allow_empty_file)
    if truncate_all:
        print("Пустой файл и --allow-empty-file: удаляем все product.", file=sys.stderr)

    try:
        asyncio.run(_async_main(rows, articles, truncate_all=truncate_all))
    except Exception as e:
        print(f"Ошибка БД: {e}", file=sys.stderr)
        return 1

    if truncate_all:
        print(f"OK: {path.name} — таблица product очищена.")
    else:
        print(
            f"OK: {path.name} — upsert {len(rows)} позиций, "
            "лишние артикулы удалены из product.",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
