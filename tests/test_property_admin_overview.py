"""Property-based tests (Hypothesis) for the admin System_Overview endpoint
(``app/routes/admin.py`` -> ``GET /api/admin/overview``, mounted at ``/api/admin``).

Two design properties are exercised here, sharing one DB harness:

- Property 1 (task 3.1): overview aggregate totals equal the true row counts of
  the seeded users/activities/goals/reminders/challenges, with
  ``telegram_linked_users`` equal to the number of users whose ``telegram_chat_id``
  is non-null.
- Property 2 (task 3.2): ``active_users_7d`` / ``active_users_30d`` equal the number
  of DISTINCT users owning at least one Activity whose ``timestamp`` is within the
  trailing 7-/30-day window (``>= utcnow() - timedelta(days=N)``); the 7d count is
  never greater than the 30d count; a user whose only activity is older than 30d is
  excluded.

Setup mirrors the proven route-level harness of ``tests/test_goal_plan_routes.py``
and ``tests/test_food_barcode_routes.py`` (there is NO conftest.py): a throwaway
FastAPI app mounting ONLY ``admin.router`` at ``/api/admin``, an in-memory async
SQLite engine, ``import app.models`` + ``Base.metadata.create_all`` to build the
full schema, ``app.database.get_db`` overridden to yield the shared session, and a
real admin JWT minted by ``auth_service.create_token(user_id, is_admin=True)`` for a
seeded user whose ``is_admin`` is True.

Expected values are computed independently in Python from the seeded data. Activity
timestamps are generated relative to a single ``datetime.utcnow()`` captured per
example, with a safety margin around the 7d/30d cutoffs so the tiny clock drift
between seeding and the request handler cannot flip a boundary row.

User-facing identifiers and comments are English; this is backend test code.
"""
import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db

# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (FKs from activities/goals/reminders/
# challenges point at users).
import app.models  # noqa: F401
from app.models.user import User
from app.models.activity import Activity
from app.models.goal import Goal
from app.models.reminder import Reminder
from app.models.challenge import Challenge
from app.routes import admin
from app.services.auth_service import auth_service


# ── Harness ──────────────────────────────────────────────────────────────────
class Harness:
    """A throwaway app + in-memory DB. Builds the schema, seeds a single ADMIN
    user, mints a real admin JWT, and exposes a TestClient wired to the admin
    router with ``get_db`` overridden to the shared session factory.

    The seeded admin counts as one User row (and, for active-window purposes, owns
    no activities unless a test seeds some for it), so tests compute expected
    values over *all* rows in the DB including this admin.
    """

    def __init__(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        asyncio.run(self._create_schema())
        self.admin_id = asyncio.run(self._seed_admin())
        self.token = auth_service.create_token(self.admin_id, is_admin=True)

        app = FastAPI()
        app.include_router(admin.router, prefix="/api/admin")
        session_factory = self.session_factory

        async def _override_get_db():
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app)

    async def _create_schema(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _seed_admin(self) -> int:
        async with self.session_factory() as db:
            admin_user = User(
                email="admin@example.com", password_hash="x", is_admin=True
            )
            db.add(admin_user)
            await db.flush()
            await db.commit()
            return admin_user.id

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def close(self):
        self.client.close()
        asyncio.run(self.engine.dispose())


@pytest.fixture
def harness():
    h = Harness()
    try:
        yield h
    finally:
        h.close()


# ── Generators ───────────────────────────────────────────────────────────────
# A "seed plan" describes the population to insert for one Hypothesis example:
#   - a list of users, each with whether it is telegram-linked and how many
#     goals / reminders / challenges it owns, plus a list of per-activity
#     "day offsets" (how many days before utcnow() the activity timestamp sits).
# Expected overview values are then computed directly from this plan in Python.

# Day offsets straddle the 7d and 30d cutoffs with a margin so boundary rows are
# unambiguous: inside-7d (and thus inside-30d), inside-30d-only, and outside-30d.
_DAY_OFFSETS = st.sampled_from([0, 1, 3, 6, 8, 15, 29, 31, 45, 100])

_user_plan = st.fixed_dictionaries(
    {
        "linked": st.booleans(),
        "goals": st.integers(min_value=0, max_value=3),
        "reminders": st.integers(min_value=0, max_value=3),
        "challenges": st.integers(min_value=0, max_value=3),
        # Day offsets for this user's activities (empty list => no activities).
        "activity_offsets": st.lists(_DAY_OFFSETS, max_size=5),
    }
)

# 0..6 extra (non-admin) users per example; the admin itself is always present.
_seed_plan = st.lists(_user_plan, max_size=6)


async def _apply_plan(session_factory, plan, now):
    """Insert the generated population and return the expected aggregate counts.

    ``now`` is the reference utcnow() captured by the test; activity timestamps are
    ``now - timedelta(days=offset)``. Returns a dict of expected overview fields
    plus the set of (user_id) that are active within each window — computed purely
    from the plan, independent of the SQL the endpoint runs.
    """
    # The admin user (seeded by the harness) already exists: 1 user row, not
    # linked, owning no activities/goals/reminders/challenges by itself.
    expected = {
        "total_users": 1,  # the admin
        "telegram_linked_users": 0,
        "total_activities": 0,
        "total_goals": 0,
        "total_reminders": 0,
        "total_challenges": 0,
    }
    active_7d_users: set[int] = set()
    active_30d_users: set[int] = set()

    # telegram_chat_id must be unique (BigInteger unique column); hand out a
    # distinct positive id to each linked user.
    next_chat_id = 1000

    async with session_factory() as db:
        # The harness fixture is function-scoped, but Hypothesis replays many
        # examples against the SAME harness/DB. Reset to the clean baseline (the
        # single admin, with no activities/goals/reminders/challenges) before
        # seeding this example, so the "baseline = admin only" invariant holds and
        # unique email / telegram_chat_id columns never collide across examples.
        await db.execute(delete(Activity))
        await db.execute(delete(Goal))
        await db.execute(delete(Reminder))
        await db.execute(delete(Challenge))
        await db.execute(delete(User).where(User.is_admin.is_(False)))
        await db.commit()

        for idx, up in enumerate(plan):
            chat_id = None
            if up["linked"]:
                chat_id = next_chat_id
                next_chat_id += 1
            user = User(
                email=f"user{idx}@example.com",
                password_hash="x",
                is_admin=False,
                telegram_chat_id=chat_id,
            )
            db.add(user)
            await db.flush()  # assign user.id

            expected["total_users"] += 1
            if chat_id is not None:
                expected["telegram_linked_users"] += 1

            for g in range(up["goals"]):
                db.add(
                    Goal(
                        user_id=user.id,
                        activity_type="deporte",
                        description=f"meta {g}",
                    )
                )
            expected["total_goals"] += up["goals"]

            for r in range(up["reminders"]):
                db.add(
                    Reminder(
                        user_id=user.id,
                        schedule="08:00",
                        frequency="daily",
                        message=f"recordatorio {r}",
                    )
                )
            expected["total_reminders"] += up["reminders"]

            for c in range(up["challenges"]):
                db.add(Challenge(user_id=user.id, name=f"reto {c}"))
            expected["total_challenges"] += up["challenges"]

            for off in up["activity_offsets"]:
                ts = now - timedelta(days=off)
                db.add(
                    Activity(
                        user_id=user.id,
                        activity_type="deporte",
                        calories=100,
                        timestamp=ts,
                    )
                )
                expected["total_activities"] += 1
                # An activity counts toward a window when its offset places it
                # inside that trailing window. The margin in _DAY_OFFSETS keeps
                # these classifications stable against sub-second clock drift.
                if off <= 7:
                    active_7d_users.add(user.id)
                if off <= 30:
                    active_30d_users.add(user.id)

        await db.commit()

    expected["active_users_7d"] = len(active_7d_users)
    expected["active_users_30d"] = len(active_30d_users)
    return expected


# ── Property 1 (task 3.1): overview totals equal row counts ──────────────────
# Feature: admin-panel, Property 1: Overview totals equal row counts
# Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(plan=_seed_plan)
def test_overview_totals_equal_row_counts(harness, plan):
    """For any seeded population, the overview's total_users /
    telegram_linked_users / total_activities / total_goals / total_reminders /
    total_challenges equal the true counts of the seeded rows."""
    now = datetime.utcnow()
    expected = asyncio.run(_apply_plan(harness.session_factory, plan, now))

    resp = harness.client.get("/api/admin/overview", headers=harness.headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_users"] == expected["total_users"]
    assert body["telegram_linked_users"] == expected["telegram_linked_users"]
    assert body["total_activities"] == expected["total_activities"]
    assert body["total_goals"] == expected["total_goals"]
    assert body["total_reminders"] == expected["total_reminders"]
    assert body["total_challenges"] == expected["total_challenges"]


# ── Property 2 (task 3.2): active-user window counts are correct ─────────────
# Feature: admin-panel, Property 2: Active-user window counts are correct
# Validates: Requirements 2.7, 2.8
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(plan=_seed_plan)
def test_active_user_window_counts(harness, plan):
    """active_users_7d / active_users_30d equal the number of DISTINCT users with
    at least one Activity inside the trailing 7-/30-day window; 7d <= 30d; a user
    whose only activity is older than 30 days is excluded."""
    now = datetime.utcnow()
    expected = asyncio.run(_apply_plan(harness.session_factory, plan, now))

    resp = harness.client.get("/api/admin/overview", headers=harness.headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["active_users_7d"] == expected["active_users_7d"]
    assert body["active_users_30d"] == expected["active_users_30d"]
    # Monotonicity: the 7-day window is a subset of the 30-day window.
    assert body["active_users_7d"] <= body["active_users_30d"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
