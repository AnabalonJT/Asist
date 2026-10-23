# Tech Stack & Build System

## Backend (Python)

- **Framework**: FastAPI 0.115 with async lifespan
- **Python version**: 3.11 (Docker) / 3.10+ minimum
- **ORM**: SQLAlchemy 2.0 with async support (asyncpg driver)
- **Database**: PostgreSQL 16
- **Migrations**: Alembic
- **Auth**: JWT (PyJWT) + bcrypt password hashing
- **Telegram**: python-telegram-bot 21.7 (polling in dev, webhook in production)
- **LLM**: OpenRouter API via httpx (model: nvidia/nemotron-3-ultra-550b-a55b:free)
- **Scheduling**: APScheduler 3.10
- **Settings**: pydantic-settings with `.env` file loading
- **HTTP client**: httpx 0.27

## Frontend (TypeScript/React)

- **Framework**: React 19 with TypeScript 6
- **Build tool**: Vite 8
- **Styling**: Tailwind CSS 3.4 + PostCSS + Autoprefixer
- **Routing**: react-router-dom 7
- **HTTP client**: axios
- **Served by**: FastAPI static files mount in production

## Infrastructure

- **Containerization**: Docker multi-stage build (Node for frontend, Python for backend)
- **Orchestration**: Docker Compose (postgres + app)
- **Deployment targets**: Fly.io (fly.toml), Railway (railway.toml)

## Common Commands

```bash
# Run everything locally (recommended)
docker compose up --build

# Stop
docker compose down

# Reset database (destructive)
docker compose down -v

# Run backend tests
pytest tests/

# Frontend dev (from src/ directory)
cd src && npm run dev

# Frontend build (from src/ directory)
cd src && npm run build

# Run alembic migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"
```

## Testing

- **Framework**: pytest with pytest-asyncio (auto mode)
- **Coverage**: pytest-cov
- **Property-based testing**: Hypothesis (`.hypothesis/` directory present)
- **Test location**: `tests/` directory
- **Markers**: `unit`, `integration`, `asyncio`
- **Config**: `pytest.ini` at project root
