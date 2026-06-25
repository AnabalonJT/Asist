"""Telegram bot service: handles polling mode for local development."""
import logging
import asyncio
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from sqlalchemy import select, update as sql_update

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.auth_service import AuthError, auth_service

logger = logging.getLogger(__name__)

_app: Application | None = None


def get_bot_username() -> str:
    """Get the real bot username (set after polling starts)."""
    if _app and _app.bot_data.get("username"):
        return _app.bot_data["username"]
    return settings.telegram_bot_username


async def _start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start <token> command to link Telegram account."""
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    
    # python-telegram-bot puts deep link params in context.args
    args = context.args or []
    logger.info("/start received from chat_id=%s, args=%s", chat_id, args)

    if not args:
        await update.message.reply_text(
            "👋 ¡Hola! Para vincular tu cuenta, usa el enlace desde la web."
        )
        return

    token = args[0].strip()
    logger.info("Attempting to validate linking token: %s...", token[:8])

    async with AsyncSessionLocal() as db:
        try:
            user = await auth_service.validate_linking_token(db, token)
            # Link telegram chat_id to user
            await db.execute(
                sql_update(User)
                .where(User.id == user.id)
                .values(telegram_chat_id=chat_id)
            )
            await db.commit()
            
            name = user.email.split("@")[0]
            await update.message.reply_text(
                f"✅ ¡Cuenta vinculada!\n\n"
                f"Hola {name} 👋\n\n"
                f"Soy tu asistente de seguimiento. Esto es lo que puedo hacer:\n\n"
                f"🏃 *Deportes*: \"Corrí 5km\", \"Nadé 30 min\", \"Anduve en bici 1 hora\"\n"
                f"💪 *Fuerza*: \"4 series de press banca 80kg\", \"Hice sentadillas 20 min\"\n"
                f"📚 *Hábitos*: \"Leí 30 min\", \"Medité 10 min\", \"Estudié 2 horas\"\n"
                f"⏰ *Recordatorios*: \"Recuérdame correr a las 7:30\"\n"
                f"📋 *Ver recordatorios*: \"Mis recordatorios\"\n"
                f"🌐 *Zona horaria*: \"Mi zona es America/Santiago\"\n\n"
                f"¡Envíame lo que hiciste y lo registro! 🚀",
                parse_mode="Markdown"
            )
            logger.info("Linked telegram_chat_id=%s to user_id=%s", chat_id, user.id)
        except AuthError as e:
            logger.warning("Linking token validation failed for chat_id=%s: %s", chat_id, e)
            await update.message.reply_text("⚠️ El enlace no es válido o ya fue usado. Genera uno nuevo desde la web.")
        except Exception as e:
            logger.exception("Error linking account for chat_id=%s: %s", chat_id, e)
            await db.rollback()
            await update.message.reply_text("❌ Ocurrió un error al vincular. Intenta de nuevo.")


async def _message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle regular messages from linked users — interpret activities, reminders, or chat."""
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not text:
        return

    # Check if user is linked
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
        user = result.scalar_one_or_none()

    if not user:
        return  # Unlinked user — ignore per spec

    # Send "typing" indicator
    await update.effective_chat.send_action("typing")

    # Interpret message with LLM
    from app.services.llm_service import interpret_message, parse_activity, parse_reminder
    from app.services.calorie_service import calorie_service
    from app.models.activity import Activity
    from app.models.reminder import Reminder

    response = await interpret_message(text)

    if not response:
        await _send_chat_response(update, user)
        return

    intent = response.get("intent", "chat")

    if intent == "activity":
        await _handle_activity(update, user, response, calorie_service, Activity)
    elif intent == "reminder":
        await _handle_reminder(update, user, response, Reminder)
    elif intent == "timezone":
        await _handle_timezone(update, user, response)
    else:
        await _send_chat_response(update, user)


async def _handle_activity(update, user, response, calorie_service, Activity):
    """Process and log an activity."""
    from app.services.llm_service import parse_activity

    activity_data = parse_activity(response)
    if not activity_data:
        await _send_chat_response(update, user)
        return

    # Calculate calories only for sport/strength categories
    calories = 0
    if activity_data.category in ("sport", "strength"):
        calories = calorie_service.estimate(
            activity_type=activity_data.activity_type,
            duration_minutes=activity_data.duration_minutes,
            distance_km=activity_data.distance_km,
        )

    # Save activity to database
    async with AsyncSessionLocal() as db:
        activity = Activity(
            user_id=user.id,
            activity_type=activity_data.activity_type,
            duration_minutes=activity_data.duration_minutes,
            distance_km=activity_data.distance_km,
            calories=calories,
        )
        db.add(activity)
        await db.commit()
        logger.info(
            "Activity logged: user_id=%s type=%s cat=%s dur=%s dist=%s cal=%s",
            user.id, activity_data.activity_type, activity_data.category,
            activity_data.duration_minutes, activity_data.distance_km, calories
        )

    # Build confirmation message based on category
    icon = {
        "running": "🏃", "walking": "🚶", "cycling": "🚴",
        "gym": "🏋️", "swimming": "🏊", "yoga": "🧘",
        "hiking": "🥾", "basketball": "🏀", "football": "⚽",
        "tennis": "🎾", "dance": "💃", "weights": "🏋️",
        "strength": "💪", "crossfit": "💪", "stretching": "🤸",
        "meditation": "🧘", "reading": "📚", "study": "📖",
        "cardio": "❤️",
    }.get(activity_data.activity_type.lower(), "⚡")

    name = activity_data.activity_type.capitalize()

    if activity_data.category == "sport":
        details = []
        if activity_data.duration_minutes:
            details.append(f"{activity_data.duration_minutes} min")
        if activity_data.distance_km:
            details.append(f"{activity_data.distance_km} km")
        details_str = " · ".join(details) if details else ""
        msg = f"✅ {icon} Registrado: *{name}*"
        if details_str:
            msg += f" ({details_str})"
        msg += f"\n🔥 {calories} cal estimadas"

    elif activity_data.category == "strength":
        msg = f"✅ {icon} Registrado: *{name}*"
        if activity_data.detail:
            msg += f"\n📋 {activity_data.detail}"
        if activity_data.duration_minutes:
            msg += f"\n⏱ {activity_data.duration_minutes} min"
        if calories > 0:
            msg += f"\n🔥 ~{calories} cal"

    else:  # habit
        msg = f"✅ {icon} Registrado: *{name}*"
        if activity_data.duration_minutes:
            msg += f" ({activity_data.duration_minutes} min)"
        if activity_data.detail:
            msg += f"\n📝 {activity_data.detail}"
        msg += "\n📊 ¡Sumado a tu racha!"

    await update.message.reply_text(msg, parse_mode="Markdown")


async def _handle_reminder(update, user, response, Reminder):
    """Process reminder create/list/delete/pause."""
    from app.services.llm_service import parse_reminder

    reminder_data = parse_reminder(response)
    if not reminder_data:
        await update.message.reply_text("No entendí qué recordatorio quieres. Intenta: \"recuérdame meditar a las 8:00\"")
        return

    if reminder_data.action == "create":
        if not reminder_data.message:
            await update.message.reply_text("¿Qué quieres que te recuerde? Ej: \"recuérdame correr a las 7:30\"")
            return

        schedule = reminder_data.schedule or "09:00"
        async with AsyncSessionLocal() as db:
            reminder = Reminder(
                user_id=user.id,
                schedule=schedule,
                frequency=reminder_data.frequency,
                message=reminder_data.message,
                active=True,
            )
            db.add(reminder)
            await db.commit()
            logger.info("Reminder created: user_id=%s msg=%s at=%s", user.id, reminder_data.message, schedule)

        freq_text = {"daily": "todos los días", "weekly": "semanalmente", "weekdays": "lunes a viernes"}.get(
            reminder_data.frequency, reminder_data.frequency
        )
        await update.message.reply_text(
            f"⏰ Recordatorio creado!\n\n"
            f"📌 *{reminder_data.message}*\n"
            f"🕐 {schedule} ({freq_text})",
            parse_mode="Markdown"
        )

    elif reminder_data.action == "list":
        from sqlalchemy import select as sa_select
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_select(Reminder)
                .where(Reminder.user_id == user.id, Reminder.active == True)
            )
            reminders = result.scalars().all()

        if not reminders:
            await update.message.reply_text("No tienes recordatorios activos. Crea uno con: \"recuérdame [hábito] a las [hora]\"")
            return

        lines = ["⏰ *Tus recordatorios:*\n"]
        for r in reminders:
            freq = {"daily": "diario", "weekly": "semanal", "weekdays": "L-V"}.get(r.frequency, r.frequency)
            lines.append(f"• {r.message} — {r.schedule} ({freq})")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif reminder_data.action in ("delete", "pause"):
        from sqlalchemy import select as sa_select
        async with AsyncSessionLocal() as db:
            # Find matching reminder by message content
            result = await db.execute(
                sa_select(Reminder)
                .where(Reminder.user_id == user.id, Reminder.active == True)
            )
            reminders = result.scalars().all()

            target = None
            if reminder_data.message:
                for r in reminders:
                    if reminder_data.message.lower() in r.message.lower():
                        target = r
                        break

            if not target and reminders:
                target = reminders[0]  # Default to first if no match

            if target:
                target.active = False
                await db.commit()
                action_text = "eliminado" if reminder_data.action == "delete" else "pausado"
                await update.message.reply_text(f"✅ Recordatorio *{target.message}* {action_text}.", parse_mode="Markdown")
            else:
                await update.message.reply_text("No encontré un recordatorio que coincida.")
    else:
        await update.message.reply_text("No entendí qué quieres hacer con los recordatorios.")


async def _handle_timezone(update, user, response):
    """Update user's timezone."""
    data = response.get("data", {})
    tz = data.get("timezone", "").strip()

    if not tz:
        await update.message.reply_text(
            "🌐 Tu zona horaria actual: *" + user.timezone + "*\n\n"
            "Para cambiarla, dime algo como:\n"
            "\"Mi zona es America/Santiago\"",
            parse_mode="Markdown"
        )
        return

    # Basic validation
    import zoneinfo
    try:
        zoneinfo.ZoneInfo(tz)
    except (KeyError, Exception):
        await update.message.reply_text(
            f"❌ \"{tz}\" no es una zona horaria válida.\n\n"
            "Ejemplos válidos:\n"
            "• America/Santiago\n• America/Mexico_City\n• America/Bogota\n"
            "• Europe/Madrid\n• US/Eastern"
        )
        return

    # Update in DB
    async with AsyncSessionLocal() as db:
        await db.execute(
            sql_update(User).where(User.id == user.id).values(timezone=tz)
        )
        await db.commit()

    await update.message.reply_text(
        f"✅ Zona horaria actualizada a *{tz}*\n"
        "Tus registros y recordatorios usarán esta zona.",
        parse_mode="Markdown"
    )


async def _send_chat_response(update, user):
    """Send a friendly chat response when intent is not recognized."""
    name = user.email.split("@")[0]
    await update.message.reply_text(
        f"Lo siento {name}, no entiendo qué quieres o no puedo ayudarte con eso 🤔\n\n"
        "Esto es lo que puedo hacer por ti:\n\n"
        "🏃 *Registrar deporte*: \"Corrí 5km\", \"Nadé 30 min\"\n"
        "💪 *Registrar fuerza*: \"4 series press banca 80kg\"\n"
        "📚 *Registrar hábito*: \"Leí 30 min\", \"Medité 10 min\"\n"
        "⏰ *Crear recordatorio*: \"Recuérdame meditar a las 8:00\"\n"
        "📋 *Ver recordatorios*: \"Mis recordatorios\"\n"
        "🌐 *Cambiar zona horaria*: \"Mi zona es America/Santiago\"\n\n"
        "_Simplemente dime qué actividad hiciste y la registro_ ✍️",
        parse_mode="Markdown"
    )


async def start_polling() -> None:
    """Start the Telegram bot in polling mode (for local development)."""
    global _app

    token = settings.bot_token
    if not token or token in ("test_token", ""):
        logger.warning("No valid Telegram bot token configured. Bot polling disabled.")
        return

    logger.info("Starting Telegram bot in POLLING mode...")
    _app = Application.builder().token(token).build()

    _app.add_handler(CommandHandler("start", _start_command))
    _app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _message_handler))

    await _app.initialize()
    
    # Get real bot username from Telegram API
    bot_info = await _app.bot.get_me()
    logger.info("Bot connected: @%s (id=%s)", bot_info.username, bot_info.id)
    # Store for later use
    _app.bot_data["username"] = bot_info.username
    
    await _app.start()
    await _app.updater.start_polling(drop_pending_updates=False)
    logger.info("Telegram bot polling started successfully")


async def stop_polling() -> None:
    """Stop the Telegram bot polling."""
    global _app
    if _app:
        logger.info("Stopping Telegram bot polling...")
        await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()
        _app = None
        logger.info("Telegram bot stopped")
