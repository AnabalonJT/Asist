"""Example-based integration tests for the Goal_Wizard REST endpoints
(``app/routes/goal_plan.py``, mounted under ``/api/goal-plan``).

These are EXAMPLE-BASED tests (not property tests). They verify, with concrete
representative inputs:

1. Every ``/api/goal-plan/*`` endpoint rejects a request with no bearer token
   (401/403), exposing no data (Req 1.3, 12.1, 12.2).
2. ``PUT /profile``, ``PUT /goal``, ``PUT /equipment`` and ``PUT /training-days``
   accept a valid body (200 + value persists, verified via a follow-up read) and
   reject an invalid body (400 with a Spanish ``detail``) while leaving the
   previously-persisted state intact (Req 2.2, 2.3, 3.2, 3.3, 4.2, 4.3, 8.2, 8.3).
3. ``GET /state`` positions ``step`` at the first incomplete wizard step for
   representative states (Req 1.6).
4. ``GET /phases`` with no active plan returns 200 with a Spanish ``message``
   (Req 11.3).

Setup mirrors the proven route-level pattern used by
``tests/test_property_goal_wizard_privacy.py`` and
``tests/test_property_goal_wizard_disclaimer.py`` (there is NO conftest.py):
a throwaway FastAPI app mounting ONLY ``goal_plan.router`` at ``/api/goal-plan``,
an in-memory async SQLite engine, ``import app.models`` + ``create_all`` to build
the full schema, ``app.database.get_db`` overridden to yield the shared session,
and a real JWT minted by ``app.services.auth_service.auth_service.create_token``.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
from datetime import date, timedelta

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
# create_all builds the full schema (FKs from fitness_profiles / diet_phase_plans
# / workout_plans point at users).
import app.models  # noqa: F401
from app.models.user import User
from app.routes import goal_plan
from app.services.auth_service import auth_service


# ── Representative valid bodies ──────────────────────────────────────────────
_VALID_PROFILE = {
    "weight_kg": 80.0,
    "height_cm": 180.0,
    "age": 30,
    "sex": "male",
    "level": "principiante",
    "days_per_week": 4,
    "minutes_per_session": 60,
}


def _valid_goal() -> dict:
    """A valid weight-target goal with a target date safely in the future."""
    return {
        "target_weight_kg": 75.0,
        "target_date": (date.today() + timedelta(weeks=12)).isoformat(),
    }


_VALID_EQUIPMENT = {"equipment": ["mancuernas", "banco"]}
_VALID_TRAINING_DAYS = {"days_per_week": 5}


# Every protected endpoint with a representative request (method, path, json).
# Bodies here only need to be shape-valid enough to reach the auth dependency;
# auth runs before the handler body, so unauthenticated calls never touch them.
_ALL_ENDPOINTS = [
    ("GET", "/api/goal-plan/state", None),
    ("PUT", "/api/goal-plan/profile", _VALID_PROFILE),
    ("PUT", "/api/goal-plan/goal", _valid_goal()),
    ("PUT", "/api/goal-plan/equipment", _VALID_EQUIPMENT),
    ("POST", "/api/goal-plan/phases/derive", None),
    ("GET", "/api/goal-plan/phases", None),
    ("PUT", "/api/goal-plan/training-days", _VALID_TRAINING_DAYS),
    ("POST", "/api/goal-plan/routine/generate", None),
    ("POST", "/api/goal-plan/routine/generate-chunk",
     {"chunk_index": 0, "chunk_count": 1}),
    ("PUT", "/api/goal-plan/routine", {"structure": []}),
    ("PUT", "/api/goal-plan/phases/active/targets",
     {"kcal": 2000.0, "protein_g": 150.0, "fat_g": 60.0, "carbs_g": 220.0}),
    ("POST", "/api/goal-plan/weight",
     {"weight_kg": 80.0, "entry_date": date.today().isoformat()}),
]


# ── Harness ──────────────────────────────────────────────────────────────────
class Harness:
    """A throwaway app + in-memory DB for one test. Builds the schema, seeds a
    single non-admin user, mints a real JWT, and exposes a TestClient wired to the
    goal_plan router with ``get_db`` overridden to the shared session."""

    def __init__(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        asyncio.run(self._create_schema())
        self.user_id = asyncio.run(self._seed_user())
        self.token = auth_service.create_token(self.user_id, is_admin=False)

        app = FastAPI()
        app.include_router(goal_plan.router, prefix="/api/goal-plan")
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

    async def _seed_user(self) -> int:
        async with self.session_factory() as db:
            user = User(email="wizard@example.com", password_hash="x",
                        is_admin=False)
            db.add(user)
            await db.flush()
            await db.commit()
            return user.id

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


# ── 1. Auth required on every endpoint (Req 1.3, 12.1, 12.2) ─────────────────
@pytest.mark.parametrize("method,path,body", _ALL_ENDPOINTS)
def test_endpoints_require_auth(harness, method, path, body):
    """Each ``/api/goal-plan/*`` endpoint rejects an unauthenticated request with
    401 (or 403) and never runs its handler, exposing no data."""
    resp = harness.client.request(method, path, json=body)
    assert resp.status_code in (401, 403), (
        f"{method} {path} without a token returned {resp.status_code}: {resp.text}"
    )


# ── 2. PUT endpoints: valid persists, invalid rejected + state intact ─────────
def test_put_profile_valid_persists_and_invalid_rejected(harness):
    """A valid profile persists (verified via GET /state); an invalid profile
    (age out of range) → 400 Spanish detail and the prior profile is intact."""
    # Valid → 200 and persisted.
    resp = harness.client.put(
        "/api/goal-plan/profile", json=_VALID_PROFILE, headers=harness.headers
    )
    assert resp.status_code == 200, resp.text
    state = harness.client.get(
        "/api/goal-plan/state", headers=harness.headers
    ).json()
    assert state["weight_kg"] == _VALID_PROFILE["weight_kg"]
    assert state["height_cm"] == _VALID_PROFILE["height_cm"]
    assert state["age"] == _VALID_PROFILE["age"]
    assert state["level"] == _VALID_PROFILE["level"]
    assert state["profile_complete"] is True

    # Invalid (age = 5, below the 13..100 range) → 400 with Spanish detail.
    bad = {**_VALID_PROFILE, "age": 5}
    resp = harness.client.put(
        "/api/goal-plan/profile", json=bad, headers=harness.headers
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and detail.strip()
    assert "edad" in detail.lower()

    # Prior state intact: the previously-persisted profile is unchanged.
    state_after = harness.client.get(
        "/api/goal-plan/state", headers=harness.headers
    ).json()
    assert state_after["age"] == _VALID_PROFILE["age"]
    assert state_after["weight_kg"] == _VALID_PROFILE["weight_kg"]


def test_put_goal_valid_persists_and_invalid_rejected(harness):
    """With a profile in place, a valid goal persists (GET /state reflects it);
    an invalid goal (target date in the past) → 400 Spanish detail and the prior
    goal is intact."""
    harness.client.put(
        "/api/goal-plan/profile", json=_VALID_PROFILE, headers=harness.headers
    )

    goal = _valid_goal()
    resp = harness.client.put(
        "/api/goal-plan/goal", json=goal, headers=harness.headers
    )
    assert resp.status_code == 200, resp.text
    state = harness.client.get(
        "/api/goal-plan/state", headers=harness.headers
    ).json()
    assert state["has_goal"] is True
    assert state["target_weight_kg"] == goal["target_weight_kg"]
    assert state["target_date"] == goal["target_date"]

    # Invalid: target date in the past → 400 Spanish detail.
    bad = {
        "target_weight_kg": 70.0,
        "target_date": (date.today() - timedelta(days=1)).isoformat(),
    }
    resp = harness.client.put(
        "/api/goal-plan/goal", json=bad, headers=harness.headers
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and detail.strip()
    assert "fecha" in detail.lower()

    # Prior goal intact.
    state_after = harness.client.get(
        "/api/goal-plan/state", headers=harness.headers
    ).json()
    assert state_after["target_weight_kg"] == goal["target_weight_kg"]
    assert state_after["target_date"] == goal["target_date"]


def test_put_equipment_valid_persists_and_invalid_rejected(harness):
    """With a profile in place, valid equipment persists (GET /state reflects it);
    an unknown equipment item → 400 Spanish detail and the prior equipment is
    intact."""
    harness.client.put(
        "/api/goal-plan/profile", json=_VALID_PROFILE, headers=harness.headers
    )

    resp = harness.client.put(
        "/api/goal-plan/equipment", json=_VALID_EQUIPMENT, headers=harness.headers
    )
    assert resp.status_code == 200, resp.text
    assert sorted(resp.json()["equipment"]) == sorted(
        _VALID_EQUIPMENT["equipment"]
    )
    state = harness.client.get(
        "/api/goal-plan/state", headers=harness.headers
    ).json()
    assert sorted(state["equipment"]) == sorted(_VALID_EQUIPMENT["equipment"])

    # Invalid: an item not in the catalog → 400 Spanish detail.
    resp = harness.client.put(
        "/api/goal-plan/equipment",
        json={"equipment": ["nave espacial"]},
        headers=harness.headers,
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and detail.strip()
    assert "catálogo" in detail.lower()

    # Prior equipment intact.
    state_after = harness.client.get(
        "/api/goal-plan/state", headers=harness.headers
    ).json()
    assert sorted(state_after["equipment"]) == sorted(
        _VALID_EQUIPMENT["equipment"]
    )


def test_put_training_days_valid_persists_and_invalid_rejected(harness):
    """With a profile in place, a valid days_per_week persists (GET /state
    reflects it); an out-of-range value → 400 Spanish detail and the prior value
    is intact."""
    harness.client.put(
        "/api/goal-plan/profile", json=_VALID_PROFILE, headers=harness.headers
    )

    resp = harness.client.put(
        "/api/goal-plan/training-days",
        json=_VALID_TRAINING_DAYS,
        headers=harness.headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["days_per_week"] == _VALID_TRAINING_DAYS["days_per_week"]
    state = harness.client.get(
        "/api/goal-plan/state", headers=harness.headers
    ).json()
    assert state["days_per_week"] == _VALID_TRAINING_DAYS["days_per_week"]

    # Invalid: 0 days (out of the 1..7 range) → 400 Spanish detail.
    resp = harness.client.put(
        "/api/goal-plan/training-days",
        json={"days_per_week": 0},
        headers=harness.headers,
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and detail.strip()
    assert "entrenamiento" in detail.lower()

    # Prior value intact.
    state_after = harness.client.get(
        "/api/goal-plan/state", headers=harness.headers
    ).json()
    assert state_after["days_per_week"] == _VALID_TRAINING_DAYS["days_per_week"]


# ── 3. GET /state positions at the first incomplete step (Req 1.6) ───────────
def test_state_positions_at_profile_when_empty(harness):
    """A brand-new user with no profile is positioned at the 'profile' step."""
    resp = harness.client.get("/api/goal-plan/state", headers=harness.headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["step"] == "profile"
    assert body["profile_complete"] is False
    assert body["has_goal"] is False


def test_state_positions_at_goal_after_profile(harness):
    """With a complete profile but no goal, the state is positioned at 'goal'."""
    harness.client.put(
        "/api/goal-plan/profile", json=_VALID_PROFILE, headers=harness.headers
    )
    body = harness.client.get(
        "/api/goal-plan/state", headers=harness.headers
    ).json()
    assert body["step"] == "goal"
    assert body["profile_complete"] is True
    assert body["has_goal"] is False


def test_state_positions_at_equipment_after_goal(harness):
    """With a complete profile + goal but no equipment, the state is positioned at
    'equipment'."""
    harness.client.put(
        "/api/goal-plan/profile", json=_VALID_PROFILE, headers=harness.headers
    )
    harness.client.put(
        "/api/goal-plan/goal", json=_valid_goal(), headers=harness.headers
    )
    body = harness.client.get(
        "/api/goal-plan/state", headers=harness.headers
    ).json()
    assert body["step"] == "equipment"
    assert body["has_goal"] is True


def test_state_positions_at_diet_after_equipment(harness):
    """With profile + goal + equipment but no derived phase plan, the state is
    positioned at 'diet'."""
    harness.client.put(
        "/api/goal-plan/profile", json=_VALID_PROFILE, headers=harness.headers
    )
    harness.client.put(
        "/api/goal-plan/goal", json=_valid_goal(), headers=harness.headers
    )
    harness.client.put(
        "/api/goal-plan/equipment", json=_VALID_EQUIPMENT, headers=harness.headers
    )
    body = harness.client.get(
        "/api/goal-plan/state", headers=harness.headers
    ).json()
    assert body["step"] == "diet"
    assert body["has_plan"] is False


# ── 4. GET /phases with no active plan → Spanish message (Req 11.3) ──────────
def test_get_phases_without_plan_returns_spanish_message(harness):
    """With no active phase plan, GET /phases returns 200 and a non-empty Spanish
    message instead of an error."""
    resp = harness.client.get("/api/goal-plan/phases", headers=harness.headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "message" in body
    message = body["message"]
    assert isinstance(message, str) and message.strip()
    assert "plan de fases" in message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
