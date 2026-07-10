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
    settings.async_database_url,
    echo=settings.db_echo,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    pool_recycle=3600,
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
    Initialize database: ensure all tables exist and columns are up-to-date.
    create_all is idempotent — safe to call even if tables already exist.
    """
    async with engine.begin() as conn:
        # Import all models to register them with Base.metadata
        from app.models import user, activity, reminder, linking_token, calorie_formula, goal, challenge  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

    # Add missing columns to existing tables (create_all doesn't do ALTER TABLE)
    await _migrate_columns()


async def close_db() -> None:
    """
    Close database connections.
    This should be called on application shutdown.
    """
    await engine.dispose()


async def _migrate_columns() -> None:
    """Add missing columns to existing tables. Safe to run multiple times."""
    import logging
    logger = logging.getLogger(__name__)

    migrations = [
        # (table, column, SQL type, default)
        ("reminders", "schedule_days", "VARCHAR(50)", None),
        ("reminders", "schedule_date", "VARCHAR(20)", None),
        ("activities", "exercise_name", "VARCHAR(100)", None),
        ("activities", "sets_data", "VARCHAR(500)", None),
        ("users", "timezone", "VARCHAR(50)", "'America/Santiago'"),
        ("goals", "ends_at", "VARCHAR(20)", None),
        ("goals", "challenge_id", "INTEGER", None),
    ]

    async with engine.begin() as conn:
        for table, column, col_type, default in migrations:
            try:
                # Check if column exists
                check_sql = f"""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='{table}' AND column_name='{column}'
                """
                from sqlalchemy import text
                result = await conn.execute(text(check_sql))
                if result.scalar() is None:
                    # Column doesn't exist, add it
                    default_clause = f" DEFAULT {default}" if default else ""
                    alter_sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}"
                    await conn.execute(text(alter_sql))
                    logger.info("Added column %s.%s", table, column)
            except Exception as e:
                logger.warning("Migration check for %s.%s: %s", table, column, e)
