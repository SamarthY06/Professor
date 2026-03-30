"""
Database configuration and session management.

Connection Pooling Strategy (Gunicorn-aware):
- pool_size=5: Per-worker base connections (4 workers x 5 = 20 total)
- max_overflow=3: Per-worker overflow (4 workers x 3 = 12 overflow, 32 max)
- pool_pre_ping=True: Validates connections before use (prevents stale connections)
- pool_recycle=1800: Recycle connections every 30 min (prevents timeout issues)
- pool_timeout=30: Wait max 30s for a connection from pool
"""

from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.config import settings


# Create async engine with optimized connection pooling
engine = create_async_engine(
    settings.database_url,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=5,            # Per-worker (4 workers x 5 = 20 total)
    max_overflow=3,         # Per-worker overflow (4 workers x 3 = 12)
    pool_pre_ping=True,     # Validate connections before use
    pool_recycle=1800,      # Recycle every 30 min
    pool_timeout=30,        # Wait max 30s for connection
    echo=settings.debug and settings.environment == "development",
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Alias for background tasks
async_session_maker = AsyncSessionLocal


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_db_context():
    """
    Context manager for database sessions.
    
    Use this for background tasks and non-FastAPI code:
    
        async with get_db_context() as db:
            result = await db.execute(query)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_pool_status() -> dict:
    """Get connection pool status for monitoring."""
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalidatedcount() if hasattr(pool, 'invalidatedcount') else 0,
    }
