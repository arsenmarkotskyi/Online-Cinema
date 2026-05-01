import pytest
from sqlalchemy import text

from src.database.session import AsyncSQLiteSessionLocal


@pytest.mark.asyncio
async def test_async_db_select_one():
    async with AsyncSQLiteSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
