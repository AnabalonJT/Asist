"""Tests for goal management in the POLLING path (app.services.telegram_bot).

The webhook path already handled goal create/list/delete; the polling path did
not dispatch intent="goal" at all. These tests cover the new `_handle_goal`
(create persists an active goal, "list" returns active goals, "delete" by
activity_type substring soft-deletes and a non-matching delete leaves goals
untouched) plus the pure `_build_goal_list_message` helper.

Uses a throwaway in-memory async SQLite DB (mirroring tests/test_goal_progress.py)
and a minimal fake Telegram update — no real Telegram/OpenRouter calls.
User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
import app.models  # noqa: F401  (register all tables on Base.metadata)
from app.models.user import User
from app.models.goal import Goal
from app.services import telegram_bot


# ──────────────────────────── pure helper ────────────────────────────

class TestBuildGoalListMessage:
    def test_header_and_in_progress_goal(self):
        msg = telegram_bot._build_goal_list_message(
            [("Correr", 2, 3, "weekly")]
        )
        assert msg.startswith("🎯 *Tus metas:*")
        # In-progress goal uses the 🔄 status and the shared progress bar.
        assert "🔄 Correr" in msg
        assert "▓▓░ 2/3 esta semana" in msg

    def test_completed_goal_uses_check_status(self):
        msg = telegram_bot._build_goal_list_message(
            [("Meditar", 1, 1, "daily")]
        )
        assert "✅ Meditar" in msg
        assert "▓ 1/1 hoy" in msg

    def test_multiple_goals_each_on_own_block(self):
        msg = telegram_bot._build_goal_list_message(
            [("Correr", 0, 3, "weekly"), ("Leer", 4, 4, "monthly")]
        )
        assert "🔄 Correr" in msg
        assert "░░░ 0/3 esta semana" in msg
        assert "✅ Leer" in msg
        assert "▓▓▓▓ 4/4 este mes" in msg


# ──────────────────────── fake Telegram update ────────────────────────

class _FakeMessage:
    def __init__(self):
        self.replies = []  # list of (text, parse_mode)

    async def reply_text(self, text, parse_mode=None):
        self.replies.append((text, parse_mode))


class _FakeUpdate:
    def __init__(self):
        self.message = _FakeMessage()


# ──────────────────────── async DB test harness ────────────────────────

async def _run(coro_fn, monkeypatch):
    """Spin up an in-memory async SQLite DB and point telegram_bot at it."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # _handle_goal opens sessions via AsyncSessionLocal in the telegram_bot module.
    monkeypatch.setattr(telegram_bot, "AsyncSessionLocal", factory)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as seed_db:
            user = User(email="poller@example.com", password_hash="x")
            seed_db.add(user)
            await seed_db.commit()
            await seed_db.refresh(user)
        await coro_fn(user, factory)
    finally:
        await engine.dispose()


def test_create_persists_active_goal(monkeypatch):
    """A goal create response persists an active goal and confirms it."""
    async def scenario(user, factory):
        update = _FakeUpdate()
        response = {
            "intent": "goal",
            "data": {
                "action": "create",
                "activity_type": "correr",
                "target_count": 3,
                "period": "weekly",
                "description": "Correr 3x/weekly",
                "ends_at": None,
            },
        }
        await telegram_bot._handle_goal(update, user, response)

        # Confirmation sent.
        assert update.message.replies, "expected a confirmation reply"
        text = update.message.replies[0][0]
        assert "Meta creada" in text

        # Goal persisted, active, and normalized (correr -> running).
        async with factory() as db:
            goals = (await db.execute(
                select(Goal).where(Goal.user_id == user.id)
            )).scalars().all()
        assert len(goals) == 1
        assert goals[0].active is True
        assert goals[0].activity_type == "running"
        assert goals[0].target_count == 3
        assert goals[0].period == "weekly"

    asyncio.run(_run(scenario, monkeypatch))


def test_list_returns_active_goals(monkeypatch):
    """'list' returns only active goals, each with a progress bar line."""
    async def scenario(user, factory):
        async with factory() as db:
            db.add(Goal(user_id=user.id, activity_type="running",
                        description="Correr", target_count=3, period="weekly", active=True))
            db.add(Goal(user_id=user.id, activity_type="reading",
                        description="Leer", target_count=2, period="daily", active=True))
            # An inactive goal must be excluded from the list.
            db.add(Goal(user_id=user.id, activity_type="swimming",
                        description="Nadar", target_count=1, period="weekly", active=False))
            await db.commit()

        update = _FakeUpdate()
        response = {"intent": "goal", "data": {"action": "list"}}
        await telegram_bot._handle_goal(update, user, response)

        assert len(update.message.replies) == 1
        text = update.message.replies[0][0]
        assert "🎯 *Tus metas:*" in text
        assert "Correr" in text
        assert "Leer" in text
        assert "Nadar" not in text  # inactive goal excluded

    asyncio.run(_run(scenario, monkeypatch))


def test_list_empty_prompts_to_create(monkeypatch):
    """No active goals -> a friendly 'create one' message, not the list header."""
    async def scenario(user, factory):
        update = _FakeUpdate()
        response = {"intent": "goal", "data": {"action": "list"}}
        await telegram_bot._handle_goal(update, user, response)

        text = update.message.replies[0][0]
        assert "No tienes metas activas" in text

    asyncio.run(_run(scenario, monkeypatch))


def test_delete_by_substring_soft_deletes(monkeypatch):
    """'eliminar meta de correr' matches by activity_type substring and sets active=False."""
    async def scenario(user, factory):
        async with factory() as db:
            db.add(Goal(user_id=user.id, activity_type="running",
                        description="Correr", target_count=3, period="weekly", active=True))
            db.add(Goal(user_id=user.id, activity_type="reading",
                        description="Leer", target_count=2, period="daily", active=True))
            await db.commit()

        update = _FakeUpdate()
        # "correr" normalizes to "running"; substring of the stored type.
        response = {
            "intent": "goal",
            "data": {"action": "delete", "activity_type": "run"},
        }
        await telegram_bot._handle_goal(update, user, response)

        text = update.message.replies[0][0]
        assert "eliminada" in text

        # Soft delete: the running goal is now inactive but still present;
        # the reading goal is untouched.
        async with factory() as db:
            running = (await db.execute(
                select(Goal).where(Goal.user_id == user.id, Goal.activity_type == "running")
            )).scalar_one()
            reading = (await db.execute(
                select(Goal).where(Goal.user_id == user.id, Goal.activity_type == "reading")
            )).scalar_one()
        assert running.active is False
        assert reading.active is True

    asyncio.run(_run(scenario, monkeypatch))


def test_delete_no_match_leaves_goals_untouched(monkeypatch):
    """A delete that matches nothing reports 'no encontré' and changes no goals."""
    async def scenario(user, factory):
        async with factory() as db:
            db.add(Goal(user_id=user.id, activity_type="running",
                        description="Correr", target_count=3, period="weekly", active=True))
            await db.commit()

        update = _FakeUpdate()
        response = {
            "intent": "goal",
            "data": {"action": "delete", "activity_type": "natacion"},
        }
        await telegram_bot._handle_goal(update, user, response)

        text = update.message.replies[0][0]
        assert "No encontré esa meta" in text

        async with factory() as db:
            running = (await db.execute(
                select(Goal).where(Goal.user_id == user.id, Goal.activity_type == "running")
            )).scalar_one()
        assert running.active is True  # untouched

    asyncio.run(_run(scenario, monkeypatch))
