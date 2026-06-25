"""Tests for Alembic migrations"""
import os
from pathlib import Path


def test_alembic_directory_exists():
    """Test that Alembic directory structure exists"""
    alembic_dir = Path("alembic")
    assert alembic_dir.exists()
    assert (alembic_dir / "env.py").exists()
    assert (alembic_dir / "script.py.mako").exists()
    assert (alembic_dir / "versions").exists()


def test_alembic_ini_exists():
    """Test that alembic.ini configuration file exists"""
    assert Path("alembic.ini").exists()


def test_initial_migration_exists():
    """Test that initial database migration exists"""
    versions_dir = Path("alembic/versions")
    migrations = list(versions_dir.glob("*.py"))
    
    # Filter out __pycache__ and __init__.py files
    migrations = [m for m in migrations if not m.name.startswith("__")]
    
    assert len(migrations) >= 1, "At least one migration should exist"
    
    # Check that the initial migration exists
    initial_migrations = [m for m in migrations if "initial" in m.name.lower()]
    assert len(initial_migrations) >= 1, "Initial migration should exist"


def test_migration_file_structure():
    """Test that migration files have proper structure"""
    versions_dir = Path("alembic/versions")
    migrations = list(versions_dir.glob("*.py"))
    migrations = [m for m in migrations if not m.name.startswith("__")]
    
    for migration in migrations:
        content = migration.read_text()
        
        # Check for required migration components
        assert "revision:" in content or "revision =" in content, f"Migration {migration.name} missing revision"
        assert "down_revision" in content, f"Migration {migration.name} missing down_revision"
        assert "def upgrade()" in content, f"Migration {migration.name} missing upgrade function"
        assert "def downgrade()" in content, f"Migration {migration.name} missing downgrade function"


def test_env_py_has_async_support():
    """Test that Alembic env.py is configured for async"""
    env_path = Path("alembic/env.py")
    content = env_path.read_text()
    
    # Check for async configuration
    assert "async" in content, "env.py should have async support"
    assert "run_async_migrations" in content, "env.py should have run_async_migrations function"
    assert "async_engine_from_config" in content, "env.py should use async_engine_from_config"


def test_alembic_ini_configuration():
    """Test that alembic.ini has proper configuration"""
    ini_path = Path("alembic.ini")
    content = ini_path.read_text()
    
    # Check for required configuration
    assert "[alembic]" in content, "alembic.ini should have [alembic] section"
    assert "script_location = alembic" in content, "alembic.ini should specify script_location"
