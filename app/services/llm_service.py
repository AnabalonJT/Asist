"""LLM service for interpreting activity messages via OpenRouter."""
import json
import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ActivityData:
    """Structured activity data extracted from a message."""
    activity_type: str
    category: str = "sport"  # "sport", "strength", "habit"
    duration_minutes: int | None = None
    distance_km: float | None = None
    detail: str | None = None  # e.g. "4x100kg press banca"
    confidence: float = 0.0


@dataclass
class ReminderData:
    """Structured reminder data extracted from a message."""
    action: str  # "create", "list", "delete", "pause"
    message: str | None = None
    schedule: str | None = None  # HH:MM format
    frequency: str = "daily"


SYSTEM_PROMPT = """Eres un asistente de seguimiento de hábitos y deportes. Tu trabajo es interpretar mensajes del usuario y clasificarlos.

Responde SIEMPRE en formato JSON con esta estructura:
{
  "intent": "activity" | "reminder" | "chat",
  "data": { ... }
}

## Si intent="activity" (el usuario registra algo que hizo):
{
  "intent": "activity",
  "data": {
    "activity_type": "string (running, walking, cycling, gym, swimming, yoga, hiking, weights, crossfit, stretching, basketball, football, tennis, dance, meditation, reading, study, strength, cardio)",
    "category": "sport" | "strength" | "habit",
    "duration_minutes": number o null,
    "distance_km": number o null,
    "detail": "string o null (detalle extra: peso, series, reps, libro, etc)",
    "confidence": 0.0-1.0
  }
}

Categorías:
- "sport": actividades cardiovasculares (correr, nadar, bici, caminar, hiking, basketball, etc)
- "strength": ejercicios de fuerza/pesas (press banca, sentadillas, peso muerto, dominadas, gym con pesas, crossfit)
- "habit": hábitos no-deportivos (meditar, leer, estudiar, stretching, journaling)

## Si intent="reminder" (el usuario quiere crear/ver/gestionar recordatorios):
{
  "intent": "reminder",
  "data": {
    "action": "create" | "list" | "delete" | "pause",
    "message": "string (qué recordar, ej: 'meditar')",
    "schedule": "HH:MM (hora del recordatorio)" o null,
    "frequency": "daily" | "weekly" | "weekdays"
  }
}

Ejemplos de recordatorios:
- "recuérdame meditar a las 8am" → create, message="meditar", schedule="08:00", frequency="daily"
- "ponme un recordatorio de correr a las 7:30" → create, message="correr", schedule="07:30"
- "mis recordatorios" o "qué recordatorios tengo" → list
- "borra el recordatorio de meditar" → delete, message="meditar"
- "pausa recordatorios" → pause

## Si intent="chat" (conversación general, preguntas, saludos):
{
  "intent": "chat",
  "data": {}
}

## Si intent="timezone" (el usuario quiere cambiar su zona horaria):
{
  "intent": "timezone",
  "data": {
    "timezone": "string (formato IANA, ej: America/Santiago, America/Mexico_City, Europe/Madrid)"
  }
}

Ejemplos de timezone:
- "mi zona es America/Santiago" → timezone="America/Santiago"
- "estoy en México" → timezone="America/Mexico_City"
- "zona horaria España" → timezone="Europe/Madrid"
- "cambiar timezone a America/Bogota" → timezone="America/Bogota"
  "data": {}
}

Reglas importantes:
- "Levanté 100kg en press banca" → activity, category="strength", detail="100kg press banca"
- "Hice 4 series de sentadillas con 80kg" → activity, category="strength", detail="4x80kg sentadillas"
- "Corrí 5km" → activity, category="sport"
- "Leí 30 min" → activity, category="habit"
- "Medité 10 minutos" → activity, category="habit"
- Series/reps sin duración: estima (4 series ≈ 8 min, sesión completa ≈ 45 min)
- "hola", "cómo va", preguntas → chat
- Responde SOLO JSON, sin texto adicional"""


REMINDER_PROMPT = """placeholder"""  # not used separately


async def interpret_message(message: str) -> dict | None:
    """
    Interpret a user message. Returns a dict with 'intent' and 'data'.
    Intent can be: 'activity', 'reminder', 'chat'
    """
    try:
        result = await _call_llm(message)
        if not result:
            return None

        data = json.loads(result)
        return data

    except json.JSONDecodeError as e:
        logger.warning("LLM returned non-JSON response: %s", e)
        return None
    except Exception as e:
        logger.exception("Error interpreting message: %s", e)
        return None


def parse_activity(data: dict) -> ActivityData | None:
    """Parse activity data from LLM response."""
    activity = data.get("data", {})
    confidence = float(activity.get("confidence", 0.0))
    if confidence < 0.3:
        return None

    return ActivityData(
        activity_type=activity.get("activity_type", "unknown"),
        category=activity.get("category", "sport"),
        duration_minutes=activity.get("duration_minutes"),
        distance_km=activity.get("distance_km"),
        detail=activity.get("detail"),
        confidence=confidence,
    )


def parse_reminder(data: dict) -> ReminderData | None:
    """Parse reminder data from LLM response."""
    reminder = data.get("data", {})
    action = reminder.get("action")
    if not action:
        return None

    return ReminderData(
        action=action,
        message=reminder.get("message"),
        schedule=reminder.get("schedule"),
        frequency=reminder.get("frequency", "daily"),
    )


async def _call_llm(user_message: str) -> str | None:
    """Call OpenRouter API and return the raw response text."""
    url = f"{settings.openrouter_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.1,
        "max_tokens": 300,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code == 429:
            logger.warning("OpenRouter rate limited")
            return None

        if response.status_code != 200:
            logger.error("OpenRouter error %s: %s", response.status_code, response.text[:200])
            return None

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            logger.warning("OpenRouter returned empty choices")
            return None

        content = choices[0].get("message", {}).get("content", "")
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n", 1)
            content = lines[1] if len(lines) > 1 else ""
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        logger.debug("LLM response: %s", content[:300])
        return content

    except httpx.TimeoutException:
        logger.warning("OpenRouter timeout (15s)")
        return None
    except Exception as e:
        logger.exception("OpenRouter request failed: %s", e)
        return None
