import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    engine = create_async_engine("sqlite+aiosqlite:///test.db", echo=True)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        print(result.scalar())


if __name__ == "__main__":
    asyncio.run(main())
