"""APScheduler setup for reminder delivery and weekly summaries."""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.reminder import Reminder
from app.models.user import User
from app.models.activity import Activity

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def deliver_reminders():
    """Check and deliver due reminders every minute."""
    now = datetime.utcnow()
    current_time = now.strftime("%H:%M")

    async with AsyncSessionLocal() as db:
        # Get active reminders scheduled for current time
        result = await db.execute(
            select(Reminder).where(
                Reminder.active == True,
                Reminder.schedule == current_time,
            )
        )
        reminders = result.scalars().all()

        if not reminders:
            return

        for reminder in reminders:
            # Skip if already sent in last 23 hours (prevent duplicates)
            if reminder.last_sent_at:
                hours_since = (now - reminder.last_sent_at).total_seconds() / 3600
                if hours_since < 23:
                    continue

            # Check frequency
            if reminder.frequency == "weekdays" and now.weekday() >= 5:
                continue
            if reminder.frequency == "weekly" and now.weekday() != 0:  # Monday
                continue

            # Get user's telegram chat_id
            user_result = await db.execute(
                select(User).where(User.id == reminder.user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user or not user.telegram_chat_id:
                continue

            # Send reminder via Telegram
            try:
                await _send_telegram(
                    user.telegram_chat_id,
                    f"⏰ *Recordatorio*\n\n📌 {reminder.message}\n\n"
                    f"_Responde con tu actividad cuando la completes_",
                )
                reminder.last_sent_at = now
                logger.info("Reminder delivered: user_id=%s msg=%s", user.id, reminder.message)
            except Exception as e:
                logger.error("Failed to deliver reminder: %s", e)

        await db.commit()


async def send_weekly_summaries():
    """Send weekly activity summaries to all users (Sunday 20:00 UTC)."""
    async with AsyncSessionLocal() as db:
        # Get all users with telegram linked
        result = await db.execute(
            select(User).where(User.telegram_chat_id != None)
        )
        users = result.scalars().all()

        week_ago = datetime.utcnow() - timedelta(days=7)

        for user in users:
            try:
                # Get week's activities
                act_result = await db.execute(
                    select(Activity).where(
                        Activity.user_id == user.id,
                        Activity.timestamp >= week_ago,
                    )
                )
                activities = act_result.scalars().all()

                # Compile stats
                total = len(activities)
                total_cal = sum(a.calories for a in activities)
                total_min = sum(a.duration_minutes or 0 for a in activities)
                types = {}
                for a in activities:
                    types[a.activity_type] = types.get(a.activity_type, 0) + 1

                # Build summary message
                if total == 0:
                    msg = (
                        "📊 *Resumen semanal*\n\n"
                        "Esta semana no registraste actividades.\n"
                        "¡Ánimo! Cualquier pequeño paso cuenta 💪"
                    )
                else:
                    type_lines = "\n".join(f"  • {k.capitalize()}: {v}x" for k, v in sorted(types.items(), key=lambda x: -x[1]))
                    msg = (
                        f"📊 *Resumen semanal*\n\n"
                        f"🏆 *{total}* actividades registradas\n"
                        f"⏱ {total_min} min totales\n"
                        f"🔥 {total_cal} cal quemadas\n\n"
                        f"📋 Desglose:\n{type_lines}\n\n"
                        f"¡Sigue así! 🚀"
                    )

                await _send_telegram(user.telegram_chat_id, msg)
                logger.info("Weekly summary sent to user_id=%s", user.id)

            except Exception as e:
                logger.error("Failed to send weekly summary to user_id=%s: %s", user.id, e)


async def _send_telegram(chat_id: int, text: str):
    """Send message via Telegram Bot API."""
    import httpx
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        })


def start_scheduler():
    """Start the APScheduler with all jobs."""
    # Check reminders every minute
    scheduler.add_job(
        deliver_reminders,
        trigger=IntervalTrigger(minutes=1),
        id="deliver_reminders",
        replace_existing=True,
    )

    # Weekly summary every Sunday at 20:00 UTC
    scheduler.add_job(
        send_weekly_summaries,
        trigger=CronTrigger(day_of_week="sun", hour=20, minute=0),
        id="weekly_summaries",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("APScheduler started: reminders (1min), weekly summary (Sun 20:00 UTC)")


def stop_scheduler():
    """Shutdown the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
