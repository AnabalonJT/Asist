# HabitTrack Backend Setup Guide

## Project Structure

The Python backend project has been initialized with the following structure:

```
f:\Proyectos\Asist\
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application with CORS middleware
│   ├── config.py            # Settings with environment variable loading
│   ├── database.py          # Async SQLAlchemy setup
│   ├── models/              # Database models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── activity.py
│   │   └── reminder.py
│   ├── routes/              # API route handlers
│   │   └── __init__.py
│   └── services/            # Business logic services
│       └── __init__.py
├── tests/
│   ├── __init__.py
│   └── test_main.py         # Basic FastAPI tests
├── alembic/                 # Database migrations
│   ├── versions/
│   └── env.py
├── .env.example             # Environment variables template
├── .gitignore               # Git ignore configuration
├── alembic.ini              # Alembic configuration
├── pytest.ini               # Pytest configuration
├── requirements.txt         # Python dependencies
└── README.md                # Project documentation
```

## Installed Dependencies

All core dependencies have been installed:

- **FastAPI 0.115.0** - Web framework
- **Uvicorn 0.32.0** - ASGI server
- **SQLAlchemy 2.0.36** - ORM with async support
- **asyncpg 0.30.0** - PostgreSQL async driver
- **Alembic 1.13.3** - Database migrations
- **python-telegram-bot 21.7** - Telegram bot integration
- **APScheduler 3.10.4** - Task scheduling
- **bcrypt 4.2.0** - Password hashing
- **PyJWT 2.9.0** - JWT authentication
- **httpx 0.27.2** - HTTP client
- **python-dotenv 1.0.1** - Environment variable loading
- **pytest 8.3.3** - Testing framework
- **pytest-asyncio 0.24.0** - Async test support

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Key configuration items:
- `DATABASE_URL`: PostgreSQL connection string
- `TELEGRAM_BOT_TOKEN`: Telegram bot token from @BotFather
- `OPENROUTER_API_KEY`: OpenRouter API key for LLM
- `JWT_SECRET_KEY`: Secret key for JWT token generation

### FastAPI Application

The main application (`app/main.py`) includes:

✅ FastAPI application initialization
✅ CORS middleware configured for frontend integration
✅ Environment variable loading via pydantic-settings
✅ Lifespan context manager for startup/shutdown
✅ Health check endpoints (`/` and `/health`)
✅ Logging configuration

### CORS Configuration

CORS is configured to allow requests from:
- `http://localhost:3000` (React default)
- `http://localhost:5173` (Vite default)

Additional origins can be added via the `CORS_ORIGINS` environment variable.

## Running the Application

### Development Server

```bash
python -m app.main
```

The server will start on `http://localhost:8000`

### API Documentation

Once running, access:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Testing

### Run All Tests

```bash
python -m pytest tests/ -v
```

### Run Specific Test File

```bash
python -m pytest tests/test_main.py -v
```

### Test Results

All initial tests pass:
- ✅ `test_root_endpoint` - Verifies root endpoint response
- ✅ `test_health_check_endpoint` - Verifies health check endpoint
- ✅ `test_cors_middleware_configured` - Verifies CORS setup

## Requirements Validation

This setup fulfills task 1.1 requirements:

✅ **Project directory structure created**
   - `app/` with `services/`, `models/`, `routes/` subdirectories
   - `tests/` for test files

✅ **requirements.txt with core dependencies**
   - FastAPI, SQLAlchemy, asyncpg
   - python-telegram-bot, APScheduler
   - bcrypt, PyJWT, httpx
   - pydantic and python-dotenv

✅ **app/main.py with FastAPI initialization**
   - Application created with proper configuration
   - Lifespan management for startup/shutdown

✅ **CORS middleware configured**
   - Supports localhost:3000 and localhost:5173
   - Configurable via environment variables

✅ **Environment variable loading**
   - Using python-dotenv
   - Pydantic Settings for type-safe configuration
   - .env.example template provided

## Next Steps

1. **Task 1.2**: Set up Alembic database migrations
2. **Task 1.3**: Define SQLAlchemy database models
3. **Task 1.4**: Implement authentication service
4. Configure PostgreSQL database
5. Set up Telegram bot webhook

## Validation Commands

```bash
# Verify Python version
python --version  # Should be 3.10+

# Verify dependencies installed
pip list | grep fastapi
pip list | grep sqlalchemy

# Import check
python -c "from app.main import app; print('Success')"

# Run tests
python -m pytest tests/test_main.py -v
```

All validation commands should execute successfully.
