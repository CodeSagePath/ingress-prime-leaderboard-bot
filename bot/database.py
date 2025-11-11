from contextlib import asynccontextmanager
from typing import AsyncIterator
import os

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import Settings


class Base(DeclarativeBase):
    pass


def build_engine(settings: Settings) -> AsyncEngine:
    # Optimize for better performance on old Android devices
    return create_async_engine(
        settings.database.url,
        echo=False,
        future=True,
        pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),  # Configurable pool size
        max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),  # Configurable overflow
        pool_pre_ping=True,  # Check connections before use
        pool_recycle=int(os.environ.get("DB_POOL_RECYCLE", "3600")),  # Configurable connection recycling
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_models(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
