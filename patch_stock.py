import re

with open("src/backend/app/ingestion/stock.py", "r") as f:
    code = f.read()

mapping_code = """
STORE_TO_WAREHOUSE: dict[int, str] = {
    25042: "bbabc78e-90ee-4aa3-bb4c-0000000061d6",  # Геленджик
    20268: "0c575ccc-a377-4611-b932-000000004f2e",  # Новороссийск
    2116: "ec3fd08b-f01d-4c50-b031-000000000846",   # Тверь
    170: "588ffa77-90a6-433c-8b45-0000000000ac",    # Ярославль
}
"""

if "STORE_TO_WAREHOUSE" not in code:
    code = code.replace("_MAX_INTERNAL_LOOKUPS = 500\n", "_MAX_INTERNAL_LOOKUPS = 500\n\n" + mapping_code)

new_func = """async def sync_stock_for_existing_products(
    session: AsyncSession,
    client: SabyClient,
    store_id: int,
) -> int:
    allowed_rows = (
        await session.execute(select(Product.article).where(Product.article.isnot(None)))
    ).all()
    allowed_articles = {str(a[0]).strip() for a in allowed_rows if a[0]}
    if not allowed_articles:
        return 0

    now = datetime.now(timezone.utc)
    filtered_stock: list[dict[str, Any]] = []
    seen_allowed: set[str] = set()
    
    warehouse_id = STORE_TO_WAREHOUSE.get(store_id)
    if warehouse_id:
        import asyncio
        sem = asyncio.Semaphore(15)
        
        async def _fetch(art: str):
            async with sem:
                raw = await client.list_products(
                    point_id=store_id, warehouse_id=warehouse_id, search_string=art, page_size=10, page=0, with_balance=True
                )
                for item in iter_nomenclature_dicts(raw):
                    try:
                        entry = ProductBalanceSchema.model_validate(item)
                        if entry.article and entry.article.strip() == art:
                            balance = to_decimal(entry.balance) if entry.balance is not None else 0
                            return {"store_id": store_id, "article": entry.article, "balance": balance, "captured_at": now, "refreshed_at": now}
                    except Exception:
                        pass
            return None
            
        arts = list(allowed_articles)
        for i in range(0, len(arts), 100):
            chunk = arts[i:i+100]
            results = await asyncio.gather(*[_fetch(a) for a in chunk])
            for r in results:
                if r and r["article"] not in seen_allowed:
                    filtered_stock.append(r)
                    seen_allowed.add(r["article"])
    else:
        # Fallback to price list
        price_list_id = await ensure_store_price_list_id(session, client, store_id)
        position = None
        while True:
            raw = await client.list_products(
                point_id=store_id, price_list_id=price_list_id, with_balance=True, page_size=_PAGE_SIZE, position=position, order="after" if position is not None else None
            )
            items = iter_nomenclature_dicts(raw)
            if not items:
                break
            for item in items:
                try:
                    entry = ProductBalanceSchema.model_validate(item)
                    art = entry.article
                    if art and art in allowed_articles and art not in seen_allowed:
                        balance = to_decimal(entry.balance) if entry.balance is not None else 0
                        filtered_stock.append({"store_id": store_id, "article": art, "balance": balance, "captured_at": now, "refreshed_at": now})
                        seen_allowed.add(art)
                except Exception:
                    pass
            outcome = raw.get("outcome") or raw.get("outCome") or {}
            if outcome.get("hasMore") is False:
                break
            position = raw["nomenclatures"][-1].get("hierarchicalId") if raw.get("nomenclatures") else None

    # Upsert found stock
    if filtered_stock:
        stmt = pg_insert(StockCurrent).values(filtered_stock)
        stmt = stmt.on_conflict_do_update(
            index_elements=[StockCurrent.store_id, StockCurrent.article],
            set_={"balance": stmt.excluded.balance, "captured_at": stmt.excluded.captured_at},
        )
        await session.execute(stmt)

    # Set 0 balance for stale items (NOT delete them)
    # Because if they were missing from the warehouse, they have 0 stock!
    stale_managed = allowed_articles - seen_allowed
    if stale_managed:
        stale_rows = [{"store_id": store_id, "article": a, "balance": 0, "captured_at": now, "refreshed_at": now} for a in stale_managed]
        for i in range(0, len(stale_rows), 500):
            stmt = pg_insert(StockCurrent).values(stale_rows[i:i+500])
            stmt = stmt.on_conflict_do_update(
                index_elements=[StockCurrent.store_id, StockCurrent.article],
                set_={"balance": stmt.excluded.balance},
            )
            await session.execute(stmt)

    return len(filtered_stock)
"""

# Replace the old sync_stock_for_existing_products
code = re.sub(r"async def sync_stock_for_existing_products\(.*", new_func, code, flags=re.DOTALL)

with open("src/backend/app/ingestion/stock.py", "w") as f:
    f.write(code)
