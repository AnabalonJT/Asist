"""Property-based tests (Hypothesis) for the single-user detail endpoint
``GET /api/admin/users/{user_id}`` of the Admin_Panel (``app/routes/admin.py``,
mounted under ``/api/admin``) plus a cross-endpoint privacy property.

Covers design Properties 6, 7, 8, and 9 (tasks 3.6, 3.7, 3.8, 3.9):

- Property 6 — detail summary is consistent with the list summary: the shared
  AdminUserSummary fields (``id``, ``email``, ``telegram_linked``, ``created_at``,
  and the four counts) returned by ``GET /users/{id}`` equal that same user's
  entry in ``GET /users`` (Req 4.1).
- Property 7 — detail windowed activity counts are correct: ``activities_7d`` /
  ``activities_30d`` equal the number of that user's activities whose
  ``timestamp`` is within the trailing 7-/30-day window, and ``7d <= 30d``
  (Req 4.2, 4.3).
- Property 8 — last-activity max/null: ``last_activity_at`` equals the ISO string
  of the user's MAX activity timestamp, or ``null`` when the user has no
  activities (Req 4.4, 4.5).
- Property 9 — no secret fields in any admin response: across ``overview``,
  ``users``, and ``users/{id}``, no key named ``password_hash`` / ``password`` /
  ``telegram_chat_id`` (or any other secret/token-ish field) appears anywhere in
  the serialized JSON, recursing into every nested structure (Req 5.1-5.3).

All four tests share ONE DB harness so the (relatively expensive) in-memory
schema build is paid once per example batch.

Setup mirrors the proven route-level harness of
``tests/test_property_admin_overview.py`` and
``tests/test_property_admin_users.py`` (there is NO conftest.py): a throwaway
FastAPI app mounting ONLY ``admin.router`` at ``/api/admin``, an in-memory async
SQLite engine, ``import app.models`` + ``Base.metadata.create_all`` to build the
full schema, ``app.database.get_db`` overridden to yield the shared session, and a
real ADMIN JWT minted by ``auth_service.create_token(user_id, is_admin=True)``.

Each Hypothesis-generated population is seeded into a freshly-reset database (the
admin user is preserved; every non-admin row is wiped) so examples do not bleed
into one another, and expected values are computed INDEPENDENTLY in Python from
the generated population (never from the endpoint under test).

The endpoint computes its windows from ``datetime.utcnow()`` and uses
``Activity.timestamp``; activity timestamps are generated relative to a single
``datetime.utcnow()`` captured per example, with a safety margin around the
7d/30d cutoffs so the sub-second clock drift between seeding and the request
handler cannot flip a boundary row.

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


# ── Generated-population description ──────────────────────────────────────────
# Each user is described by a plain dict the generator emits; the harness turns
# the description into real rows and the tests compute expectations from the SAME
# description, independently of the endpoint response.
#
#   {
#     "linked": bool,                   # drives telegram_linked / telegram_chat_id
#     "goals": int,
#     "reminders": int,
#     "challenges": int,
#     "activity_offsets": list[int],    # per-activity "days before utcnow()"
#   }
#
# Day offsets straddle the 7d and 30d cutoffs with a margin so boundary rows are
# unambiguous: inside-7d (and thus inside-30d), inside-30d-only, and outside-30d.
# An empty activity_offsets list yields a user with NO activities, which exercises
# the null last_activity_at branch (Property 8 / Req 4.5).
_DAY_OFFSETS = st.sampled_from([0, 1, 3, 6, 8, 15, 29, 31, 45, 100])

_user_spec = st.fixed_dictionaries(
    {
        "linked": st.booleans(),
        "goals": st.integers(min_value=0, max_value=3),
        "reminders": st.integers(min_value=0, max_value=3),
        "challenges": st.integers(min_value=0, max_value=3),
        "activity_offsets": st.lists(_DAY_OFFSETS, max_size=5),
    }
)

# A population of at least one non-admin user (so there is always a user to fetch
# detail for besides the admin), up to a handful.
_population = st.lists(_user_spec, min_size=1, max_size=6)


# ── Harness ──────────────────────────────────────────────────────────────────
class Harness:
    """A throwaway app + in-memory DB. Builds the schema once; ``seed`` wipes the
    non-admin rows and repopulates them per Hypothesis example, keeping the same
    TestClient/session.

    A single ADMIN user is always present (the requester). Generated users are
    added on top of that admin.
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
            await db.execute(delete(Activity))
            await db.execute(delete(Goal))
            await db.execute(delete(Reminder))
            await db.execute(delete(Challenge))
            await db.execute(delete(User).where(User.id != self.admin_id))
            await db.commit()

    def seed(self, specs: list[dict], now: datetime) -> dict[int, dict]:
        """Wipe prior non-admin data, seed the given population relative to ``now``,
        and return the EXPECTED per-user record keyed by the real user id.

        Expectations are computed here from the generator's description, so the
        tests never derive expectations from the endpoint under test. The admin
        user is included with all-zero counts, telegram unlinked, and no
        activities (null last_activity_at).
        """
        return asyncio.run(self._seed(specs, now))

    async def _seed(self, specs: list[dict], now: datetime) -> dict[int, dict]:
        await self._reset_non_admin_rows()

        expected: dict[int, dict] = {}
        next_chat_id = 1000

        async with self.session_factory() as db:
            # The admin requester: always present, no linked telegram, zero rows,
            # no activities => null last_activity_at.
            expected[self.admin_id] = {
                "email": "admin@example.com",
                "telegram_linked": False,
                "activity_count": 0,
                "goal_count": 0,
                "reminder_count": 0,
                "challenge_count": 0,
                "activities_7d": 0,
                "activities_30d": 0,
                "last_activity_at": None,
            }

            for i, spec in enumerate(specs):
                chat_id = None
                if spec["linked"]:
                    chat_id = next_chat_id
                    next_chat_id += 1

                user = User(
                    email=f"user{i}@example.com",
                    password_hash="secret-hash",
                    is_admin=False,
                    telegram_chat_id=chat_id,
                )
                db.add(user)
                await db.flush()  # assign user.id

                # Seed activities at explicit timestamps relative to ``now``.
                activity_timestamps: list[datetime] = []
                for off in spec["activity_offsets"]:
                    ts = now - timedelta(days=off)
                    activity_timestamps.append(ts)
                    db.add(Activity(
                        user_id=user.id,
                        activity_type="correr",
                        calories=100,
                        timestamp=ts,
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

                # Compute expected windowed counts and max timestamp purely from
                # the generated offsets. The margin baked into _DAY_OFFSETS keeps
                # these classifications stable against sub-second clock drift
                # between ``now`` here and ``utcnow()`` inside the handler.
                activities_7d = sum(1 for off in spec["activity_offsets"] if off <= 7)
                activities_30d = sum(1 for off in spec["activity_offsets"] if off <= 30)
                last_ts = max(activity_timestamps) if activity_timestamps else None

                expected[user.id] = {
                    "email": f"user{i}@example.com",
                    "telegram_linked": chat_id is not None,
                    "activity_count": len(spec["activity_offsets"]),
                    "goal_count": spec["goals"],
                    "reminder_count": spec["reminders"],
                    "challenge_count": spec["challenges"],
                    "activities_7d": activities_7d,
                    "activities_30d": activities_30d,
                    "last_activity_at": last_ts.isoformat() if last_ts else None,
                }

            await db.commit()

        return expected

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def get_overview(self):
        resp = self.client.get("/api/admin/overview", headers=self.headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def get_users(self):
        resp = self.client.get("/api/admin/users", headers=self.headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def get_user_detail(self, user_id: int):
        resp = self.client.get(f"/api/admin/users/{user_id}", headers=self.headers)
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


# Shared summary keys present on both AdminUserSummary and AdminUserDetail.
_SUMMARY_KEYS = (
    "id",
    "email",
    "telegram_linked",
    "created_at",
    "activity_count",
    "goal_count",
    "reminder_count",
    "challenge_count",
)

# Keys that must NEVER appear anywhere in any admin response (Property 9).
_FORBIDDEN_KEYS = {
    "password_hash",
    "password",
    "telegram_chat_id",
    "token",
    "access_token",
    "jwt",
    "secret",
    "hashed_password",
}


def _iter_keys(obj):
    """Yield every dict key found anywhere in a nested JSON-like structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _iter_keys(item)


# ── Property 6: Detail summary is consistent with the list summary ────────────
# Feature: admin-panel, Property 6: Detail summary is consistent with the list summary
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(specs=_population)
def test_detail_summary_consistent_with_list_summary(harness, specs):
    """For every seeded user, the shared AdminUserSummary fields returned by
    GET /users/{id} equal that same user's entry in GET /users.

    Validates: Requirements 4.1
    """
    now = datetime.utcnow()
    expected = harness.seed(specs, now)

    list_body = harness.get_users()
    list_by_id = {row["id"]: row for row in list_body}
    assert set(list_by_id) == set(expected), "list ids must match seeded users"

    for uid in expected:
        detail = harness.get_user_detail(uid)
        list_row = list_by_id[uid]
        for key in _SUMMARY_KEYS:
            assert key in detail, f"detail for user {uid} missing summary key {key!r}"
            assert key in list_row, f"list for user {uid} missing summary key {key!r}"
            assert detail[key] == list_row[key], (
                f"user {uid} field {key!r} differs between detail and list: "
                f"detail={detail[key]!r} list={list_row[key]!r}"
            )


# ── Property 7: Detail windowed activity counts are correct ───────────────────
# Feature: admin-panel, Property 7: Detail windowed activity counts are correct
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(specs=_population)
def test_detail_windowed_activity_counts(harness, specs):
    """For every seeded user, AdminUserDetail.activities_7d / activities_30d equal
    the number of that user's activities within the trailing 7-/30-day window, and
    activities_7d <= activities_30d.

    Validates: Requirements 4.2, 4.3
    """
    now = datetime.utcnow()
    expected = harness.seed(specs, now)

    for uid, exp in expected.items():
        detail = harness.get_user_detail(uid)
        assert detail["activities_7d"] == exp["activities_7d"], (
            f"user {uid} activities_7d: "
            f"expected {exp['activities_7d']}, got {detail['activities_7d']}"
        )
        assert detail["activities_30d"] == exp["activities_30d"], (
            f"user {uid} activities_30d: "
            f"expected {exp['activities_30d']}, got {detail['activities_30d']}"
        )
        # The 7-day window is a subset of the 30-day window.
        assert detail["activities_7d"] <= detail["activities_30d"], (
            f"user {uid}: activities_7d ({detail['activities_7d']}) must be "
            f"<= activities_30d ({detail['activities_30d']})"
        )


# ── Property 8: Last activity timestamp is the max, or null when none ─────────
# Feature: admin-panel, Property 8: Last activity timestamp is the max, or null when none
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(specs=_population)
def test_last_activity_is_max_or_null(harness, specs):
    """For every seeded user, AdminUserDetail.last_activity_at equals the ISO
    string of that user's MAX activity timestamp, or null when the user owns no
    activities.

    Validates: Requirements 4.4, 4.5
    """
    now = datetime.utcnow()
    expected = harness.seed(specs, now)

    for uid, exp in expected.items():
        detail = harness.get_user_detail(uid)
        if exp["last_activity_at"] is None:
            # No activities => null, and the activity_count agrees it is zero.
            assert detail["last_activity_at"] is None, (
                f"user {uid} has no activities; last_activity_at must be null, "
                f"got {detail['last_activity_at']!r}"
            )
            assert exp["activity_count"] == 0
        else:
            assert detail["last_activity_at"] == exp["last_activity_at"], (
                f"user {uid} last_activity_at: expected the max timestamp "
                f"{exp['last_activity_at']!r}, got {detail['last_activity_at']!r}"
            )


# ── Property 9: No secret fields appear in any admin response ─────────────────
# Feature: admin-panel, Property 9: No secret fields appear in any admin response
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(specs=_population)
def test_no_secret_fields_in_any_admin_response(harness, specs):
    """Across the overview, the users list, and every user-detail response, no key
    named password_hash / password / telegram_chat_id (or other secret/token-ish
    field) appears anywhere in the serialized JSON, recursing into nested
    structures. Users are seeded with a real password_hash and (for linked users)
    a telegram_chat_id so the privacy filtering is genuinely exercised.

    Validates: Requirements 5.1, 5.2, 5.3
    """
    now = datetime.utcnow()
    expected = harness.seed(specs, now)

    responses = [
        ("overview", harness.get_overview()),
        ("users", harness.get_users()),
    ]
    for uid in expected:
        responses.append((f"users/{uid}", harness.get_user_detail(uid)))

    for label, payload in responses:
        keys = {str(k).lower() for k in _iter_keys(payload)}
        leaked = keys & _FORBIDDEN_KEYS
        assert not leaked, (
            f"admin response {label!r} leaked forbidden secret key(s): "
            f"{sorted(leaked)}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
