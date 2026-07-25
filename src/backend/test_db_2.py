import asyncio
import sys
sys.path.append("/app")
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from src.backend.app.db.session import async_session_maker
from src.backend.app.models import AggStoreProduct

async def main():
    async with async_session_maker() as session:
        query = select(AggStoreProduct).options(joinedload(AggStoreProduct.product)).limit(5)
        result = await session.execute(query)
        rows = result.scalars().all()
        for row in rows:
            print(f"Article: {row.article}, Rating: {getattr(row.product, 'focus', 'MISSING_PRODUCT')}")

if __name__ == "__main__":
    asyncio.run(main())
