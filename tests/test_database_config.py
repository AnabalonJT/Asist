"""Tests for database configuration"""
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.database import Base, engine, AsyncSessionLocal, get_db
from app.config import settings


def test_database_engine_configuration():
    """Test that database engine is properly configured"""
    assert isinstance(engine, AsyncEngine)
    assert engine.pool.__class__ == AsyncAdaptedQueuePool
    assert engine.pool.size() == settings.db_pool_size


def test_session_factory_configuration():
    """Test that async session factory is properly configured"""
    assert isinstance(AsyncSessionLocal, async_sessionmaker)
    # Verify the session factory is properly configured
    assert hasattr(AsyncSessionLocal, 'kw')
    assert AsyncSessionLocal.kw.get("expire_on_commit") is False


def test_base_class_exists():
    """Test that Base declarative class exists"""
    assert Base is not None
    assert hasattr(Base, "metadata")
    # Base itself doesn't have __tablename__, only subclasses do


def test_get_db_generator():
    """Test that get_db is an async generator function"""
    import inspect
    assert inspect.isasyncgenfunction(get_db)


def test_database_url_configuration():
    """Test that database URL is properly configured"""
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert "asyncpg" in settings.database_url


def test_connection_pool_settings():
    """Test that connection pool settings are properly configured"""
    assert settings.db_pool_size >= 10
    assert settings.db_max_overflow >= 10
    assert settings.db_pool_size <= 20  # Within recommended range


@pytest.mark.asyncio
async def test_get_db_context_manager():
    """Test that get_db properly handles context management"""
    # This test verifies the generator structure without actual DB connection
    gen = get_db()
    assert gen is not None
    # Note: We can't fully test this without a real database connection
    # Integration tests will cover actual database operations
