"""Shared, pure helpers for rendering reminder schedules in Spanish.

Both reminder-list code paths (the Telegram webhook in ``app/routes/telegram.py``
and the polling bot in ``app/services/telegram_bot.py``) render the "Tus
recordatorios" list. Keeping the human-readable formatting here means both use
the SAME logic and it is unit-testable without a database or Telegram.

Day numbering follows the rest of the codebase and the dashboard
(``src/components/ReminderList.tsx``): 0 = Monday .. 6 = Sunday → Lun..Dom.

``frequency`` values (see ``app/models/reminder.py``):
    daily, weekdays, weekends, specific_days (uses schedule_days CSV),
    once (uses schedule_date), biweekly, weekly.

All user-facing text is Spanish.
"""
from __future__ import annotations

# 0 = Monday .. 6 = Sunday
DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

# Short Spanish month names (index 1..12), matching the dashboard's "6 Jul".
_MONTHS_ES = [
    "", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
]


def _parse_days(schedule_days: str | None) -> list[int]:
    """Parse a CSV of day numbers (e.g. "0,2") into a clean [0..6] list."""
    if not schedule_days:
        return []
    days: list[int] = []
    for part in schedule_days.split(","):
        part = part.strip()
        if part.isdigit():
            d = int(part)
            if 0 <= d <= 6:
                days.append(d)
    return days


def _format_once_date(schedule_date: str | None, schedule: str | None) -> str:
    """Render a one-time reminder date like "6 Jul 08:00".

    ``schedule_date`` is an ISO date ("2026-07-06"). ``schedule`` is HH:MM.
    Falls back gracefully when parts are missing or malformed.
    """
    day_month = ""
    if schedule_date:
        parts = schedule_date.split("-")
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            month = int(parts[1])
            day = int(parts[2])
            if 1 <= month <= 12:
                # Strip a leading zero from the day for "6 Jul" (not "06 Jul").
                day_month = f"{day} {_MONTHS_ES[month]}"
        if not day_month:
            # Unparseable date string: show it verbatim rather than losing it.
            day_month = schedule_date

    parts_out = [p for p in (day_month, (schedule or "").strip()) if p]
    if not parts_out:
        return "una vez"
    return " ".join(parts_out)


def format_reminder_schedule(
    frequency: str,
    schedule: str | None = None,
    schedule_days: str | None = None,
    schedule_date: str | None = None,
) -> str:
    """Return a human-readable Spanish description of a reminder's schedule.

    Recurring frequencies render the cadence ("Todos los días", "Lun a Vie",
    "Sáb y Dom", "Lun y Mié", "Cada 2 semanas", "Semanal"). One-time ("once")
    reminders render the date and time ("6 Jul 08:00") so the UI can clearly
    distinguish them from recurring ones.
    """
    if frequency == "daily":
        return "Todos los días"
    if frequency == "weekdays":
        return "Lun a Vie"
    if frequency == "weekends":
        return "Sáb y Dom"
    if frequency == "specific_days":
        days = _parse_days(schedule_days)
        if days:
            return " y ".join(DAY_NAMES[d] for d in days)
        return "Días específicos"
    if frequency == "once":
        return _format_once_date(schedule_date, schedule)
    if frequency == "biweekly":
        return "Cada 2 semanas"
    if frequency == "weekly":
        return "Semanal"
    return frequency


def format_reminder_line(
    message: str,
    frequency: str,
    schedule: str | None = None,
    schedule_days: str | None = None,
    schedule_date: str | None = None,
) -> str:
    """Render a single "Tus recordatorios" list line for the bot.

    Recurring reminders are marked with 🔁 and show the time plus cadence:
        "🔁 Meditar — 07:30 (Lun y Mié)"
    One-time reminders are marked with 📅 and show the date/time inline:
        "📅 Ir al Dr — 6 Jul 08:00 (una vez)"
    The distinct markers and tag let the user tell recurring from one-time.
    """
    desc = format_reminder_schedule(frequency, schedule, schedule_days, schedule_date)
    if frequency == "once":
        return f"📅 {message} — {desc} (una vez)"
    time_part = (schedule or "").strip()
    if time_part:
        return f"🔁 {message} — {time_part} ({desc})"
    return f"🔁 {message} — {desc}"


def format_reminder_from_model(r) -> str:
    """Render a list line from a Reminder ORM-ish object with the right attrs."""
    return format_reminder_line(
        message=r.message,
        frequency=r.frequency,
        schedule=getattr(r, "schedule", None),
        schedule_days=getattr(r, "schedule_days", None),
        schedule_date=getattr(r, "schedule_date", None),
    )
