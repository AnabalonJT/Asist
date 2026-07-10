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
    category: str = "sport"  # "sport", "strength", "habit", "life"
    duration_minutes: int | None = None
    distance_km: float | None = None
    detail: str | None = None
    exercise_name: str | None = None
    sets: list | None = None
    confidence: float = 0.0


@dataclass
class ReminderData:
    """Structured reminder data extracted from a message."""
    action: str  # "create", "list", "delete", "pause"
    message: str | None = None
    schedule: str | None = None  # HH:MM format
    frequency: str = "daily"
    schedule_days: str | None = None  # "0,2,4" for Mon,Wed,Fri
    schedule_date: str | None = None  # "2026-07-06" for one-time


@dataclass
class GoalData:
    """Structured goal data extracted from a message."""
    action: str  # "create", "list", "delete"
    activity_type: str | None = None
    target_count: int = 1
    period: str = "weekly"  # "daily", "weekly", "monthly"
    description: str | None = None
    ends_at: str | None = None  # "YYYY-MM-DD" or None (forever)


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
    "category": "sport" | "strength" | "habit" | "life",
    "duration_minutes": number o null,
    "distance_km": number o null,
    "detail": "string o null (detalle extra: peso, series, reps, libro, etc)",
    "exercise_name": "string o null (nombre del ejercicio para fuerza: Press Banca, Sentadillas, etc)",
    "sets": [{"reps": number, "weight_kg": number}] o null (series para fuerza),
    "confidence": 0.0-1.0
  }
}

Categorías:
- "sport": actividades cardiovasculares (correr, nadar, bici, caminar, hiking, basketball, etc)
- "strength": ejercicios de fuerza/pesas (press banca, sentadillas, peso muerto, dominadas, gym con pesas, crossfit)
- "habit": hábitos y actividades no-deportivas (meditar, leer, estudiar, stretching, journaling)
- "life": registros de vida cotidiana (comer, ir al baño, ver película, cocinar, limpiar, dormir, etc)

## Si intent="reminder" (el usuario quiere crear/ver/gestionar recordatorios):
{
  "intent": "reminder",
  "data": {
    "action": "create" | "list" | "delete" | "pause",
    "message": "string (qué recordar, ej: 'meditar')",
    "schedule": "HH:MM (hora del recordatorio)" o null,
    "frequency": "daily" | "weekdays" | "weekends" | "specific_days" | "once" | "biweekly",
    "schedule_days": "string CSV de días (0=lun,1=mar,2=mie,3=jue,4=vie,5=sab,6=dom)" o null,
    "schedule_date": "YYYY-MM-DD" o null (para recordatorios únicos)
  }
}

Ejemplos de recordatorios:
- "recuérdame meditar a las 8am" → create, message="meditar", schedule="08:00", frequency="daily"
- "recordatorio de correr los lunes y miércoles a las 7:30" → create, message="correr", schedule="07:30", frequency="specific_days", schedule_days="0,2"
- "el lunes 6 de julio a las 8am ir al Dr" → create, message="ir al Dr", schedule="08:00", frequency="once", schedule_date="2026-07-06"
- "recordatorio de gym solo fines de semana a las 10" → create, message="gym", schedule="10:00", frequency="weekends"
- "recuérdame estudiar de lunes a viernes a las 20:00" → create, message="estudiar", schedule="20:00", frequency="weekdays"
- "recuerdame que el domingo 5 de julio a las 11:20 tengo que ver horarios de banco" → create, message="ver horarios de banco", schedule="11:20", frequency="once", schedule_date="2026-07-05"
- "el martes a las 3pm tengo dentista" → create, message="dentista", schedule="15:00", frequency="once"
- "mis recordatorios" → list
- "borra el recordatorio de meditar" → delete, message="meditar"

IMPORTANTE: Si el usuario dice "recuérdame", "recuerdame", "no olvides", "tengo que", "acuérdame" + una fecha/hora, SIEMPRE es intent="reminder" aunque tenga errores de tipeo.

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

## Si intent="goal" (el usuario quiere crear/ver/eliminar metas):
{
  "intent": "goal",
  "data": {
    "action": "create" | "list" | "delete",
    "activity_type": "string (tipo de actividad de la meta)",
    "target_count": number (cuántas veces por periodo),
    "period": "daily" | "weekly" | "monthly",
    "description": "string (descripción legible de la meta)",
    "ends_at": "YYYY-MM-DD" o null (fecha de término, null = para siempre)
  }
}

Ejemplos de metas:
- "quiero correr 3 veces por semana" → create, activity_type="running", target_count=3, period="weekly", ends_at=null
- "meta: meditar todos los días por 75 días" → create, activity_type="meditation", target_count=1, period="daily", ends_at=(fecha actual + 75 días)
- "ir al gym 4 veces por semana hasta el 2 de septiembre" → create, activity_type="gym", target_count=4, period="weekly", ends_at="2026-09-02"
- "correr diario por 3 meses" → create, activity_type="running", target_count=1, period="daily", ends_at=(fecha actual + 90 días)
- "mis metas" → list
- "eliminar meta de correr" → delete, activity_type="running"

## Si el usuario quiere crear un DESAFÍO (múltiples metas agrupadas):
{
  "intent": "challenge",
  "data": {
    "name": "string (nombre del desafío)",
    "ends_at": "YYYY-MM-DD" o null,
    "goals": [
      {"activity_type": "string", "target_count": number, "period": "daily"|"weekly"|"monthly", "description": "string"},
      ...
    ]
  }
}

Ejemplos de desafíos:
- "durante 75 días quiero hacer deporte, mi cama y meditar" → challenge, name="75 días de disciplina", ends_at=(+75 días), goals=[{activity_type:"gym",target_count:1,period:"daily"},{activity_type:"cama",target_count:1,period:"daily"},{activity_type:"meditation",target_count:1,period:"daily"}]
- "3 meses: correr 3 veces por semana y meditar todos los días" → challenge, name="Desafío 3 meses", ends_at=(+90 días), goals=[{activity_type:"running",target_count:3,period:"weekly"},{activity_type:"meditation",target_count:1,period:"daily"}]
- "desafío: leer y estudiar todos los días por 30 días" → challenge, name="30 días de estudio", ends_at=(+30 días), goals=[...]

REGLA: Si el mensaje menciona MÚLTIPLES actividades con una duración compartida (X días, X meses, etc), es un "challenge". Si es solo UNA actividad, es un "goal".

Reglas importantes:
- "Levanté 100kg en press banca" → activity, category="strength", exercise_name="Press Banca", sets=[{"reps":1,"weight_kg":100}]
- "Hice 4 series de sentadillas con 80kg" → activity, category="strength", exercise_name="Sentadillas", sets=[{"reps":10,"weight_kg":80},{"reps":10,"weight_kg":80},{"reps":10,"weight_kg":80},{"reps":10,"weight_kg":80}]
- "10x4 con 50kg pressbanca" = 4 series de 10 reps → exercise_name="Press Banca", sets=[{"reps":10,"weight_kg":50},{"reps":10,"weight_kg":50},{"reps":10,"weight_kg":50},{"reps":10,"weight_kg":50}]
- "Press banca 10 reps 40kg, 10 reps 50kg, 8x60kg" → sets=[{"reps":10,"weight_kg":40},{"reps":10,"weight_kg":50},{"reps":8,"weight_kg":60}]
- Para strength: activity_type siempre "weights", exercise_name = nombre real del ejercicio
- "Corrí 5km" → activity, category="sport"
- "Leí 30 min" → activity, category="habit"
- "Medité 10 minutos" → activity, category="habit"
- "Comí almuerzo" → activity, category="life", activity_type="comer", detail="almuerzo"
- "Fui al baño" o "hice caca" → activity, category="life", activity_type="baño"
- "Vi una película" → activity, category="life", activity_type="película", detail="película"
- "Cociné" → activity, category="life", activity_type="cocinar"
- "Dormí 7 horas" → activity, category="life", activity_type="dormir", duration_minutes=420
- "Tomé agua" → activity, category="life", activity_type="agua"
- CUALQUIER cosa que el usuario diga que HIZO es una actividad válida. Si dice que hizo algo, registrarlo.
- Si no tiene duración obvia, duration_minutes puede ser null
- Series/reps sin duración: estima (4 series ≈ 8 min, sesión completa ≈ 45 min)
- "hola", "cómo va", preguntas que NO describen algo que hicieron → chat
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
        exercise_name=activity.get("exercise_name"),
        sets=activity.get("sets"),
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
        schedule_days=reminder.get("schedule_days"),
        schedule_date=reminder.get("schedule_date"),
    )


def parse_goal(data: dict) -> GoalData | None:
    """Parse goal data from LLM response."""
    goal = data.get("data", {})
    action = goal.get("action")
    if not action:
        return None

    return GoalData(
        action=action,
        activity_type=goal.get("activity_type"),
        target_count=goal.get("target_count", 1),
        period=goal.get("period", "weekly"),
        description=goal.get("description"),
        ends_at=goal.get("ends_at"),
    )


async def _call_llm(user_message: str) -> str | None:
    """Call OpenRouter API and return the raw response text."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    # Inject current date so LLM can resolve relative dates
    now = datetime.now(ZoneInfo("America/Santiago"))
    date_prefix = f"[Fecha actual: {now.strftime('%Y-%m-%d')} ({now.strftime('%A')}), {now.strftime('%H:%M')}] "

    url = f"{settings.openrouter_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": date_prefix + user_message},
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
