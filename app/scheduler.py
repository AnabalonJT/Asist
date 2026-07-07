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
    """Check and deliver due reminders every minute, respecting user timezones."""
    from zoneinfo import ZoneInfo

    now_utc = datetime.utcnow()

    async with AsyncSessionLocal() as db:
        # Get ALL active reminders with their user's timezone
        result = await db.execute(
            select(Reminder, User.timezone, User.telegram_chat_id)
            .join(User, Reminder.user_id == User.id)
            .where(Reminder.active == True, User.telegram_chat_id != None)
        )
        rows = result.all()

        if not rows:
            return

        for reminder, user_tz, chat_id in rows:
            # Get current time in user's timezone
            try:
                tz = ZoneInfo(user_tz or "America/Santiago")
            except Exception:
                tz = ZoneInfo("America/Santiago")

            user_now = datetime.now(tz)
            user_current_time = user_now.strftime("%H:%M")

            # Check if it's time to deliver this reminder
            if reminder.schedule != user_current_time:
                continue

            # Skip if already sent in last 23 hours (prevent duplicates)
            if reminder.last_sent_at:
                hours_since = (now_utc - reminder.last_sent_at).total_seconds() / 3600
                if hours_since < 23:
                    continue

            # Check frequency / day rules
            day_of_week = user_now.weekday()  # 0=Mon, 6=Sun
            today_str = user_now.strftime("%Y-%m-%d")

            if reminder.frequency == "weekdays" and day_of_week >= 5:
                continue
            elif reminder.frequency == "weekends" and day_of_week < 5:
                continue
            elif reminder.frequency == "specific_days" and reminder.schedule_days:
                allowed_days = [int(d.strip()) for d in reminder.schedule_days.split(",") if d.strip().isdigit()]
                if day_of_week not in allowed_days:
                    continue
            elif reminder.frequency == "once":
                if reminder.schedule_date and reminder.schedule_date != today_str:
                    continue
            elif reminder.frequency == "biweekly":
                if reminder.last_sent_at:
                    days_since = (now_utc - reminder.last_sent_at).days
                    if days_since < 13:  # ~2 weeks
                        continue
            elif reminder.frequency == "weekly" and day_of_week != 0:
                continue

            # Send reminder
            try:
                await _send_telegram(
                    chat_id,
                    f"⏰ *Recordatorio*\n\n"
                    f"📌 {reminder.message}\n\n"
                    f"🕐 Son las {user_current_time} — ¡no te olvides!",
                )
                reminder.last_sent_at = now_utc
                # Auto-deactivate one-time reminders
                if reminder.frequency == "once":
                    reminder.active = False
                logger.info("Reminder delivered: tz=%s schedule=%s msg=%s", user_tz, reminder.schedule, reminder.message)
            except Exception as e:
                logger.error("Failed to deliver reminder: %s", e)

        await db.commit()


async def send_weekly_summaries():
    """Send weekly activity summaries to all users (Sunday 20:00 UTC)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.telegram_chat_id != None)
        )
        users = result.scalars().all()

        week_ago = datetime.utcnow() - timedelta(days=7)

        for user in users:
            try:
                act_result = await db.execute(
                    select(Activity).where(
                        Activity.user_id == user.id,
                        Activity.timestamp >= week_ago,
                    )
                )
                activities = act_result.scalars().all()

                total = len(activities)
                total_cal = sum(a.calories for a in activities)
                total_min = sum(a.duration_minutes or 0 for a in activities)
                types = {}
                for a in activities:
                    types[a.activity_type] = types.get(a.activity_type, 0) + 1

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
    scheduler.add_job(
        deliver_reminders,
        trigger=IntervalTrigger(minutes=1),
        id="deliver_reminders",
        replace_existing=True,
    )

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
