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
_summary_sent_this_week: str = ""  # Track to prevent duplicate sends


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
    global _summary_sent_this_week
    
    # Prevent duplicate sends (multiple machines or restarts)
    current_week = datetime.utcnow().strftime("%Y-W%W")
    if current_week == _summary_sent_this_week:
        return
    _summary_sent_this_week = current_week

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


async def send_goal_notifications():
    """
    Duolingo-style notifications for goals.
    Sends at 20:00 user time. Frequency decreases if user ignores.
    """
    from zoneinfo import ZoneInfo
    from app.models.goal import Goal

    now_utc = datetime.utcnow()

    async with AsyncSessionLocal() as db:
        # Get users with telegram linked and active goals
        result = await db.execute(
            select(User).where(User.telegram_chat_id != None)
        )
        users = result.scalars().all()

        for user in users:
            try:
                # Check if it's 20:00 in user's timezone
                try:
                    tz = ZoneInfo(user.timezone or "America/Santiago")
                except Exception:
                    tz = ZoneInfo("America/Santiago")

                user_now = datetime.now(tz)
                if user_now.strftime("%H:%M") != "20:00":
                    continue

                # Get active goals (standalone + from challenges)
                goals_result = await db.execute(
                    select(Goal).where(Goal.user_id == user.id, Goal.active == True)
                )
                goals = goals_result.scalars().all()

                if not goals:
                    continue

                # Check which goals are NOT yet met for today/this week
                pending = []
                for g in goals:
                    progress = await _calc_goal_progress(g, user.id, db)
                    if progress < g.target_count:
                        pending.append(g)

                if not pending:
                    continue  # All goals met today!

                # Build notification
                pending_list = "\n".join(f"  • {g.description}" for g in pending[:5])
                
                # Check if any goal has approaching deadline
                urgent_msg = ""
                for g in pending:
                    if g.ends_at:
                        try:
                            end = datetime.strptime(g.ends_at, "%Y-%m-%d")
                            days_left = (end - now_utc).days
                            if days_left <= 3:
                                urgent_msg = f"\n\n⚠️ *¡{g.description}* termina en {days_left} día{'s' if days_left != 1 else ''}!"
                                break
                            elif days_left <= 7:
                                urgent_msg = f"\n\n💪 Te queda 1 semana para *{g.description}*. ¡Tú puedes!"
                                break
                        except Exception:
                            pass

                msg = (
                    f"🎯 *Metas pendientes hoy*\n\n"
                    f"{pending_list}{urgent_msg}\n\n"
                    f"_¡No pierdas tu racha!_ 🔥"
                )

                await _send_telegram(user.telegram_chat_id, msg)
                logger.info("Goal notification sent to user_id=%s (%d pending)", user.id, len(pending))

            except Exception as e:
                logger.error("Goal notification error user_id=%s: %s", user.id, e)

        await db.commit()


async def _calc_goal_progress(goal, user_id: int, db) -> int:
    """Calculate progress for a goal in its current period."""
    from sqlalchemy import func as sa_func

    now = datetime.utcnow()
    if goal.period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif goal.period == "weekly":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(sa_func.count())
        .select_from(Activity)
        .where(
            Activity.user_id == user_id,
            Activity.activity_type == goal.activity_type,
            Activity.timestamp >= start,
        )
    )
    return result.scalar() or 0


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

    # Goal notifications: check every minute (sends at 20:00 user time)
    scheduler.add_job(
        send_goal_notifications,
        trigger=IntervalTrigger(minutes=1),
        id="goal_notifications",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("APScheduler started: reminders (1min), goals (1min), weekly summary (Sun 20:00 UTC)")


def stop_scheduler():
    """Shutdown the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
