"""Async SQLAlchemy engine + session factory for Bella Casa Postgres."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _build_url() -> str:
    url = os.getenv('DATABASE_URL', '')
    if not url:
        raise RuntimeError('DATABASE_URL is not set')
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://') :]
    if url.startswith('postgresql://'):
        url = 'postgresql+asyncpg://' + url[len('postgresql://') :]
    return url


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    if _sessionmaker is None:
        _engine = create_async_engine(
            _build_url(),
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=1800,
            future=True,
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _sessionmaker


def async_session() -> AsyncSession:
    """Retorna uma nova sessão. Use como context manager: `async with async_session() as s:`."""
    return _get_sessionmaker()()


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-friendly context manager com commit/rollback automático."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
