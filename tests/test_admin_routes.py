"""Example-based integration tests for the Admin_API endpoints
(``app/routes/admin.py``, mounted under ``/api/admin``).

These are EXAMPLE-BASED tests (not property tests). They cover two tasks:

Task 4.1 — Auth matrix across all three endpoints
  (``GET /api/admin/overview``, ``GET /api/admin/users``,
   ``GET /api/admin/users/{id}``), parameterized over the actor:
    - no token             → 401 (or 403)   (Req 1.3)
    - garbage token        → 401            (Req 1.3)
    - non-admin JWT        → 403            (Req 1.2)
    - admin JWT            → 200            (Req 1.1, 1.4)

Task 4.2 — Single-user, 404, and null-last-activity example tests
    - ``GET /users/{id}`` for an existing user returns the AdminUserDetail
      with the expected fields (Req 4.1).
    - ``GET /users/{id}`` for a non-existent id → 404 with the "User not
      found" detail (Req 4.6).
    - a user with NO activities has ``last_activity_at == null``,
      ``activities_7d``/``activities_30d`` == 0 and ``activity_count`` == 0
      (Req 4.5, 3.9).

Setup mirrors the proven route-level pattern of
``tests/test_goal_plan_routes.py`` and ``tests/test_food_barcode_routes.py``
(there is NO conftest.py): a throwaway FastAPI app mounting ONLY
``admin.router`` at ``/api/admin``, an in-memory async SQLite engine,
``import app.models`` + ``create_all`` to build the full schema,
``app.database.get_db`` overridden to yield the shared session, an ADMIN user
AND a non-admin user seeded, and real JWTs minted by
``app.services.auth_service.auth_service.create_token``.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (FKs from activities / goals / reminders /
# challenges point at users).
import app.models  # noqa: F401
from app.models.user import User
from app.models.activity import Activity
from app.models.goal import Goal
from app.models.reminder import Reminder
from app.models.challenge import Challenge
from app.routes import admin
from app.services.auth_service import auth_service


# ── Concrete, deterministic fixture counts for the admin user ────────────────
# The admin owns a known number of each entity. Activities are split so that
# some fall inside the 7-day window and some only inside the 30-day window.
_ADMIN_ACTIVITIES_WITHIN_7D = 2
_ADMIN_ACTIVITIES_WITHIN_30D_ONLY = 3  # older than 7d but within 30d
_ADMIN_ACTIVITY_TOTAL = _ADMIN_ACTIVITIES_WITHIN_7D + _ADMIN_ACTIVITIES_WITHIN_30D_ONLY
_ADMIN_GOALS = 3
_ADMIN_REMINDERS = 2
_ADMIN_CHALLENGES = 1


# ── Harness ──────────────────────────────────────────────────────────────────
class Harness:
    """A throwaway app + in-memory DB for one test. Builds the schema, seeds an
    ADMIN user (with concrete activities/goals/reminders/challenges) and a
    non-admin user (with NO data), mints real JWTs for both, and exposes a
    TestClient wired to the admin router with ``get_db`` overridden to the shared
    session."""

    def __init__(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        asyncio.run(self._create_schema())
        self.admin_id, self.user_id, self.last_activity_at = asyncio.run(
            self._seed_data()
        )
        self.admin_token = auth_service.create_token(self.admin_id, is_admin=True)
        self.user_token = auth_service.create_token(self.user_id, is_admin=False)

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

    async def _seed_data(self):
        """Seed an admin (with data) and a non-admin (no activities).

        Returns (admin_id, non_admin_id, admin_last_activity_at)."""
        now = datetime.utcnow()
        async with self.session_factory() as db:
            admin = User(
                email="admin@example.com",
                password_hash="x",
                is_admin=True,
                telegram_chat_id=123456,  # linked
            )
            # Non-admin with NO activities/goals/reminders/challenges and no
            # Telegram link — drives the null-last-activity / zero-count case.
            plain = User(
                email="user@example.com",
                password_hash="x",
                is_admin=False,
                telegram_chat_id=None,
            )
            db.add_all([admin, plain])
            await db.flush()

            # Activities within the 7-day window (most recent one is the max).
            last_activity_at = None
            for i in range(_ADMIN_ACTIVITIES_WITHIN_7D):
                ts = now - timedelta(days=1, hours=i)
                if last_activity_at is None or ts > last_activity_at:
                    last_activity_at = ts
                db.add(Activity(
                    user_id=admin.id,
                    activity_type="running",
                    calories=100,
                    timestamp=ts,
                ))
            # Activities older than 7d but within the 30-day window.
            for i in range(_ADMIN_ACTIVITIES_WITHIN_30D_ONLY):
                ts = now - timedelta(days=15, hours=i)
                db.add(Activity(
                    user_id=admin.id,
                    activity_type="cycling",
                    calories=200,
                    timestamp=ts,
                ))

            for i in range(_ADMIN_GOALS):
                db.add(Goal(
                    user_id=admin.id,
                    activity_type="running",
                    description=f"Meta {i}",
                ))
            for i in range(_ADMIN_REMINDERS):
                db.add(Reminder(
                    user_id=admin.id,
                    schedule="08:00",
                    frequency="daily",
                    message=f"Recordatorio {i}",
                ))
            for i in range(_ADMIN_CHALLENGES):
                db.add(Challenge(
                    user_id=admin.id,
                    name=f"Reto {i}",
                ))

            await db.commit()
            return admin.id, plain.id, last_activity_at

    def auth(self, token: str | None) -> dict:
        return {"Authorization": f"Bearer {token}"} if token else {}

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


# ─────────────────────────────────────────────────────────────────────────────
# Task 4.1 — Auth matrix across all three endpoints (Req 1.1–1.4)
# ─────────────────────────────────────────────────────────────────────────────

def _endpoint_paths(harness) -> list[tuple[str, str]]:
    """The three admin endpoints with a representative concrete path."""
    return [
        ("overview", "/api/admin/overview"),
        ("users", "/api/admin/users"),
        ("user_detail", f"/api/admin/users/{harness.admin_id}"),
    ]


@pytest.mark.parametrize("endpoint_name", ["overview", "users", "user_detail"])
def test_no_token_is_rejected(harness, endpoint_name):
    """No Authorization header → the shared dependency rejects the request with
    401 (or 403) and the handler never runs (Req 1.3)."""
    path = dict(_endpoint_paths(harness))[endpoint_name]
    resp = harness.client.get(path)
    assert resp.status_code in (401, 403), (
        f"{path} without a token returned {resp.status_code}: {resp.text}"
    )


@pytest.mark.parametrize("endpoint_name", ["overview", "users", "user_detail"])
def test_garbage_token_is_rejected_401(harness, endpoint_name):
    """An unparsable bearer token → 401 (invalid JWT) (Req 1.3)."""
    path = dict(_endpoint_paths(harness))[endpoint_name]
    resp = harness.client.get(path, headers=harness.auth("not-a-real-jwt"))
    assert resp.status_code == 401, (
        f"{path} with a garbage token returned {resp.status_code}: {resp.text}"
    )


@pytest.mark.parametrize("endpoint_name", ["overview", "users", "user_detail"])
def test_non_admin_token_is_forbidden_403(harness, endpoint_name):
    """A valid NON-admin JWT → get_current_admin rejects with 403 (Req 1.2)."""
    path = dict(_endpoint_paths(harness))[endpoint_name]
    resp = harness.client.get(path, headers=harness.auth(harness.user_token))
    assert resp.status_code == 403, (
        f"{path} with a non-admin token returned {resp.status_code}: {resp.text}"
    )


@pytest.mark.parametrize("endpoint_name", ["overview", "users", "user_detail"])
def test_admin_token_is_allowed_200(harness, endpoint_name):
    """A valid ADMIN JWT → 200 with data (Req 1.1, 1.4)."""
    path = dict(_endpoint_paths(harness))[endpoint_name]
    resp = harness.client.get(path, headers=harness.auth(harness.admin_token))
    assert resp.status_code == 200, (
        f"{path} with an admin token returned {resp.status_code}: {resp.text}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 4.2 — Single-user, 404, and null-last-activity example tests
# ─────────────────────────────────────────────────────────────────────────────

def test_user_detail_existing_user_returns_expected_fields(harness):
    """GET /users/{id} for the seeded admin returns an AdminUserDetail whose
    fields match the seeded data (Req 4.1, 4.2, 4.3, 4.4)."""
    resp = harness.client.get(
        f"/api/admin/users/{harness.admin_id}",
        headers=harness.auth(harness.admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Summary fields.
    assert body["id"] == harness.admin_id
    assert body["email"] == "admin@example.com"
    assert body["telegram_linked"] is True  # admin has a telegram_chat_id
    assert isinstance(body["created_at"], str) and body["created_at"]

    # Entity counts match the seeded fixtures.
    assert body["activity_count"] == _ADMIN_ACTIVITY_TOTAL
    assert body["goal_count"] == _ADMIN_GOALS
    assert body["reminder_count"] == _ADMIN_REMINDERS
    assert body["challenge_count"] == _ADMIN_CHALLENGES

    # Windowed activity counts: 2 within 7d, all 5 within 30d.
    assert body["activities_7d"] == _ADMIN_ACTIVITIES_WITHIN_7D
    assert body["activities_30d"] == _ADMIN_ACTIVITY_TOTAL

    # last_activity_at is the max timestamp among the admin's activities.
    assert body["last_activity_at"] is not None
    assert body["last_activity_at"] == harness.last_activity_at.isoformat()

    # Privacy by construction: no secret keys leak.
    assert "password_hash" not in body
    assert "telegram_chat_id" not in body


def test_user_detail_nonexistent_id_returns_404(harness):
    """GET /users/{id} for an id that does not exist → 404 with the
    "User not found" detail (Req 4.6)."""
    missing_id = 999999
    resp = harness.client.get(
        f"/api/admin/users/{missing_id}",
        headers=harness.auth(harness.admin_token),
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "User not found"


def test_user_detail_user_without_activities_has_null_last_activity(harness):
    """A user with NO activities reports last_activity_at == null and all
    activity counts == 0 (Req 4.5, 3.9)."""
    resp = harness.client.get(
        f"/api/admin/users/{harness.user_id}",
        headers=harness.auth(harness.admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["id"] == harness.user_id
    assert body["email"] == "user@example.com"
    assert body["telegram_linked"] is False  # no telegram_chat_id

    assert body["last_activity_at"] is None
    assert body["activities_7d"] == 0
    assert body["activities_30d"] == 0
    assert body["activity_count"] == 0
    # This user owns nothing at all.
    assert body["goal_count"] == 0
    assert body["reminder_count"] == 0
    assert body["challenge_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
