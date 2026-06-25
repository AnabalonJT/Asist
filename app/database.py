"""Database configuration with async SQLAlchemy and session management"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models"""
    pass


# Create async engine with connection pooling
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to provide database session to FastAPI routes.
    
    Yields:
        AsyncSession: Database session that will be automatically closed
        
    Example:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
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


async def init_db() -> None:
    """
    Initialize database: ensure all tables exist.
    create_all is idempotent — safe to call even if tables already exist.
    """
    async with engine.begin() as conn:
        # Import all models to register them with Base.metadata
        from app.models import user, activity, reminder, linking_token, calorie_formula  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close database connections.
    This should be called on application shutdown.
    """
    await engine.dispose()
