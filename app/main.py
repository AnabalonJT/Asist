
"""Main FastAPI application."""
import logging
from contextlib import asynccontextmanager
 
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
 
from app.config import settings
 
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
 
 
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting HabitTrack API — env=%s debug=%s", settings.environment, settings.debug)

    from app.database import init_db, close_db

    # Ensure tables exist
    await init_db()
    logger.info("Database tables ensured")

    # Telegram: webhook in production, polling in dev
    if settings.use_webhook:
        await _register_webhook()
    else:
        from app.services.telegram_bot import start_polling, stop_polling
        try:
            await start_polling()
        except Exception as e:
            logger.warning("Could not start Telegram polling: %s", e)

    # Start APScheduler for reminders and weekly summaries
    from app.scheduler import start_scheduler, stop_scheduler
    try:
        start_scheduler()
    except Exception as e:
        logger.warning("Could not start scheduler: %s", e)

    yield

    # Shutdown
    try:
        stop_scheduler()
    except Exception:
        pass
    if not settings.use_webhook:
        try:
            from app.services.telegram_bot import stop_polling
            await stop_polling()
        except Exception:
            pass
    await close_db()
    logger.info("HabitTrack API shut down")


async def _register_webhook():
    """Register Telegram webhook URL on startup (production only)."""
    import httpx
    url = f"https://api.telegram.org/bot{settings.bot_token}/setWebhook"
    payload = {
        "url": settings.telegram_webhook_url,
        "allowed_updates": ["message", "edited_message"],
    }
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if data.get("ok"):
                logger.info("Telegram webhook registered: %s", settings.telegram_webhook_url)
            else:
                logger.error("Failed to register webhook: %s", data)
    except Exception as e:
        logger.error("Error registering webhook: %s", e)


app = FastAPI(
    title="HabitTrack API",
    description="Telegram-based habit tracking with web dashboard",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
# ── Routes ────────────────────────────────────────────────────────────────────
from app.routes import auth, telegram, dashboard, activities, reminders, goals  # noqa: E402
 
app.include_router(auth.router,       prefix="/api/auth",       tags=["Auth"])
app.include_router(telegram.router,   prefix="/api/telegram",   tags=["Telegram"])
app.include_router(dashboard.router,  prefix="/api/dashboard",  tags=["Dashboard"])
app.include_router(activities.router, prefix="/api/activities", tags=["Activities"])
app.include_router(reminders.router,  prefix="/api/reminders",  tags=["Reminders"])
app.include_router(goals.router,      prefix="/api/goals",      tags=["Goals"])
 
 
@app.get("/health")
async def health():
    from sqlalchemy import text
    from app.database import AsyncSessionLocal
    db_status = "unknown"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "database": db_status,
    }


# ── Serve frontend static files in production ─────────────────────────────────
import os
from pathlib import Path

_static_dir = Path(__file__).resolve().parent.parent / "static"

if _static_dir.exists() and not settings.debug:
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Fallback: serve index.html for SPA routing."""
        file_path = _static_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_static_dir / "index.html"))
else:
    @app.get("/")
    async def root():
        return {"service": "HabitTrack API", "status": "running", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.debug)