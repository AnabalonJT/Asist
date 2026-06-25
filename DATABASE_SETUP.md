# Database Setup Guide

## Prerequisites

1. Install PostgreSQL 14+ on your system
2. Create a database for the application

## Database Creation

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE habittrack;

# Create user (optional, for production)
CREATE USER habittrack_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE habittrack TO habittrack_user;
```

## Configuration

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Update the `DATABASE_URL` in `.env`:
   ```
   DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/habittrack
   ```

## Database Migration

The project uses Alembic for database migrations with async SQLAlchemy support.

### Initial Migration

Generate the initial migration (after models are created):

```bash
python -m alembic revision --autogenerate -m "Initial database schema"
```

### Apply Migrations

```bash
python -m alembic upgrade head
```

### Other Useful Commands

```bash
# Check current migration version
python -m alembic current

# View migration history
python -m alembic history

# Downgrade to previous version
python -m alembic downgrade -1

# Downgrade to specific version
python -m alembic downgrade <revision_id>

# Create empty migration (manual changes)
python -m alembic revision -m "description"
```

## Connection Pooling

The application is configured with asyncpg connection pooling:

- **Pool Size**: 10-20 connections (configurable via `DB_POOL_SIZE`)
- **Max Overflow**: 10 additional connections (configurable via `DB_MAX_OVERFLOW`)
- **Pool Pre-Ping**: Enabled (validates connections before use)
- **Pool Recycle**: 3600 seconds (1 hour)

## Database Architecture

### Tables

- **users**: User accounts with Telegram linking
- **activities**: Activity logs with type, duration, distance, calories
- **reminders**: Scheduled reminders for habits
- **linking_tokens**: One-time tokens for Telegram account linking
- **calorie_formulas**: Activity-specific calorie calculation formulas

### Indexes

Performance indexes are created on:
- User email and telegram_chat_id (lookups)
- Activity user_id and timestamp (queries)
- Linking token values (validation)

See the design document for detailed schema information.

## Async SQLAlchemy Usage

The application uses async SQLAlchemy with asyncpg driver:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User

async def get_user(db: AsyncSession, user_id: int):
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()
```

## Troubleshooting

### Connection Errors

If you see connection errors:
1. Verify PostgreSQL is running: `psql -U postgres -l`
2. Check DATABASE_URL in .env matches your setup
3. Ensure asyncpg is installed: `pip install asyncpg`

### Migration Conflicts

If autogenerate creates unexpected migrations:
1. Review the generated migration file in `alembic/versions/`
2. Edit if needed before applying
3. Always test migrations on dev database first

### Pool Exhaustion

If you see "pool exhausted" errors:
1. Increase DB_POOL_SIZE in .env
2. Check for connection leaks (unclosed sessions)
3. Verify long-running transactions are properly committed
