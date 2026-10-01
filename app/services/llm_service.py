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

## Si intent="fitness" (el usuario pide o consulta su rutina de entrenamiento):
{
  "intent": "fitness",
  "data": {
    "action": "generate" | "view",
    "goal_type": "gain_muscle" | "lose_weight" | "maintain" | null,
    "equipment": ["..."] o null,
    "days_per_week": number o null
  }
}

Ejemplos de fitness:
- "genérame una rutina para ganar músculo 4 días" → generate, goal_type="gain_muscle", days_per_week=4
- "quiero una rutina de entrenamiento" → generate
- "mi rutina" / "ver mi rutina" → view

## Si intent="meal" (el usuario pide, arma o consulta su plan de comidas):
{
  "intent": "meal",
  "data": {
    "action": "generate" | "view",
    "foods": ["..."] o null (alimentos que el usuario dice tener, ej: "tengo pollo, arroz..."),
    "goal_type": "gain_muscle" | "lose_weight" | "maintain" | null
  }
}

Ejemplos de comidas:
- "dame un plan de comidas" → generate
- "qué como esta semana" / "menú de la semana" → generate
- "tengo pollo, arroz y huevos, arma mi plan" → generate, foods=["pollo","arroz","huevos"]
- "plan de comidas para bajar de peso" → generate, goal_type="lose_weight"
- "ver mi plan de comidas" / "mi plan" → view

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


# ── Workout plan generation (Fitness_Coach, Req 5.1, 6.1-6.3) ────────────────
# NOTE: this template contains literal JSON braces, so it must NOT be passed
# through str.format(). The variable rules are built separately in
# _build_workout_prompt() and concatenated.
WORKOUT_SYSTEM_PROMPT = """Eres un entrenador personal. Genera una rutina de entrenamiento en JSON.
Devuelve SOLO JSON con esta estructura, sin texto adicional:
{
  "days": [
    {
      "day": "Día 1 - Empuje",
      "exercises": [
        {"name": "Press banca", "sets": 4, "reps": 10,
         "duration_seconds": null, "rest_seconds": 90, "equipment": "banco"}
      ]
    }
  ]
}
"""


def _build_workout_prompt(
    days_per_week, equipment_text: str, level, goal_desc: str, activity_summary_text: str
) -> str:
    """Compose the full workout system prompt WITHOUT str.format (the JSON example
    above contains literal braces). Rules are appended as plain text.
    """
    rules = (
        "Reglas (síguelas al pie de la letra):\n"
        f"- Genera EXACTAMENTE {days_per_week} días. MÁXIMO 5 ejercicios por día.\n"
        f"- Usa ÚNICAMENTE este equipo disponible: {equipment_text}. "
        "No uses equipo fuera de esa lista.\n"
        "- Cada ejercicio: sets(1-20)+reps(1-100) O duration_seconds(1-7200), y rest_seconds(0-3600). "
        "Si usas sets+reps, pon duration_seconds en null; si usas duración, pon sets y reps en null.\n"
        f"- Ajusta al nivel ({level}) y al objetivo ({goal_desc}).\n"
        "- El campo \"equipment\" de cada ejercicio debe ser uno de la lista (o \"peso corporal\").\n"
        "- Nombres de ejercicio en español, breves.\n"
        "- CRÍTICO: responde SOLO el objeto JSON, compacto, en una sola respuesta completa. "
        "Comillas dobles, sin comas finales, sin comentarios, sin texto antes ni después. "
        "Asegúrate de CERRAR todas las llaves y corchetes."
    )
    return WORKOUT_SYSTEM_PROMPT + "\n" + rules


def _extract_json(content: str) -> dict | None:
    """Best-effort extraction of a JSON object from an LLM response.

    Free models often wrap JSON in prose or emit minor syntax errors (trailing
    commas, code fences). Strategy:
      1. strip markdown code fences,
      2. slice from the first '{' to the last '}',
      3. try json.loads; if it fails, remove trailing commas and retry.
    Returns the parsed dict, or None if it still cannot be parsed.
    """
    import re

    if not content:
        return None
    text = content.strip()

    # 1) strip code fences
    if text.startswith("```"):
        lines = text.split("\n", 1)
        text = lines[1] if len(lines) > 1 else ""
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    # 2) slice to the outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    # 3a) direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3b) remove trailing commas before } or ] and retry
    repaired = re.sub(r",(\s*[}\]])", r"\1", text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # 3c) repair a TRUNCATED object: drop any dangling partial token, then close
    # all still-open brackets/braces (in the right order) and retry. This rescues
    # plans that got cut off by the token limit.
    try:
        repaired2 = _close_truncated_json(text)
        if repaired2 is not None:
            return json.loads(repaired2)
    except json.JSONDecodeError:
        return None
    return None


def _close_truncated_json(text: str) -> str | None:
    """Attempt to close a truncated JSON object.

    Walks the string tracking string state and the stack of open { and [. Cuts at
    the last position that is a safe boundary (after a complete value), strips a
    trailing comma, and appends the closing brackets in reverse order.
    """
    import re as _re

    # Trim to the last character that could end a value: digit, quote, ], }, e, l
    # (true/false/null). Everything after a dangling key/`:`/partial token is junk.
    # Find a safe cut point by scanning for the last complete token boundary.
    stack: list[str] = []
    in_str = False
    escape = False
    last_safe = -1  # index (inclusive) of last char that safely ends a value/element

    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
                last_safe = i
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
            last_safe = i
        elif ch in "0123456789":
            last_safe = i
        elif ch in "el":  # end of true/false/null
            last_safe = i

    if last_safe < 0:
        return None

    candidate = text[: last_safe + 1]
    # Strip a trailing comma if present.
    candidate = _re.sub(r",\s*$", "", candidate)

    # Recompute the open-stack for the truncated candidate.
    stack = []
    in_str = False
    escape = False
    for ch in candidate:
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()

    closing = "".join("}" if b == "{" else "]" for b in reversed(stack))
    return candidate + closing


async def generate_workout_plan(
    profile: dict,
    goal: dict,
    activity_summary: dict,
    timeout_seconds: float = 60.0,
) -> dict | None:
    """Generate a workout plan via OpenRouter.

    Builds the prompt from profile+goal+activity_summary, calls OpenRouter with a
    60s timeout (reusing the _call_llm pattern), strips markdown code fences and
    json.loads the result.

    Returns the parsed dict, or None on timeout / HTTP error / empty response /
    JSONDecodeError.
    """
    equipment = profile.get("equipment") or []
    days_per_week = profile.get("days_per_week")
    level = profile.get("level")
    goal_type = goal.get("goal_type")
    goal_desc = goal.get("performance_target") or goal_type

    system_prompt = _build_workout_prompt(
        days_per_week=days_per_week,
        equipment_text=", ".join(equipment) if equipment else "peso corporal",
        level=level,
        goal_desc=goal_desc,
        activity_summary_text=json.dumps(activity_summary, ensure_ascii=False),
    )

    user_message = (
        "Genera mi rutina de entrenamiento en JSON según mi perfil "
        f"(nivel {level}, {days_per_week} días/semana, objetivo {goal_desc})."
    )

    url = f"{settings.openrouter_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.2,
        "max_tokens": 2000,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            logger.error(
                "OpenRouter workout error %s: %s",
                response.status_code,
                response.text[:200],
            )
            return None

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            logger.warning("OpenRouter returned empty choices for workout plan")
            return None

        content = choices[0].get("message", {}).get("content", "")
        if not content or not content.strip():
            logger.warning("OpenRouter returned empty content for workout plan")
            return None

        parsed = _extract_json(content)
        if parsed is None:
            logger.warning(
                "OpenRouter workout returned unparseable JSON: %s", content[:300]
            )
            return None
        return parsed

    except httpx.TimeoutException:
        logger.warning("OpenRouter workout timeout (%ss)", timeout_seconds)
        return None
    except Exception as e:
        logger.exception("OpenRouter workout request failed: %s", e)
        return None


# ── Meal plan generation (Meal_Planner, Req 6.1, 9.1-9.3) ────────────────────
# NOTE: this template contains literal JSON braces, so it must NOT be passed
# through str.format(). The per-request variables (inventory, kcal/macros,
# dietary restrictions) are composed by the service layer's build_meal_prompt
# (task 9.1) and passed in as the `prompt` argument; generate_meal_plan sends
# MEAL_SYSTEM_PROMPT as the system message and `prompt` as the user message.
MEAL_SYSTEM_PROMPT = """Eres un chef nutricionista. Genera un plan de comidas semanal en JSON.
Devuelve SOLO JSON con esta estructura, sin texto adicional:
{
  "days": [
    {
      "day": "Lunes",
      "meals": [
        {"type": "desayuno", "items": [{"food_name": "Avena", "grams": 80}]}
      ],
      "totals": {"kcal": 2100, "protein_g": 160, "fat_g": 60, "carbs_g": 220}
    }
  ]
}

Reglas (síguelas al pie de la letra):
- Genera EXACTAMENTE 7 días, en orden: Lunes, Martes, Miércoles, Jueves, Viernes, Sábado, Domingo.
- Cada día debe tener AL MENOS una comida.
- El campo "type" de cada comida debe ser uno de: desayuno, almuerzo, cena, snack.
- Cada comida debe tener al menos un ítem; los gramos ("grams") de cada ítem deben estar entre 1 y 100000.
- Prioriza los alimentos que el usuario tiene en su inventario.
- Aproxima las kcal y macronutrientes diarios a las metas indicadas.
- Respeta las restricciones dietéticas: no incluyas alimentos prohibidos ni alérgenos.
- Calcula los totales diarios ("totals": kcal, protein_g, fat_g, carbs_g) a partir de los ítems del día.
- Los nombres de los alimentos deben estar en español.
- CRÍTICO: responde SOLO el objeto JSON, compacto, en una sola respuesta completa. Comillas dobles, sin comas finales, sin comentarios, sin texto antes ni después. Asegúrate de CERRAR todas las llaves y corchetes.
"""


async def generate_meal_plan(
    prompt: str,
    timeout_seconds: float = 60.0,
) -> dict | None:
    """Generate a weekly meal plan via OpenRouter.

    Sends MEAL_SYSTEM_PROMPT as the system message and `prompt` (composed by the
    service layer's build_meal_prompt with inventory, targets and dietary rules)
    as the user message. Calls OpenRouter with the given timeout, then uses the
    tolerant `_extract_json` helper (handles code fences, trailing commas and
    truncated-JSON repair) to parse the response.

    Returns the parsed dict, or None on timeout / HTTP error / empty response /
    unparseable JSON.
    """
    url = f"{settings.openrouter_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": MEAL_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 3000,
        # Ask for a strict JSON object response when the model/provider supports it.
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            logger.error(
                "OpenRouter meal error %s: %s",
                response.status_code,
                response.text[:200],
            )
            return None

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            # Free models sometimes answer 200 with no choices (queued/rate
            # limited) and put the reason in an 'error' field. Log the body so
            # we can tell an empty answer from an upstream error.
            logger.warning(
                "OpenRouter returned empty choices for meal plan: %s",
                json.dumps(data)[:400],
            )
            return None

        message = choices[0].get("message", {}) or {}
        content = message.get("content", "")
        # Some models put the answer in a 'reasoning' field and leave content
        # empty; fall back to it so a valid plan is not discarded.
        if not content or not content.strip():
            content = message.get("reasoning", "") or ""
        if not content or not content.strip():
            logger.warning(
                "OpenRouter returned empty content for meal plan: %s",
                json.dumps(message)[:400],
            )
            return None

        parsed = _extract_json(content)
        if parsed is None:
            logger.warning(
                "OpenRouter meal returned unparseable JSON: %s", content[:300]
            )
            return None
        return parsed

    except httpx.TimeoutException:
        logger.warning("OpenRouter meal timeout (%ss)", timeout_seconds)
        return None
    except Exception as e:
        logger.exception("OpenRouter meal request failed: %s", e)
        return None
