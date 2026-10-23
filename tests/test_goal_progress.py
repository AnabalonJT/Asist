"""Unit tests for the shared habit-goal progress helper (app.services.goal_progress).

Covers:
- period_start window math for daily/weekly/monthly (pure).
- goal_progress_message "en progreso" vs "¡Meta cumplida!" branches (pure).
- progress_bar rendering and capping (pure).
- goal_progress_count / check_goal_progress against a throwaway in-memory async
  SQLite DB: an activity inside the current period counts, one outside does not,
  and reaching the target produces the "🏆 ¡Meta cumplida!" message.

Mirrors the async-SQLite-per-test pattern used in test_property_goal_wizard_persist.py.
User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
import app.models  # noqa: F401  (register all tables on Base.metadata)
from app.models.user import User
from app.models.activity import Activity
from app.models.goal import Goal
from app.services import goal_progress


# ──────────────────────────── pure helpers ────────────────────────────

class TestPeriodStart:
    def test_daily_is_midnight_today(self):
        now = datetime(2026, 3, 18, 14, 30, 45, 123)
        start = goal_progress.period_start("daily", now)
        assert start == datetime(2026, 3, 18, 0, 0, 0, 0)

    def test_weekly_is_monday_midnight(self):
        # 2026-03-18 is a Wednesday -> Monday is 2026-03-16.
        now = datetime(2026, 3, 18, 14, 30)
        start = goal_progress.period_start("weekly", now)
        assert start == datetime(2026, 3, 16, 0, 0, 0, 0)
        assert start.weekday() == 0

    def test_monthly_is_first_of_month(self):
        now = datetime(2026, 3, 18, 14, 30)
        start = goal_progress.period_start("monthly", now)
        assert start == datetime(2026, 3, 1, 0, 0, 0, 0)

    def test_unknown_period_defaults_monthly(self):
        now = datetime(2026, 3, 18, 14, 30)
        assert goal_progress.period_start("weird", now) == datetime(2026, 3, 1, 0, 0)


class TestProgressBar:
    def test_partial(self):
        assert goal_progress.progress_bar(2, 3) == "▓▓░"

    def test_full(self):
        assert goal_progress.progress_bar(3, 3) == "▓▓▓"

    def test_empty(self):
        assert goal_progress.progress_bar(0, 3) == "░░░"

    def test_overflow_is_capped(self):
        # More than target must not produce negative/extra blocks.
        assert goal_progress.progress_bar(5, 3) == "▓▓▓"


class TestGoalProgressMessage:
    def test_in_progress_weekly(self):
        msg = goal_progress.goal_progress_message("Correr", 2, 3, "weekly")
        assert msg == "🎯 Meta: ▓▓░ 2/3 esta semana"

    def test_goal_met(self):
        msg = goal_progress.goal_progress_message("Correr", 3, 3, "weekly")
        assert msg.startswith("🏆 *¡Meta cumplida!*")
        assert "3/3 esta semana" in msg

    def test_goal_exceeded_still_met(self):
        msg = goal_progress.goal_progress_message("Leer", 5, 3, "daily")
        assert "¡Meta cumplida!" in msg
        assert "5/3 hoy" in msg

    def test_monthly_label(self):
        msg = goal_progress.goal_progress_message("Nadar", 1, 4, "monthly")
        assert "este mes" in msg


# ──────────────────────── async DB-backed helpers ────────────────────────

async def _seed_user_and_goal(db, *, activity_type="running", target=3, period="weekly"):
    user = User(email="tester@example.com", password_hash="x")
    db.add(user)
    await db.flush()
    goal = Goal(
        user_id=user.id,
        activity_type=activity_type,
        description="Correr",
        target_count=target,
        period=period,
        active=True,
    )
    db.add(goal)
    await db.flush()
    return user, goal


async def _add_activity(db, user_id, activity_type, when):
    db.add(Activity(
        user_id=user_id,
        activity_type=activity_type,
        calories=0,
        timestamp=when,
    ))
    await db.flush()


async def _run(coro_fn):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            await coro_fn(db)
    finally:
        await engine.dispose()


def test_count_includes_in_window_excludes_out_of_window():
    """An activity inside the current week counts; one before it does not."""
    async def scenario(db):
        now = datetime.utcnow()
        week_start = goal_progress.period_start("weekly", now)
        user, goal = await _seed_user_and_goal(db, period="weekly")

        # Two activities inside the current week (raw rows both count).
        await _add_activity(db, user.id, "running", week_start + timedelta(hours=1))
        await _add_activity(db, user.id, "running", week_start + timedelta(days=1))
        # One activity BEFORE the window start -> must not count.
        await _add_activity(db, user.id, "running", week_start - timedelta(seconds=1))

        count = await goal_progress.goal_progress_count(
            db, user.id, goal.activity_type, goal.period, now
        )
        assert count == 2

    asyncio.run(_run(scenario))


def test_count_matches_via_normalized_synonym():
    """A goal 'correr' matches activities stored as the canonical 'running'."""
    async def scenario(db):
        now = datetime.utcnow()
        week_start = goal_progress.period_start("weekly", now)
        user, goal = await _seed_user_and_goal(db, activity_type="correr", period="weekly")
        await _add_activity(db, user.id, "running", week_start + timedelta(hours=2))

        count = await goal_progress.goal_progress_count(
            db, user.id, goal.activity_type, goal.period, now
        )
        assert count == 1

    asyncio.run(_run(scenario))


def test_check_goal_progress_in_progress_message():
    """Below target -> '🎯 Meta' progress line with n/target."""
    async def scenario(db):
        now = datetime.utcnow()
        week_start = goal_progress.period_start("weekly", now)
        user, _ = await _seed_user_and_goal(db, target=3, period="weekly")
        await _add_activity(db, user.id, "running", week_start + timedelta(hours=1))

        msg = await goal_progress.check_goal_progress(db, user.id, "running", now)
        assert msg is not None
        assert msg.startswith("🎯 Meta:")
        assert "1/3 esta semana" in msg

    asyncio.run(_run(scenario))


def test_check_goal_progress_meta_cumplida_when_target_reached():
    """Reaching the target flips the message to '🏆 ¡Meta cumplida!'."""
    async def scenario(db):
        now = datetime.utcnow()
        day_start = goal_progress.period_start("daily", now)
        user, _ = await _seed_user_and_goal(db, target=2, period="daily")
        await _add_activity(db, user.id, "running", day_start + timedelta(hours=1))
        await _add_activity(db, user.id, "running", day_start + timedelta(hours=2))

        msg = await goal_progress.check_goal_progress(db, user.id, "running", now)
        assert msg is not None
        assert "¡Meta cumplida!" in msg
        assert "2/2 hoy" in msg

    asyncio.run(_run(scenario))


def test_check_goal_progress_none_when_no_goal():
    """No active goal for the activity type -> no message appended."""
    async def scenario(db):
        now = datetime.utcnow()
        user = User(email="nogoals@example.com", password_hash="x")
        db.add(user)
        await db.flush()
        await _add_activity(db, user.id, "running", now)

        msg = await goal_progress.check_goal_progress(db, user.id, "running", now)
        assert msg is None

    asyncio.run(_run(scenario))
