"""Telegram webhook route.

Handles:
- /start <token>  → link Telegram account to web account
- Any other text  → placeholder for LLM activity parsing (next phase)
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.auth_service import AuthError, auth_service

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Telegram send helper (lightweight, no PTB needed for webhooks) ────────────

async def _send(chat_id: int, text: str) -> None:
    """Fire-and-forget Telegram sendMessage via httpx."""
    import httpx

    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json={"chat_id": chat_id, "text": text})
    except Exception as e:
        logger.warning("Failed to send Telegram message to %s: %s", chat_id, e)


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/webhook")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive Telegram updates via webhook."""

    # Optional secret token validation
    if settings.telegram_webhook_secret:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_secret != settings.telegram_webhook_secret:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bad secret")

    try:
        update: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}  # Ignore non-message updates

    chat_id: int = message["chat"]["id"]
    text: str = message.get("text", "").strip()

    if not text:
        return {"ok": True}

    # ── /start <token> ────────────────────────────────────────────────────────
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await _send(chat_id, "👋 Envía /start <token> para vincular tu cuenta.")
            return {"ok": True}

        token = parts[1].strip()
        try:
            user = await auth_service.validate_linking_token(db, token)
        except AuthError as e:
            logger.info("Invalid linking token %s: %s", token, e)
            return {"ok": True}  # Ignore silently per spec

        # Save telegram_chat_id on user
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(telegram_chat_id=chat_id)
        )
        await _send(chat_id, "✅ ¡Cuenta vinculada! Ya puedes registrar actividades.")
        logger.info("Linked telegram_chat_id=%s to user_id=%s", chat_id, user.id)
        return {"ok": True}

    # ── Regular message from linked user ──────────────────────────────────────
    result = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
    user = result.scalar_one_or_none()

    if not user:
        # Unlinked user — ignore per spec
        return {"ok": True}

    # TODO (next phase): pass text to LLM service for activity parsing
    await _send(
        chat_id,
        f"📝 Recibido: \"{text}\"\n\n⚙️ El procesamiento de actividades estará disponible pronto.",
    )
    return {"ok": True}