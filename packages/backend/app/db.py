"""SQLAlchemy async 엔진 및 세션 팩토리."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import settings

engine = create_async_engine(
    settings.async_database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI Depends 용 DB 세션 제공자.

    사용:
        async def route(session: AsyncSession = Depends(get_session)): ...
    """
    async with SessionLocal() as session:
        yield session
