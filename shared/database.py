"""
Database connectie - Async SQLAlchemy engine.

Ondersteunt PostgreSQL (productie) en SQLite (development).
Keuze op basis van USE_SQLITE env var of afwezigheid van asyncpg.

Gebruik:
    from shared.database import get_db, engine

    # In FastAPI endpoint:
    async def my_endpoint(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(User))
        users = result.scalars().all()
"""

import os
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.config.settings import config


def _get_database_url() -> str:
    """Bepaal database URL op basis van omgeving."""
    # Railway/Render/Fly zetten DATABASE_URL automatisch
    railway_url = os.getenv("DATABASE_URL", "")
    if railway_url:
        # Railway geeft postgresql://, SQLAlchemy async wil postgresql+asyncpg://
        if railway_url.startswith("postgresql://"):
            return railway_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return railway_url

    use_sqlite = os.getenv("USE_SQLITE", "").lower() in ("1", "true", "yes")

    if use_sqlite or config.is_development:
        # Probeer asyncpg; als niet beschikbaar, gebruik SQLite
        try:
            import asyncpg  # noqa: F401
            return config.db.async_dsn
        except ImportError:
            db_path = Path(os.getenv("SQLITE_PATH", "./data/dev.db"))
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite+aiosqlite:///{db_path}"
    return config.db.async_dsn


DATABASE_URL = _get_database_url()
_is_sqlite = DATABASE_URL.startswith("sqlite")

# Engine kwargs afhankelijk van backend
_engine_kwargs = {
    "echo": config.is_development,
}
if not _is_sqlite:
    _engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 5,
        "pool_pre_ping": True,
    })

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)

# SQLite: foreign keys aanzetten (standaard uitgeschakeld)
if _is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

# Session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """FastAPI dependency: geeft een database sessie."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Initialiseer database: test connectie en maak tabellen aan (dev)."""
    if _is_sqlite:
        from shared.models.base import Base
        # Importeer alle models zodat ze geregistreerd worden
        import shared.models  # noqa: F401
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))


async def close_db():
    """Sluit de database connectie pool."""
    await engine.dispose()
