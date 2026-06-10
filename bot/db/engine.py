"""
Moteur de base de données async + fabrique de sessions.

Compatible SQLite (local) et PostgreSQL (Railway), au choix via DATABASE_URL.
On expose :
  - `init_engine()` : crée le moteur et applique le schéma (create_all en secours
    si Alembic n'a pas été lancé — pratique pour un premier boot sur Railway).
  - `session_scope()` : context manager async qui commit/rollback proprement.
  - `dispose_engine()` : fermeture propre au shutdown.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import get_settings
from bot.models.base import Base
from bot.utils.logging_config import get_logger

log = get_logger("db")

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


async def init_engine() -> None:
    """Initialise le moteur global et garantit l'existence du schéma."""
    global _engine, _sessionmaker
    if _engine is not None:
        return

    settings = get_settings()
    # Pour SQLite async, on désactive le pooling figé qui pose problème en async.
    connect_args = {}
    engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        connect_args = {"timeout": 30}
        engine_kwargs.pop("pool_pre_ping")  # inutile/incompatible avec SQLite

    _engine = create_async_engine(
        settings.database_url, connect_args=connect_args, **engine_kwargs
    )
    _sessionmaker = async_sessionmaker(
        _engine, expire_on_commit=False, class_=AsyncSession
    )

    # Filet de sécurité : crée les tables si elles n'existent pas encore.
    # En prod on s'appuie sur Alembic, mais ceci évite un crash au tout premier boot.
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    log.info("db.initialized", backend="postgres" if settings.is_postgres else "sqlite")


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("init_engine() doit être appelé avant get_sessionmaker()")
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Fournit une session transactionnelle avec commit/rollback automatiques."""
    maker = get_sessionmaker()
    session = maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engine() -> None:
    """Ferme proprement le pool de connexions."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        log.info("db.disposed")
