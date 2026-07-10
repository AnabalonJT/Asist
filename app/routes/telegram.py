"""Telegram webhook route — production endpoint for incoming messages.

In production, Telegram sends updates here via HTTPS webhook.
In development, polling mode handles messages (see telegram_bot.py).
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.activity import Activity
from app.models.reminder import Reminder
from app.services.auth_service import AuthError, auth_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Deduplication: track processed update_ids to prevent Telegram retries
_processed_updates: set[int] = set()


async def _send(chat_id: int, text: str, parse_mode: str = "Markdown") -> None:
    """Send a message via Telegram Bot API."""
    import httpx
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
    except Exception as e:
        logger.warning("Failed to send message to %s: %s", chat_id, e)


async def _send_typing(chat_id: int) -> None:
    import httpx
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendChatAction"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json={"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass


@router.post("/webhook")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive Telegram updates via webhook."""
    if settings.telegram_webhook_secret:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_secret != settings.telegram_webhook_secret:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    try:
        update: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    # Deduplicate: Telegram may retry if we're slow to respond
    update_id = update.get("update_id")
    if update_id and update_id in _processed_updates:
        return {"ok": True}
    if update_id:
        _processed_updates.add(update_id)
        # Keep set from growing forever (max 1000 entries)
        if len(_processed_updates) > 1000:
            _processed_updates.clear()

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id: int = message["chat"]["id"]
    text: str = message.get("text", "").strip()
    if not text:
        return {"ok": True}

    if text.startswith("/start"):
        await _handle_start(chat_id, text, db)
        return {"ok": True}

    result = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"ok": True}

    await _send_typing(chat_id)
    try:
        await _handle_message(chat_id, text, user, db)
    except Exception as e:
        logger.exception("Error handling message from chat_id=%s: %s", chat_id, e)
        await _send(chat_id, "❌ Ocurrió un error procesando tu mensaje. Intenta de nuevo.")
    return {"ok": True}


async def _handle_start(chat_id: int, text: str, db: AsyncSession) -> None:
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await _send(chat_id, "👋 ¡Hola! Para vincular tu cuenta, usa el enlace desde la web.")
        return

    token = parts[1].strip()
    try:
        user = await auth_service.validate_linking_token(db, token)
        await db.execute(sql_update(User).where(User.id == user.id).values(telegram_chat_id=chat_id))
        name = user.email.split("@")[0]
        await _send(chat_id,
            f"✅ ¡Cuenta vinculada!\n\nHola {name} 👋\n\n"
            f"Soy tu asistente de seguimiento:\n\n"
            f"🏃 *Deportes*: \"Corrí 5km\"\n"
            f"💪 *Fuerza*: \"4 series press banca 80kg\"\n"
            f"📚 *Hábitos*: \"Leí 30 min\"\n"
            f"⏰ *Recordatorios*: \"Recuérdame correr a las 7:30\"\n\n"
            f"¡Envíame lo que hiciste! 🚀"
        )
    except AuthError:
        await _send(chat_id, "⚠️ Enlace no válido o ya usado. Genera uno nuevo desde la web.")
    except Exception as e:
        logger.exception("Error linking: %s", e)
        await db.rollback()


def _detect_when_keywords(text: str) -> str | None:
    """Detect time references in the message text."""
    lower = text.lower()
    
    if "ayer" in lower and "anteayer" not in lower:
        return "yesterday"
    if "anteayer" in lower:
        return "2_days_ago"
    if "la semana pasada" in lower:
        return "7_days_ago"
    if "hace 2 días" in lower or "hace dos días" in lower:
        return "2_days_ago"
    if "hace 3 días" in lower or "hace tres días" in lower:
        return "3_days_ago"
    
    # Day names: "el lunes", "el martes", etc.
    import re
    day_match = re.search(r'(?:el\s+)?(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)', lower)
    if day_match:
        return f"last_{day_match.group(1)}"
    
    return None  # means "now"


def _resolve_when(when: str | None, user_now) -> 'datetime':
    """Resolve a 'when' string to an actual datetime."""
    from datetime import timedelta
    import re

    if not when or when == "now":
        return user_now

    lower = when.lower().strip()

    if lower == "yesterday":
        return user_now - timedelta(days=1)
    elif lower in ("anteayer", "2_days_ago", "2 days ago"):
        return user_now - timedelta(days=2)
    elif lower in ("3_days_ago", "3 days ago"):
        return user_now - timedelta(days=3)
    elif lower in ("7_days_ago", "last_week", "la semana pasada"):
        return user_now - timedelta(days=7)

    # Try "X_days_ago" pattern
    days_match = re.match(r'(\d+)_?days?_?ago', lower)
    if days_match:
        return user_now - timedelta(days=int(days_match.group(1)))

    # Try day names: "last_monday", "last_tuesday", etc.
    day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
               "friday": 4, "saturday": 5, "sunday": 6,
               "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
               "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6}
    for day_name, day_num in day_map.items():
        if day_name in lower:
            days_back = (user_now.weekday() - day_num) % 7
            if days_back == 0:
                days_back = 7  # "last monday" when today is monday = 7 days ago
            return user_now - timedelta(days=days_back)

    # Try ISO date: "2026-07-05"
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(lower)
        return parsed.replace(hour=user_now.hour, minute=user_now.minute)
    except (ValueError, TypeError):
        pass

    return user_now


def _detect_challenge_keywords(text: str) -> dict | None:
    """
    Detect challenge/multi-goal intent from keywords.
    Triggers when: "durante X días/meses" + multiple activities (comma/y separated).
    """
    import re
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    lower = text.lower().strip()

    # Must contain a duration trigger
    duration_days = None
    duration_match = re.search(r'(\d+)\s*días', lower)
    if duration_match:
        duration_days = int(duration_match.group(1))
    
    months_match = re.search(r'(\d+)\s*mes(?:es)?', lower)
    if months_match:
        duration_days = int(months_match.group(1)) * 30

    # Must contain "durante" or "por" or "quiero" with duration
    triggers = ["durante", "por", "desafío", "desafio", "challenge"]
    has_trigger = any(t in lower for t in triggers)
    
    if not duration_days and not has_trigger:
        return None
    
    # Must have multiple activities (separated by comma or "y")
    # Remove the duration/trigger part to get activities
    activities_text = lower
    activities_text = re.sub(r'durante\s+\d+\s*(días|meses?)', '', activities_text)
    activities_text = re.sub(r'por\s+\d+\s*(días|meses?)', '', activities_text)
    activities_text = re.sub(r'desaf[ií]o:?\s*', '', activities_text)
    activities_text = re.sub(r'quiero\s*', '', activities_text)
    activities_text = activities_text.strip(" .,;:-")

    # Split by comma and "y"
    parts = re.split(r'\s*[,]\s*|\s+y\s+', activities_text)
    parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]

    if len(parts) < 2:
        return None  # Not a multi-goal, let LLM handle as single goal

    # Build goals from parts
    goals = []
    for part in parts:
        # Try to extract frequency
        target_count = 1
        period = "daily"
        
        freq_match = re.search(r'(\d+)\s*(?:veces?\s*(?:por|a la)\s*semana|x\s*semana)', part)
        if freq_match:
            target_count = int(freq_match.group(1))
            period = "weekly"
            part = re.sub(r'\d+\s*(?:veces?\s*(?:por|a la)\s*semana|x\s*semana)', '', part).strip()
        elif "diario" in part or "todos los días" in part or "cada día" in part:
            target_count = 1
            period = "daily"
            part = re.sub(r'(?:diario|todos los días|cada día)', '', part).strip()

        # Clean activity name
        activity = part.strip(" .,;:-")
        if not activity:
            continue

        # Map common names
        activity_map = {
            "deporte": "gym", "gimnasio": "gym", "gym": "gym",
            "correr": "running", "caminar": "walking", "nadar": "swimming",
            "meditar": "meditation", "meditación": "meditation",
            "leer": "reading", "estudiar": "study",
            "cama": "cama", "mi cama": "cama", "hacer mi cama": "cama",
            "yoga": "yoga", "bici": "cycling",
        }
        activity_type = activity_map.get(activity, activity)

        goals.append({
            "activity_type": activity_type,
            "target_count": target_count,
            "period": period,
            "description": activity.capitalize(),
        })

    if len(goals) < 2:
        return None

    # Calculate ends_at
    ends_at = None
    if duration_days:
        now = datetime.now(ZoneInfo("America/Santiago"))
        end_date = now + timedelta(days=duration_days)
        ends_at = end_date.strftime("%Y-%m-%d")

    name = f"Desafío {duration_days} días" if duration_days else "Mi desafío"

    return {
        "intent": "challenge",
        "data": {
            "name": name,
            "ends_at": ends_at,
            "goals": goals,
        }
    }


def _detect_life_keywords(text: str) -> dict | None:
    """
    Detect life/daily activities that the LLM might refuse to classify.
    Also detects common sports activities as fallback when LLM fails.
    Returns a fake LLM activity response or None.
    """
    import re
    lower = text.lower().strip()
    
    # Sport patterns (fallback for when LLM fails)
    sport_patterns = [
        (r'corr[íi]|corriendo|troté', "running"),
        (r'camin[ée]|caminando', "walking"),
        (r'nad[ée]|nadando|natación', "swimming"),
        (r'bici|ciclismo|pedale[ée]', "cycling"),
        (r'gym|gimnasio', "gym"),
        (r'yoga', "yoga"),
        (r'medit[ée]|meditando|meditación', "meditation"),
        (r'le[íi]|leyendo|lectura', "reading"),
        (r'estudi[ée]|estudiando', "study"),
    ]
    
    for pattern, activity_type in sport_patterns:
        if re.search(pattern, lower):
            # Extract distance
            dist_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:km|kilómetros)', lower)
            distance = float(dist_match.group(1).replace(',', '.')) if dist_match else None
            
            # Extract duration
            dur_match = re.search(r'(\d+)\s*(?:min|minutos|hrs?|horas?)', lower)
            duration = None
            if dur_match:
                val = int(dur_match.group(1))
                if 'hr' in lower or 'hora' in lower:
                    duration = val * 60
                else:
                    duration = val
            
            category = "sport" if activity_type in ("running", "walking", "swimming", "cycling", "gym") else "habit"
            
            return {
                "intent": "activity",
                "data": {
                    "activity_type": activity_type,
                    "category": category,
                    "duration_minutes": duration,
                    "distance_km": distance,
                    "detail": None,
                    "exercise_name": None,
                    "sets": None,
                    "confidence": 0.85,
                }
            }
    
    # Life activity patterns
    life_patterns = [
        (["hice caca", "fui al baño", "hice del baño", "fui a cagar", "cagué", "hice popo", "fui al wc"], "baño"),
        (["comí", "almorcé", "desayuné", "cené", "merendé", "comimos"], "comer"),
        (["tomé agua", "bebí agua", "me hidraté", "vaso de agua"], "agua"),
        (["dormí", "me dormí", "me acosté"], "dormir"),
        (["vi una película", "vi una peli", "vi una serie", "vi tele", "vi netflix"], "entretenimiento"),
        (["cociné", "hice comida", "preparé comida"], "cocinar"),
        (["limpié", "hice aseo", "ordené", "aspiré", "lavé"], "limpieza"),
        (["me duché", "me bañé"], "higiene"),
    ]
    
    for keywords, activity_type in life_patterns:
        for kw in keywords:
            if kw in lower:
                detail = lower.replace(kw, "").strip(" .,;:-")
                return {
                    "intent": "activity",
                    "data": {
                        "activity_type": activity_type,
                        "category": "life",
                        "duration_minutes": None,
                        "distance_km": None,
                        "detail": detail if detail else None,
                        "exercise_name": None,
                        "sets": None,
                        "confidence": 0.9,
                    }
                }
    
    return None


def _detect_reminder_keywords(text: str) -> dict | None:
    """
    Detect reminder intent from keywords when LLM fails.
    Returns a fake LLM response dict or None.
    """
    import re
    lower = text.lower()

    # Must contain a reminder trigger word
    triggers = ["recuérdame", "recuerdame", "recordatorio", "acuérdame", "no olvides", "no te olvides"]
    if not any(t in lower for t in triggers):
        return None

    # Try to extract time (HH:MM pattern)
    time_match = re.search(r'(\d{1,2})[:\.](\d{2})', text)
    schedule = None
    if time_match:
        h, m = int(time_match.group(1)), int(time_match.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            schedule = f"{h:02d}:{m:02d}"

    # Try AM/PM
    if not schedule:
        am_pm = re.search(r'(\d{1,2})\s*(am|pm)', lower)
        if am_pm:
            h = int(am_pm.group(1))
            if am_pm.group(2) == "pm" and h < 12:
                h += 12
            schedule = f"{h:02d}:00"

    if not schedule:
        schedule = "09:00"  # Default

    # Try to extract date
    schedule_date = None
    frequency = "daily"
    
    # Resolve relative dates: "hoy", "mañana", "este miércoles", etc.
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/Santiago"))
    today = now.date()
    
    DAY_MAP = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
    }

    if "hoy" in lower:
        schedule_date = today.isoformat()
        frequency = "once"
    elif "mañana" in lower or "manana" in lower:
        schedule_date = (today + timedelta(days=1)).isoformat()
        frequency = "once"
    elif "pasado mañana" in lower or "pasado manana" in lower:
        schedule_date = (today + timedelta(days=2)).isoformat()
        frequency = "once"
    else:
        # Check "este [día]" or just day name
        for day_name, day_num in DAY_MAP.items():
            if day_name in lower:
                # Calculate next occurrence of this day (or today if it's today)
                days_ahead = day_num - today.weekday()
                if days_ahead < 0:
                    days_ahead += 7
                # If days_ahead == 0, it means today (e.g., "este miércoles" on a Wednesday)
                target_date = today + timedelta(days=days_ahead)
                schedule_date = target_date.isoformat()
                frequency = "once"
                break

    # Match "DD de MES" for explicit dates
    if not schedule_date:
        months = {"enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
                  "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
                  "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"}
        
        for month_name, month_num in months.items():
            date_match = re.search(rf'(\d{{1,2}})\s+de\s+{month_name}', lower)
            if date_match:
                day = int(date_match.group(1))
                schedule_date = f"{now.year}-{month_num}-{day:02d}"
                frequency = "once"
                break

    # Extract message (remove trigger word, time, and date parts)
    message = lower
    for t in triggers:
        message = message.replace(t, "")
    # Remove time patterns
    message = re.sub(r'\d{1,2}[:.]\d{2}', '', message)
    message = re.sub(r'\d{1,2}\s*(am|pm)', '', message)
    # Remove date patterns
    message = re.sub(r'(el\s+)?(lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)', '', message)
    message = re.sub(r'\d{1,2}\s+de\s+\w+', '', message)
    message = re.sub(r'(hoy|mañana|manana|pasado mañana|este|esta)', '', message)
    # Remove filler words
    message = re.sub(r'\b(que|de|a las|tengo que|hay que|debo)\b', '', message)
    message = message.strip(" .,;:-")
    
    if not message or len(message) < 2:
        message = "recordatorio"

    return {
        "intent": "reminder",
        "data": {
            "action": "create",
            "message": message,
            "schedule": schedule,
            "frequency": frequency,
            "schedule_days": None,
            "schedule_date": schedule_date,
        }
    }


async def _handle_message(chat_id: int, text: str, user: User, db: AsyncSession) -> None:
    from app.services.llm_service import interpret_message, parse_activity, parse_reminder, parse_goal
    from app.services.calorie_service import calorie_service
    from app.models.goal import Goal

    # Quick keyword detection for reminders (LLM sometimes misclassifies these)
    forced_reminder = _detect_reminder_keywords(text)
    
    # Quick keyword detection for challenges/multi-goal
    forced_challenge = _detect_challenge_keywords(text)
    
    # Quick keyword detection for life activities the LLM might reject
    forced_activity = _detect_life_keywords(text)

    response = await interpret_message(text)
    if not response:
        if forced_reminder:
            response = forced_reminder
        elif forced_challenge:
            response = forced_challenge
        elif forced_activity:
            response = forced_activity
        else:
            await _send_help(chat_id, user)
            return

    intent = response.get("intent", "chat")

    # Override LLM classification if we detected reminder keywords
    if intent != "reminder" and forced_reminder:
        intent = "reminder"
        response = forced_reminder
    # Override for challenges
    elif intent != "challenge" and forced_challenge:
        intent = "challenge"
        response = forced_challenge
    # Override if LLM rejected a life activity we detected
    elif intent == "chat" and forced_activity:
        intent = "activity"
        response = forced_activity

    if intent == "activity":
        activity_data = parse_activity(response)
        if not activity_data:
            await _send_help(chat_id, user)
            return

        calories = 0
        if activity_data.category in ("sport", "strength"):
            calories = calorie_service.estimate(
                activity_type=activity_data.activity_type,
                duration_minutes=activity_data.duration_minutes,
                distance_km=activity_data.distance_km,
            )

        import json as json_mod
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        # Use user's timezone for the timestamp
        try:
            user_tz = ZoneInfo(user.timezone or "America/Santiago")
        except Exception:
            user_tz = ZoneInfo("America/Santiago")
        
        # Resolve when from the original text (keyword detection)
        user_now = datetime.now(user_tz).replace(tzinfo=None)
        when_detected = _detect_when_keywords(text)
        activity_time = _resolve_when(when_detected, user_now)

        activity = Activity(
            user_id=user.id,
            activity_type=activity_data.activity_type,
            exercise_name=activity_data.exercise_name,
            duration_minutes=activity_data.duration_minutes,
            distance_km=activity_data.distance_km,
            calories=calories,
            sets_data=json_mod.dumps(activity_data.sets) if activity_data.sets else None,
            timestamp=activity_time,
        )
        db.add(activity)
        await db.flush()

        icon = {"running": "🏃", "walking": "🚶", "cycling": "🚴", "gym": "🏋️",
                "swimming": "🏊", "yoga": "🧘", "weights": "💪", "strength": "💪",
                "crossfit": "💪", "meditation": "🧘", "reading": "📚", "study": "📖"
        }.get(activity_data.activity_type.lower(), "⚡")

        if activity_data.category == "sport":
            name = activity_data.activity_type.capitalize()
            parts = []
            if activity_data.duration_minutes: parts.append(f"{activity_data.duration_minutes} min")
            if activity_data.distance_km: parts.append(f"{activity_data.distance_km} km")
            msg = f"✅ {icon} *{name}*"
            if parts: msg += f" ({' · '.join(parts)})"
            msg += f"\n🔥 {calories} cal"

        elif activity_data.category == "strength":
            name = activity_data.exercise_name or activity_data.activity_type.capitalize()
            msg = f"✅ 💪 *{name}*"
            if activity_data.sets:
                sets_str = ", ".join(f"{s['reps']}×{s['weight_kg']}kg" for s in activity_data.sets)
                msg += f"\n📋 {len(activity_data.sets)} series: {sets_str}"
                total_vol = sum(s.get("reps", 0) * s.get("weight_kg", 0) for s in activity_data.sets)
                if total_vol > 0:
                    msg += f"\n📊 Volumen: {total_vol:,} kg"
            elif activity_data.detail:
                msg += f"\n📋 {activity_data.detail}"

        elif activity_data.category == "life":
            name = activity_data.activity_type.capitalize()
            life_icons = {"comer": "🍽", "baño": "🚽", "agua": "💧", "dormir": "😴",
                         "película": "🎬", "cocinar": "👨‍🍳", "limpiar": "🧹", "compras": "🛒"}
            icon = life_icons.get(activity_data.activity_type.lower(), "📝")
            msg = f"✅ {icon} *{name}*"
            if activity_data.detail:
                msg += f" — {activity_data.detail}"
            if activity_data.duration_minutes:
                msg += f" ({activity_data.duration_minutes} min)"
            msg += "\n📋 Registrado"

        else:
            name = activity_data.activity_type.capitalize()
            msg = f"✅ {icon} *{name}*"
            if activity_data.duration_minutes: msg += f" ({activity_data.duration_minutes} min)"
            msg += "\n📊 ¡Sumado a tu racha!"

        # Show when it was registered if not "now"
        if when_detected and when_detected != "now":
            msg += f"\n🕐 Registrado: {activity_time.strftime('%d/%m %H:%M')}"

        # Check goal progress
        goal_msg = await _check_goal_progress(user.id, activity_data.activity_type, db)
        if goal_msg:
            msg += f"\n\n{goal_msg}"

        await _send(chat_id, msg)

    elif intent == "reminder":
        reminder_data = parse_reminder(response)
        if not reminder_data:
            await _send(chat_id, "No entendí. Intenta: \"recuérdame meditar a las 8:00\"")
            return

        if reminder_data.action == "create":
            schedule = reminder_data.schedule or "09:00"
            msg_text = reminder_data.message or "actividad"

            # Prevent duplicates: check if same reminder already exists
            existing = await db.execute(
                select(Reminder).where(
                    Reminder.user_id == user.id,
                    Reminder.message == msg_text,
                    Reminder.schedule == schedule,
                    Reminder.active == True,
                )
            )
            if existing.scalar_one_or_none():
                await _send(chat_id, f"⏰ Ya tienes ese recordatorio: *{msg_text}* a las {schedule}")
                return

            r = Reminder(
                user_id=user.id,
                schedule=schedule,
                frequency=reminder_data.frequency,
                message=msg_text,
                schedule_days=reminder_data.schedule_days,
                schedule_date=reminder_data.schedule_date,
                active=True,
            )
            db.add(r)
            await db.flush()

            freq_text = _format_frequency(r)
            await _send(chat_id, f"⏰ Recordatorio creado!\n📌 *{r.message}*\n🕐 {schedule} — {freq_text}")

        elif reminder_data.action == "list":
            res = await db.execute(select(Reminder).where(Reminder.user_id == user.id, Reminder.active == True))
            reminders = res.scalars().all()
            if not reminders:
                await _send(chat_id, "No tienes recordatorios activos.")
            else:
                lines = ["⏰ *Tus recordatorios:*\n"]
                for r in reminders:
                    lines.append(f"• {r.message} — {r.schedule} ({_format_frequency(r)})")
                await _send(chat_id, "\n".join(lines))
        elif reminder_data.action in ("delete", "pause"):
            res = await db.execute(select(Reminder).where(Reminder.user_id == user.id, Reminder.active == True))
            reminders = res.scalars().all()
            target = next((r for r in reminders if reminder_data.message and reminder_data.message.lower() in r.message.lower()), None)
            if not target and reminders:
                target = reminders[0]
            if target:
                target.active = False
                await _send(chat_id, f"✅ Recordatorio *{target.message}* desactivado.")
            else:
                await _send(chat_id, "No encontré ese recordatorio.")

    elif intent == "timezone":
        tz = response.get("data", {}).get("timezone", "")
        if tz:
            import zoneinfo
            try:
                zoneinfo.ZoneInfo(tz)
                await db.execute(sql_update(User).where(User.id == user.id).values(timezone=tz))
                await _send(chat_id, f"✅ Zona horaria: *{tz}*")
            except Exception:
                await _send(chat_id, "❌ Zona horaria no válida.")
        else:
            await _send(chat_id, f"🌐 Tu zona: *{user.timezone}*")

    elif intent == "goal":
        await _handle_goal(chat_id, user, response, db)

    elif intent == "challenge":
        await _handle_challenge(chat_id, user, response, db)

    else:
        await _send_help(chat_id, user)


def _format_frequency(r) -> str:
    """Format reminder frequency in human-readable Spanish."""
    DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    if r.frequency == "daily":
        return "todos los días"
    elif r.frequency == "weekdays":
        return "Lun a Vie"
    elif r.frequency == "weekends":
        return "Sáb y Dom"
    elif r.frequency == "specific_days" and r.schedule_days:
        days = [int(d.strip()) for d in r.schedule_days.split(",") if d.strip().isdigit()]
        return " y ".join(DAY_NAMES[d] for d in days if d < 7)
    elif r.frequency == "once" and r.schedule_date:
        return f"solo {r.schedule_date}"
    elif r.frequency == "biweekly":
        return "cada 2 semanas"
    elif r.frequency == "weekly":
        return "semanal"
    return r.frequency


async def _check_goal_progress(user_id: int, activity_type: str, db: AsyncSession) -> str | None:
    """Check if user has a goal for this activity type and return progress message."""
    from app.models.goal import Goal

    result = await db.execute(
        select(Goal).where(
            Goal.user_id == user_id,
            Goal.activity_type == activity_type,
            Goal.active == True,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        return None

    progress = await _get_goal_progress(goal, db)
    period_text = {"daily": "hoy", "weekly": "esta semana", "monthly": "este mes"}.get(goal.period, goal.period)

    if progress >= goal.target_count:
        return f"🏆 *¡Meta cumplida!* {goal.description} ({progress}/{goal.target_count} {period_text})"
    else:
        bar = _progress_bar(progress, goal.target_count)
        return f"🎯 Meta: {bar} {progress}/{goal.target_count} {period_text}"


async def _handle_challenge(chat_id: int, user: User, response: dict, db: AsyncSession) -> None:
    """Create a challenge with multiple goals."""
    from app.models.challenge import Challenge
    from app.models.goal import Goal

    data = response.get("data", {})
    name = data.get("name", "Mi desafío")
    ends_at = data.get("ends_at")
    goals_data = data.get("goals", [])

    if not goals_data:
        await _send(chat_id, "No entendí las actividades del desafío. Intenta: \"75 días de deporte, meditar y leer\"")
        return

    # Create challenge
    challenge = Challenge(
        user_id=user.id,
        name=name,
        ends_at=ends_at,
        active=True,
    )
    db.add(challenge)
    await db.flush()

    # Create goals linked to this challenge
    goal_lines = []
    for g in goals_data:
        goal = Goal(
            user_id=user.id,
            challenge_id=challenge.id,
            activity_type=g.get("activity_type", "actividad"),
            description=g.get("description", g.get("activity_type", "")),
            target_count=g.get("target_count", 1),
            period=g.get("period", "daily"),
            ends_at=ends_at,
            active=True,
        )
        db.add(goal)
        freq = {"daily": "diario", "weekly": "semanal", "monthly": "mensual"}.get(goal.period, goal.period)
        goal_lines.append(f"  • {goal.description} ({goal.target_count}x {freq})")

    await db.flush()

    ends_text = f"\n📅 Hasta: {ends_at}" if ends_at else "\n♾️ Sin fecha límite"
    goals_list = "\n".join(goal_lines)

    await _send(chat_id,
        f"🏆 *Desafío creado: {name}*{ends_text}\n\n"
        f"📋 Metas incluidas:\n{goals_list}\n\n"
        f"_Registra tus actividades y verás el progreso de cada meta_"
    )


async def _handle_goal(chat_id: int, user: User, response: dict, db: AsyncSession) -> None:
    """Handle goal create/list/delete."""
    from app.services.llm_service import parse_goal
    from app.models.goal import Goal

    goal_data = parse_goal(response)
    if not goal_data:
        await _send(chat_id, "No entendí tu meta. Intenta: \"quiero correr 3 veces por semana\"")
        return

    if goal_data.action == "create":
        if not goal_data.activity_type:
            await _send(chat_id, "¿Qué actividad quieres como meta? Ej: \"meta: meditar todos los días\"")
            return

        goal = Goal(
            user_id=user.id,
            activity_type=goal_data.activity_type,
            description=goal_data.description or f"{goal_data.activity_type} {goal_data.target_count}x/{goal_data.period}",
            target_count=goal_data.target_count,
            period=goal_data.period,
            ends_at=goal_data.ends_at,
            active=True,
        )
        db.add(goal)
        await db.flush()

        period_text = {"daily": "al día", "weekly": "por semana", "monthly": "al mes"}.get(goal_data.period, goal_data.period)
        duration_text = ""
        if goal_data.ends_at:
            duration_text = f"\n📅 Hasta: {goal_data.ends_at}"
        else:
            duration_text = "\n♾️ Sin fecha límite"

        await _send(chat_id,
            f"🎯 Meta creada!\n\n"
            f"📌 *{goal_data.description or goal_data.activity_type}*\n"
            f"🏆 {goal_data.target_count} veces {period_text}{duration_text}\n\n"
            f"_Te mostraré tu progreso cada vez que registres esta actividad_"
        )

    elif goal_data.action == "list":
        result = await db.execute(
            select(Goal).where(Goal.user_id == user.id, Goal.active == True)
        )
        goals = result.scalars().all()

        if not goals:
            await _send(chat_id, "No tienes metas activas. Crea una con: \"quiero correr 3 veces por semana\"")
            return

        lines = ["🎯 *Tus metas:*\n"]
        for g in goals:
            # Calculate progress
            progress = await _get_goal_progress(g, db)
            bar = _progress_bar(progress, g.target_count)
            period_text = {"daily": "hoy", "weekly": "esta semana", "monthly": "este mes"}.get(g.period, g.period)
            status = "✅" if progress >= g.target_count else "🔄"
            lines.append(f"{status} {g.description}\n   {bar} {progress}/{g.target_count} {period_text}")

        await _send(chat_id, "\n".join(lines))

    elif goal_data.action == "delete":
        result = await db.execute(
            select(Goal).where(Goal.user_id == user.id, Goal.active == True)
        )
        goals = result.scalars().all()
        target = None
        if goal_data.activity_type:
            for g in goals:
                if goal_data.activity_type.lower() in g.activity_type.lower():
                    target = g
                    break
        if target:
            target.active = False
            await _send(chat_id, f"✅ Meta *{target.description}* eliminada.")
        else:
            await _send(chat_id, "No encontré esa meta.")


async def _get_goal_progress(goal, db: AsyncSession) -> int:
    """Count activities matching this goal in the current period."""
    from datetime import datetime, timedelta
    from sqlalchemy import func as sa_func

    now = datetime.utcnow()

    if goal.period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif goal.period == "weekly":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # monthly
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(sa_func.count())
        .select_from(Activity)
        .where(
            Activity.user_id == goal.user_id,
            Activity.activity_type == goal.activity_type,
            Activity.timestamp >= start,
        )
    )
    return result.scalar() or 0


def _progress_bar(current: int, target: int) -> str:
    """Generate a text progress bar."""
    filled = min(current, target)
    return "▓" * filled + "░" * (target - filled)


async def _send_help(chat_id: int, user: User) -> None:
    name = user.email.split("@")[0]
    await _send(chat_id,
        f"Lo siento {name}, no entiendo 🤔\n\n"
        "Puedo:\n"
        "🏃 *Deportes*: \"Corrí 5km\"\n"
        "💪 *Fuerza*: \"Press banca 4x80kg\"\n"
        "📚 *Hábitos*: \"Leí 30 min\"\n"
        "🎯 *Metas*: \"Quiero correr 3 veces por semana\"\n"
        "⏰ *Recordatorios*: \"Recuérdame meditar a las 8:00\"\n"
        "📋 *Ver metas*: \"Mis metas\"\n\n"
        "_Dime qué hiciste y lo registro_ ✍️"
    )
