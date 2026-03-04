"""Async database session and engine for API."""
import os
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://iot:iot_secret@localhost:5432/iot_platform"
)
# asyncpg uses postgresql+asyncpg://
ASYNC_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    ASYNC_URL,
    echo=os.environ.get("SQL_ECHO", "0") == "1",
    pool_size=10,
    max_overflow=20,
)
SessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Verify connectivity; schema is applied via init scripts in Docker."""
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))


async def close_db() -> None:
    await engine.dispose()


async def db_healthy() -> bool:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
