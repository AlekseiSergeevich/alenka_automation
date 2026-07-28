import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.ingestion.identifiers import is_sbis_internal_nom_code
from src.backend.app.ingestion.utils import to_decimal
from src.backend.app.integrations.saby.client import SabyClient
from src.backend.app.integrations.saby.schemas import (
    ProductBalanceSchema,
    first_price_list_id,
    iter_nomenclature_dicts,
)
from src.backend.app.models import Product, StockCurrent, Store

logger = logging.getLogger(__name__)

_PAGE_SIZE = 500
_LOOKUP_CONCURRENCY = 10
_MAX_INTERNAL_LOOKUPS = 500




async def ensure_store_price_list_id(
    session: AsyncSession,
    client: SabyClient,
    store_id: int,
) -> int | None:
    """Вернуть ``store.price_list_id``; при отсутствии — запросить Saby и сохранить в БД."""
    cached = await session.scalar(select(Store.price_list_id).where(Store.id == store_id))
    if cached is not None:
        return int(cached)
    raw = await client.price_list(
        point_id=store_id,
        actual_date=datetime.now(timezone.utc),
        page=0,
        page_size=100,
    )
    plid = first_price_list_id(raw)
    if plid is not None:
        await session.execute(
            update(Store).where(Store.id == store_id).values(price_list_id=plid)
        )
    return plid


async def _lookup_vendor_article(
    client: SabyClient,
    store_id: int,
    nom_key: str,
    price_list_id: int | None,
) -> str | None:
    """Розница Sbis в «полном» списке номенклатуры без поиска не отдаёт ``article``.
    По ``searchString`` (в т.ч. по ``X4924446``) можно получить «боевой» артикул вроде ``СР12667``."""

    nom_key_t = nom_key.strip()
    if not nom_key_t:
        return None
    raw = await client.list_products(
        point_id=store_id,
        price_list_id=price_list_id,
        search_string=nom_key_t,
        page_size=100,
        page=0,
        with_balance=True,
    )
    for raw_item in iter_nomenclature_dicts(raw):
        try:
            cand = ProductBalanceSchema.model_validate(raw_item)
        except ValidationError:
            continue
        if (cand.nom_number or "").strip() != nom_key_t:
            continue
        art = (cand.article or "").strip()
        if not art:
            continue
        if art == nom_key_t:
            continue
        if is_sbis_internal_nom_code(art):
            continue
        return art
    return None


async def _build_article_remaps(
    client: SabyClient,
    store_id: int,
    internals: list[str],
    price_list_id: int | None,
) -> dict[str, str]:
    if not internals:
        return {}
    if len(internals) > _MAX_INTERNAL_LOOKUPS:
        logger.warning(
            "Ограничение поиска артикула для точки %s: %s внутренних кодов (лимит %s)",
            store_id,
            len(internals),
            _MAX_INTERNAL_LOOKUPS,
        )
        internals = internals[:_MAX_INTERNAL_LOOKUPS]

    sem = asyncio.Semaphore(_LOOKUP_CONCURRENCY)

    async def _one(key: str) -> tuple[str, str | None]:
        async with sem:
            mapped = await _lookup_vendor_article(client, store_id, key, price_list_id)
            return key, mapped

    pairs = await asyncio.gather(*(_one(k) for k in internals))
    out: dict[str, str] = {}
    for k, v in pairs:
        if v:
            out[k] = v
    return out


def _apply_article_remaps(
    remap: dict[str, str],
    product_rows: list[dict[str, Any]],
    stock_rows: list[dict[str, Any]],
    seen_articles: set[str],
) -> None:
    merged: dict[str, dict[str, Any]] = {}
    for row in product_rows:
        row = dict(row)
        original_article = row["article"].strip()
        vendor_article = remap.get(original_article, original_article).strip()

        nn_out = row.get("nom_number")
        if vendor_article != original_article:
            nn_out = nn_out or original_article
            row["nom_number"] = nn_out.strip() if isinstance(nn_out, str) else nn_out

        elif not nn_out and is_sbis_internal_nom_code(vendor_article):
            row["nom_number"] = vendor_article.strip()

        row["article"] = vendor_article

        payload = {
            "article": vendor_article,
            "nom_number": row.get("nom_number"),
            "name": row.get("name", ""),
            "unit": row.get("unit", ""),
            "type": row.get("type") or "",
            "focus": row.get("focus") or "",
            "group_abc": row.get("group_abc") or "",
            "feature": row.get("feature") or "",
            "quantity_in_box": row.get("quantity_in_box") or 0,
            "updated_at": row["updated_at"],
        }
        prev = merged.get(vendor_article)
        if prev is None or len(payload["name"]) >= len(prev.get("name") or ""):
            merged[vendor_article] = payload

    product_rows[:] = list(merged.values())

    keyed: dict[tuple[int, str], dict[str, Any]] = {}
    for row in stock_rows:
        na = remap.get(row["article"], row["article"]).strip()
        nr = dict(row)
        nr["article"] = na
        keyed[(int(nr["store_id"]), na)] = nr
    stock_rows[:] = list(keyed.values())

    seen2 = {remap.get(a, a) for a in seen_articles}
    seen_articles.clear()
    seen_articles.update(seen2)


async def sync_stock(
    session: AsyncSession,
    client: SabyClient,
    store_id: int,
) -> int:
    """Refresh `stock_current` and `product` for a single store.

    Pulls all nomenclature items with `withBalance=true`, upserts the product
    dictionary and replaces the store's current stock snapshot transactionally.
    Removed SKUs are deleted so that `agg_store_product` does not carry stale
    rows.
    """

    price_list_id = await ensure_store_price_list_id(session, client, store_id)

    now = datetime.now(timezone.utc)
    seen_articles: set[str] = set()
    product_rows: list[dict[str, Any]] = []
    stock_rows: list[dict[str, Any]] = []

    page = 0
    while True:
        raw = await client.list_products(
            point_id=store_id,
            price_list_id=price_list_id,
            with_balance=True,
            page=page,
            page_size=_PAGE_SIZE,
        )
        items = iter_nomenclature_dicts(raw)
        if not items:
            break

        for item in items:
            try:
                entry = ProductBalanceSchema.model_validate(item)
            except ValidationError:
                logger.warning(
                    "Skipping stock row with invalid payload for store %s: %s",
                    store_id,
                    item.get("article"),
                )
                continue
            if not entry.article:
                continue
            if entry.article in seen_articles:
                # Defensive dedup in case Saby returns duplicates across pages.
                continue
            seen_articles.add(entry.article)
            nn = (entry.nom_number or "").strip() or None
            if nn is None and is_sbis_internal_nom_code(entry.article):
                nn = entry.article.strip()
            product_rows.append(
                {
                    "article": entry.article,
                    "nom_number": nn,
                    "name": entry.name or "",
                    "unit": entry.unit or "",
                    "type": entry.type or "",
                    "focus": entry.focus or "",
                    "group_abc": entry.group_abc or "",
                    "feature": entry.feature or "",
                    "quantity_in_box": entry.quantity_in_box,
                    "updated_at": now,
                }
            )
            stock_rows.append(
                {
                    "store_id": store_id,
                    "article": entry.article,
                    "balance": to_decimal(entry.balance),
                    "captured_at": now,
                }
            )

        if len(items) < _PAGE_SIZE:
            break
        page += 1

    internal_keys = sorted(
        [a.strip() for a in seen_articles if is_sbis_internal_nom_code(a)]
    )
    remap: dict[str, str] = {}
    try:
        remap = await _build_article_remaps(
            client, store_id, internal_keys, price_list_id
        )
    except Exception:
        logger.exception(
            "Пропускаем поиск артикулов Sbis для точки %s (остаётся ключ X…)",
            store_id,
        )
    if remap:
        logger.info(
            "store %s: vendor article remap from Sbis internals: %s example(s)",
            store_id,
            min(len(remap), 5),
        )
        _apply_article_remaps(remap, product_rows, stock_rows, seen_articles)

    if product_rows:
        stmt = pg_insert(Product).values(product_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Product.article],
            set_={
                "name": stmt.excluded.name,
                "unit": stmt.excluded.unit,
                "updated_at": now,
                "nom_number": func.coalesce(stmt.excluded.nom_number, Product.nom_number),
                "type": stmt.excluded.type,
                "focus": stmt.excluded.focus,
                "group_abc": stmt.excluded.group_abc,
                "feature": stmt.excluded.feature,
                "quantity_in_box": stmt.excluded.quantity_in_box,
            },
        )
        await session.execute(stmt)

    if stock_rows:
        stmt = pg_insert(StockCurrent).values(stock_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[StockCurrent.store_id, StockCurrent.article],
            set_={
                "balance": stmt.excluded.balance,
                "captured_at": stmt.excluded.captured_at,
            },
        )
        await session.execute(stmt)

    # Drop rows that disappeared from Saby's nomenclature for this store.
    if seen_articles:
        await session.execute(
            delete(StockCurrent).where(
                and_(
                    StockCurrent.store_id == store_id,
                    StockCurrent.article.notin_(seen_articles),
                )
            )
        )
    else:
        await session.execute(delete(StockCurrent).where(StockCurrent.store_id == store_id))

    return len(stock_rows)


async def sync_stock_for_existing_products(
    session: AsyncSession,
    client: SabyClient,
    store_id: int,
) -> int:
    """Обновить ``stock_current`` только для артикулов из таблицы ``product``.

    Тянет номенклатуру точки как ``sync_stock``, применяет remap ``X…`` → артикул,
    затем оставляет только SKU из каталога ``product``. Не изменяет таблицу ``product``.
    """

    allowed_rows = (
        await session.execute(select(Product.article).where(Product.article.isnot(None)))
    ).all()
    allowed_articles = {str(a[0]).strip() for a in allowed_rows if a[0]}
    if not allowed_articles:
        return 0

    price_list_id = await ensure_store_price_list_id(session, client, store_id)

    now = datetime.now(timezone.utc)
    seen_articles: set[str] = set()
    product_rows: list[dict[str, Any]] = []
    stock_rows: list[dict[str, Any]] = []

    sem = asyncio.Semaphore(20)

    async def fetch_folder(folder_id: int | None):
        page = 0
        found_items = []
        found_folders = []
        while True:
            params = {
                "pointId": store_id,
                "priceListId": price_list_id,
                "withBalance": "true",
                "page": page,
                "pageSize": _PAGE_SIZE,
            }
            if folder_id is not None:
                params["folder"] = folder_id

            async with sem:
                raw = await client._get("/retail/v2/nomenclature/list", params=params)

            items = raw.get("nomenclatures", [])
            if not items:
                break

            for item in items:
                if not item.get("article") and item.get("hierarchicalId"):
                    found_folders.append(item.get("hierarchicalId"))
                else:
                    found_items.append(item)

            if len(items) < _PAGE_SIZE:
                break
            page += 1
        return found_items, found_folders

    folders_to_process = [None]
    processed_folders = set()
    all_raw_items = []

    while folders_to_process:
        tasks = []
        for f in folders_to_process:
            if f not in processed_folders:
                processed_folders.add(f)
                tasks.append(fetch_folder(f))

        folders_to_process = []
        if not tasks:
            break

        results = await asyncio.gather(*tasks)
        for items, subfolders in results:
            all_raw_items.extend(items)
            folders_to_process.extend(subfolders)

    for item in all_raw_items:
        try:
            entry = ProductBalanceSchema.model_validate(item)
        except ValidationError:
            continue
        if not entry.article:
            continue
        if entry.article in seen_articles:
            continue
        seen_articles.add(entry.article)
        nn = (entry.nom_number or "").strip() or None
        if nn is None and is_sbis_internal_nom_code(entry.article):
            nn = entry.article.strip()
        product_rows.append(
            {
                "article": entry.article,
                "nom_number": nn,
                "name": entry.name or "",
                "unit": entry.unit or "",
                "type": entry.type or "",
                "focus": entry.focus or "",
                "group_abc": entry.group_abc or "",
                "feature": entry.feature or "",
                "quantity_in_box": entry.quantity_in_box,
                "updated_at": now,
            }
        )
        stock_rows.append(
            {
                "store_id": store_id,
                "article": entry.article,
                "balance": to_decimal(entry.balance),
                "captured_at": now,
            }
        )

    internal_keys = sorted(
        [a.strip() for a in seen_articles if is_sbis_internal_nom_code(a)]
    )
    remap: dict[str, str] = {}
    try:
        remap = await _build_article_remaps(
            client, store_id, internal_keys, price_list_id
        )
    except Exception:
        pass
    if remap:
        _apply_article_remaps(remap, product_rows, stock_rows, seen_articles)

    filtered_stock: list[dict[str, Any]] = []
    seen_allowed: set[str] = set()
    for row in stock_rows:
        art = str(row["article"]).strip()
        if art in allowed_articles:
            filtered_stock.append(row)
            seen_allowed.add(art)

    if filtered_stock:
        stmt = pg_insert(StockCurrent).values(filtered_stock)
        stmt = stmt.on_conflict_do_update(
            index_elements=[StockCurrent.store_id, StockCurrent.article],
            set_={
                "balance": stmt.excluded.balance,
                "captured_at": stmt.excluded.captured_at,
            },
        )
        await session.execute(stmt)

    stale_managed = allowed_articles - seen_allowed
    if stale_managed:
        await session.execute(
            delete(StockCurrent).where(
                and_(
                    StockCurrent.store_id == store_id,
                    StockCurrent.article.in_(stale_managed),
                )
            )
        )

    return len(filtered_stock)
