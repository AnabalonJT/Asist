"""Property-based tests (Hypothesis) for the per-user list endpoint
``GET /api/admin/users`` of the Admin_Panel (``app/routes/admin.py``,
mounted under ``/api/admin``).

Covers design Properties 3, 4, and 5 (tasks 3.3, 3.4, 3.5):

- Property 3 — the user list is a bijection over users (Req 3.1, 3.9).
- Property 4 — per-user summary fields match their source (Req 3.2, 3.3, 3.4).
- Property 5 — per-user entity counts equal that user's rows, with 0 as the
  grouped-count-map default when the user owns none (Req 3.5, 3.6, 3.7, 3.8).

All three tests share ONE DB harness so the (relatively expensive) in-memory
schema build is paid once per example batch.

Setup mirrors the proven route-level pattern of
``tests/test_food_barcode_routes.py`` and ``tests/test_goal_plan_routes.py``
(there is NO conftest.py): a throwaway FastAPI app mounting ONLY
``admin.router`` at ``/api/admin``, an in-memory async SQLite engine,
``import app.models`` + ``create_all`` to build the full schema,
``app.database.get_db`` overridden to yield the shared session, and a real
ADMIN JWT minted by ``auth_service.create_token(user_id, is_admin=True)``.

Each Hypothesis-generated population is seeded into a FRESH in-memory database
so examples do not bleed into one another, and expected values are computed
INDEPENDENTLY in Python from the generated population (never from the endpoint).

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (the admin router reads users, activities,
# goals, reminders, challenges).
import app.models  # noqa: F401
from app.models.user import User
from app.models.activity import Activity
from app.models.goal import Goal
from app.models.reminder import Reminder
from app.models.challenge import Challenge
from app.routes import admin
from app.services.auth_service import auth_service


# ── Generated-population description ──────────────────────────────────────────
# Each user is described by a plain dict the generator emits; the harness turns
# the description into real rows and the test computes expectations from the SAME
# description, independently of the endpoint response.
#
#   {
#     "telegram_chat_id": int | None,   # drives telegram_linked
#     "activities": int,                # how many Activity rows to seed
#     "goals": int,
#     "reminders": int,
#     "challenges": int,
#   }
#
# Counts intentionally include 0 so the grouped-count-map default (.get(id, 0))
# is exercised (Property 5).

_user_spec = st.fixed_dictionaries(
    {
        # None ~1/3 of the time so both linked and unlinked users appear.
        "telegram_chat_id": st.one_of(
            st.none(),
            st.integers(min_value=1, max_value=2_000_000_000),
        ),
        "activities": st.integers(min_value=0, max_value=4),
        "goals": st.integers(min_value=0, max_value=4),
        "reminders": st.integers(min_value=0, max_value=4),
        "challenges": st.integers(min_value=0, max_value=4),
    }
)

# A population of several users (at least one). telegram_chat_id has a UNIQUE
# constraint, so the harness de-duplicates generated chat ids before seeding.
_population = st.lists(_user_spec, min_size=1, max_size=6)


# ── Harness ──────────────────────────────────────────────────────────────────
class Harness:
    """A throwaway app + in-memory DB. Builds the schema once; ``seed`` wipes and
    repopulates it per Hypothesis example, keeping the same TestClient/session.

    A single ADMIN user is always present (the requester). Generated users are
    added on top of that admin, so the returned list always includes the admin
    plus every generated user.
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
                email="admin@example.com",
                password_hash="x",
                is_admin=True,
            )
            db.add(admin_user)
            await db.flush()
            await db.commit()
            return admin_user.id

    async def _reset_non_admin_rows(self):
        """Delete everything except the admin user so each example starts clean.

        Child entities are removed first to respect FK ordering, then every user
        other than the admin.
        """
        async with self.session_factory() as db:
            from sqlalchemy import delete

            await db.execute(delete(Activity))
            await db.execute(delete(Goal))
            await db.execute(delete(Reminder))
            await db.execute(delete(Challenge))
            await db.execute(delete(User).where(User.id != self.admin_id))
            await db.commit()

    def seed(self, specs: list[dict]) -> dict[int, dict]:
        """Wipe prior non-admin data, seed the given population, and return the
        EXPECTED per-user record keyed by the real user id.

        The expected record is computed here from the generator's description, so
        the test never derives expectations from the endpoint under test. The
        admin user is included with all-zero counts and telegram unlinked.
        """
        return asyncio.run(self._seed(specs))

    async def _seed(self, specs: list[dict]) -> dict[int, dict]:
        await self._reset_non_admin_rows()

        expected: dict[int, dict] = {}
        used_chat_ids: set[int] = set()

        async with self.session_factory() as db:
            # The admin requester: always present, no linked telegram, zero rows.
            expected[self.admin_id] = {
                "email": "admin@example.com",
                "telegram_linked": False,
                "activity_count": 0,
                "goal_count": 0,
                "reminder_count": 0,
                "challenge_count": 0,
            }

            for i, spec in enumerate(specs):
                # telegram_chat_id is UNIQUE; drop collisions to None.
                chat_id = spec["telegram_chat_id"]
                if chat_id is not None and chat_id in used_chat_ids:
                    chat_id = None
                if chat_id is not None:
                    used_chat_ids.add(chat_id)

                user = User(
                    email=f"user{i}@example.com",
                    password_hash="secret-hash",
                    is_admin=False,
                    telegram_chat_id=chat_id,
                )
                db.add(user)
                await db.flush()  # assign user.id

                for _ in range(spec["activities"]):
                    db.add(Activity(
                        user_id=user.id,
                        activity_type="correr",
                        calories=100,
                    ))
                for g in range(spec["goals"]):
                    db.add(Goal(
                        user_id=user.id,
                        activity_type="correr",
                        description=f"meta {g}",
                    ))
                for r in range(spec["reminders"]):
                    db.add(Reminder(
                        user_id=user.id,
                        schedule="08:00",
                        frequency="daily",
                        message=f"recordatorio {r}",
                    ))
                for c in range(spec["challenges"]):
                    db.add(Challenge(
                        user_id=user.id,
                        name=f"reto {c}",
                    ))

                expected[user.id] = {
                    "email": f"user{i}@example.com",
                    "telegram_linked": chat_id is not None,
                    "activity_count": spec["activities"],
                    "goal_count": spec["goals"],
                    "reminder_count": spec["reminders"],
                    "challenge_count": spec["challenges"],
                }

            await db.commit()

        return expected

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def get_users(self):
        resp = self.client.get("/api/admin/users", headers=self.headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def close(self):
        self.client.close()
        asyncio.run(self.engine.dispose())


@pytest.fixture(scope="module")
def harness():
    h = Harness()
    try:
        yield h
    finally:
        h.close()


# ── Property 3: The user list is a bijection over users ───────────────────────
# Feature: admin-panel, Property 3: The user list is a bijection over users
@settings(max_examples=100, deadline=None)
@given(specs=_population)
def test_user_list_is_a_bijection_over_users(harness, specs):
    """GET /users returns exactly one summary per seeded user: the set of returned
    ids equals the set of user ids, with no missing, extra, or duplicate ids.

    Validates: Requirements 3.1, 3.9
    """
    expected = harness.seed(specs)
    body = harness.get_users()

    returned_ids = [row["id"] for row in body]
    expected_ids = set(expected.keys())

    # Exactly one summary per user (no duplicates): count matches the id-set size.
    assert len(returned_ids) == len(expected_ids), (
        f"expected {len(expected_ids)} summaries (1 per user), "
        f"got {len(returned_ids)}: {sorted(returned_ids)}"
    )
    # No duplicate ids in the response.
    assert len(returned_ids) == len(set(returned_ids)), (
        f"duplicate ids in response: {sorted(returned_ids)}"
    )
    # Bijection: the returned id set equals the user id set exactly.
    assert set(returned_ids) == expected_ids, (
        f"id mismatch: missing={expected_ids - set(returned_ids)}, "
        f"extra={set(returned_ids) - expected_ids}"
    )


# ── Property 4: Per-user summary fields match their source ────────────────────
# Feature: admin-panel, Property 4: Per-user summary fields match their source
@settings(max_examples=100, deadline=None)
@given(specs=_population)
def test_per_user_summary_fields_match_source(harness, specs):
    """For each returned summary: id/email match the source user, created_at is a
    non-empty isoformat string (the seeded users always have a created_at), and
    telegram_linked is the derived boolean (True iff telegram_chat_id is not None).
    No raw telegram_chat_id or password_hash key is exposed at any level.

    Validates: Requirements 3.2, 3.3, 3.4
    """
    expected = harness.seed(specs)
    body = harness.get_users()

    by_id = {row["id"]: row for row in body}
    assert set(by_id) == set(expected), "response ids must match seeded users"

    for uid, exp in expected.items():
        row = by_id[uid]
        assert row["id"] == uid
        assert row["email"] == exp["email"]
        # telegram association is surfaced only as the derived boolean.
        assert row["telegram_linked"] == exp["telegram_linked"]
        # created_at is the user's created_at isoformat (seeded via func.now(),
        # so always present) — a non-empty string, not "" and not null.
        assert isinstance(row["created_at"], str)
        assert row["created_at"] != ""

        # Privacy by construction: no secret/raw keys leak into the summary.
        assert "telegram_chat_id" not in row
        assert "password_hash" not in row
        assert "password" not in row


# ── Property 5: Per-user entity counts equal that user's rows ─────────────────
# Feature: admin-panel, Property 5: Per-user entity counts equal that user's rows
@settings(max_examples=100, deadline=None)
@given(specs=_population)
def test_per_user_entity_counts_equal_rows_with_zero_default(harness, specs):
    """For each user, activity/goal/reminder/challenge counts equal the true number
    of that entity owned by the user; a user owning none of an entity reports 0
    (the grouped-count-map default). The admin user, seeded with no rows, reports 0
    for all four counts.

    Validates: Requirements 3.5, 3.6, 3.7, 3.8
    """
    expected = harness.seed(specs)
    body = harness.get_users()

    by_id = {row["id"]: row for row in body}
    assert set(by_id) == set(expected), "response ids must match seeded users"

    for uid, exp in expected.items():
        row = by_id[uid]
        assert row["activity_count"] == exp["activity_count"], (
            f"user {uid} activity_count: "
            f"expected {exp['activity_count']}, got {row['activity_count']}"
        )
        assert row["goal_count"] == exp["goal_count"], (
            f"user {uid} goal_count: "
            f"expected {exp['goal_count']}, got {row['goal_count']}"
        )
        assert row["reminder_count"] == exp["reminder_count"], (
            f"user {uid} reminder_count: "
            f"expected {exp['reminder_count']}, got {row['reminder_count']}"
        )
        assert row["challenge_count"] == exp["challenge_count"], (
            f"user {uid} challenge_count: "
            f"expected {exp['challenge_count']}, got {row['challenge_count']}"
        )

    # Explicit zero-default check: any user the generator gave zero of an entity
    # must report exactly 0 (not null, not missing).
    for uid, exp in expected.items():
        row = by_id[uid]
        for key in ("activity_count", "goal_count", "reminder_count", "challenge_count"):
            if exp[key] == 0:
                assert row[key] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
