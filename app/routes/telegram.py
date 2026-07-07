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


def _detect_life_keywords(text: str) -> dict | None:
    """
    Detect life/daily activities that the LLM might refuse to classify.
    Returns a fake LLM activity response or None.
    """
    lower = text.lower().strip()
    
    # Map of keywords → (activity_type, detail)
    patterns = [
        (["hice caca", "fui al baño", "hice del baño", "fui a cagar", "cagué", "hice popo", "fui al wc"], "baño", None),
        (["comí", "almorcé", "desayuné", "cené", "merendé", "comimos"], "comer", None),
        (["tomé agua", "bebí agua", "me hidraté", "vaso de agua"], "agua", None),
        (["dormí", "me dormí", "me acosté"], "dormir", None),
        (["vi una película", "vi una peli", "vi una serie", "vi tele", "vi netflix"], "entretenimiento", None),
        (["cociné", "hice comida", "preparé comida"], "cocinar", None),
        (["limpié", "hice aseo", "ordené", "aspiré", "lavé"], "limpieza", None),
        (["me duché", "me bañé"], "higiene", None),
    ]
    
    for keywords, activity_type, _ in patterns:
        for kw in keywords:
            if kw in lower:
                # Extract any extra detail after the keyword
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
    
    # Match "DD de MES" or "MES DD"
    months = {"enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
              "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
              "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"}
    
    for month_name, month_num in months.items():
        date_match = re.search(rf'(\d{{1,2}})\s+de\s+{month_name}', lower)
        if date_match:
            day = int(date_match.group(1))
            schedule_date = f"2026-{month_num}-{day:02d}"
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
    
    # Quick keyword detection for life activities the LLM might reject
    forced_activity = _detect_life_keywords(text)

    response = await interpret_message(text)
    if not response:
        if forced_reminder:
            response = forced_reminder
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

        activity = Activity(
            user_id=user.id,
            activity_type=activity_data.activity_type,
            exercise_name=activity_data.exercise_name,
            duration_minutes=activity_data.duration_minutes,
            distance_km=activity_data.distance_km,
            calories=calories,
            sets_data=json_mod.dumps(activity_data.sets) if activity_data.sets else None,
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
            r = Reminder(
                user_id=user.id,
                schedule=schedule,
                frequency=reminder_data.frequency,
                message=reminder_data.message or "actividad",
                schedule_days=reminder_data.schedule_days,
                schedule_date=reminder_data.schedule_date,
                active=True,
            )
            db.add(r)
            await db.flush()

            # Build human-readable schedule description
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
            active=True,
        )
        db.add(goal)
        await db.flush()

        period_text = {"daily": "al día", "weekly": "por semana", "monthly": "al mes"}.get(goal_data.period, goal_data.period)
        await _send(chat_id,
            f"🎯 Meta creada!\n\n"
            f"📌 *{goal_data.description or goal_data.activity_type}*\n"
            f"🏆 {goal_data.target_count} veces {period_text}\n\n"
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
