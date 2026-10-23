"""Shared habit-goal progress calculation and messaging.

A single source of truth for "how many times a habit was completed this period"
so the Telegram bot (webhook + polling), the goals/challenges routes, and the
scheduler all agree. Previously each site had its own copy of the window math and
the webhook owned the confirmation-message text; the polling path lagged behind
and never showed goal progress at all. This module removes that drift.

Definitions:
- "how many times completed this period" = the count of Activity rows whose
  (normalized) activity_type matches the goal, logged since the start of the
  current period. Raw rows are counted (not distinct days): logging the same
  activity twice in a day counts as 2 toward a target.
- period window start:
    daily   -> 00:00 today
    weekly  -> 00:00 Monday of the current ISO week
    monthly -> 00:00 on the 1st of the current month
  (all in naive UTC, matching Activity.timestamp which is stored naive-UTC).

User-facing text is Spanish; identifiers and comments are English.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.services.activity_types import normalize_activity_type

# Human-readable period label used in the Spanish confirmation line.
_PERIOD_TEXT = {"daily": "hoy", "weekly": "esta semana", "monthly": "este mes"}


def period_start(period: str, now: datetime | None = None) -> datetime:
    """Return the start of the goal's current period window (naive UTC). Pure.

    ``now`` defaults to ``datetime.utcnow()``. An unknown/empty period is treated
    as "monthly" to match the pre-existing ``else`` branches in the old copies.
    """
    now = now or datetime.utcnow()
    p = (period or "").lower()
    if p == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if p == "weekly":
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    # monthly (and any unknown period) -> first of month
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def goal_progress_count(
    db: AsyncSession,
    user_id: int,
    activity_type: str,
    period: str,
    now: datetime | None = None,
) -> int:
    """Count matching activities logged in the goal's current period.

    Matching is done on the canonical (normalized) activity_type so a goal and a
    logged activity that use different synonyms for the same thing still match.
    """
    start = period_start(period, now)
    result = await db.execute(
        select(sa_func.count())
        .select_from(Activity)
        .where(
            Activity.user_id == user_id,
            sa_func.lower(Activity.activity_type) == normalize_activity_type(activity_type),
            Activity.timestamp >= start,
        )
    )
    return result.scalar() or 0


def progress_bar(current: int, target: int) -> str:
    """Render a text progress bar: filled blocks up to ``current`` (capped)."""
    filled = min(max(current, 0), target)
    remaining = max(target - filled, 0)
    return "▓" * filled + "░" * remaining


def goal_progress_message(description: str, progress: int, target_count: int, period: str) -> str:
    """Build the Spanish goal-progress line appended to an activity confirmation.

    Returns the "🏆 ¡Meta cumplida!" line when the target is reached, otherwise a
    "🎯 Meta: ▓▓░ n/target esta semana" progress line. Pure/string-only so it can
    be unit-tested without a database.
    """
    period_text = _PERIOD_TEXT.get(period, period)
    if progress >= target_count:
        return f"🏆 *¡Meta cumplida!* {description} ({progress}/{target_count} {period_text})"
    bar = progress_bar(progress, target_count)
    return f"🎯 Meta: {bar} {progress}/{target_count} {period_text}"


async def check_goal_progress(
    db: AsyncSession,
    user_id: int,
    activity_type: str,
    now: datetime | None = None,
) -> str | None:
    """Return a goal-progress message for the user's active goal of this type.

    Looks up a single active Goal matching the (normalized) activity_type; if one
    exists, counts progress for its current period and returns the Spanish line to
    append to the activity confirmation. Returns ``None`` when the user has no
    active goal for this activity type.
    """
    from app.models.goal import Goal  # local import to avoid a model import cycle

    normalized = normalize_activity_type(activity_type)
    result = await db.execute(
        select(Goal).where(
            Goal.user_id == user_id,
            sa_func.lower(Goal.activity_type) == normalized,
            Goal.active == True,  # noqa: E712
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        return None

    progress = await goal_progress_count(db, user_id, goal.activity_type, goal.period, now)
    return goal_progress_message(goal.description, progress, goal.target_count, goal.period)
