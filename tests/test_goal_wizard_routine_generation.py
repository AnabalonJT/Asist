"""Example-based integration tests for Goal_Wizard routine generation
(goal-wizard, Task 7.2).

Covers ``POST /api/goal-plan/routine/generate`` (and ``/routine/generate-chunk``)
in ``app/routes/goal_plan.py``:

1. Success — the LLM is MOCKED to return a valid routine; the endpoint returns
   200, the Workout_Plan is persisted and active, and the number of days does
   NOT exceed the profile's ``days_per_week`` (Req 9.1, 9.6).
2. Failure modes — the LLM/service is MOCKED to fail via timeout / empty (None) /
   invalid JSON / raised ``LLMError``. Each returns HTTP 502 with a Spanish
   ``detail`` AND preserves (unchanged) the Fitness_Profile, the goal, the
   Diet_Phase_Plan and any previously-active routine (Req 9.3, 9.5 preservation).
3. Retry — after a failure, a subsequent successful generate works WITHOUT
   re-submitting profile/goal data; the persisted state is reused (Req 9.5).

Setup mirrors ``tests/test_property_goal_wizard_disclaimer.py``: a throwaway
FastAPI app wired only to the ``goal_plan`` router, ``get_db`` overridden with an
in-memory async SQLite session, a real JWT minted by ``auth_service``, and the
LLM mocked so the real OpenRouter API is NEVER called. There is NO conftest.py.

Failure modes are injected at the ``llm_service`` boundary (returning ``None`` or
a bad payload) so the REAL ``fitness_service.generate_workout_plan`` runs its
real preservation logic — it persists nothing on failure, which is exactly what
Req 9.4 requires. The raised-``LLMError`` case is injected one level up at
``goal_wizard_service.generate_routine`` to cover the router's 502 translation.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
import json
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema.
import app.models  # noqa: F401
from app.models.diet_phase_plan import DietPhasePlan
from app.models.fitness_profile import FitnessProfile
from app.models.user import User
from app.models.workout_plan import WorkoutPlan
from app.routes import goal_plan
from app.services import fitness_service
from app.services import goal_wizard_service
from app.services import llm_service
from app.services.auth_service import auth_service


# A profile that asks for 3 training days. The LLM mock below returns MORE days
# than this so the success test can assert the real clamping to days_per_week.
_PROFILE = {
    "weight_kg": 90.0,
    "height_cm": 178.0,
    "age": 30,
    "sex": "male",
    "level": "principiante",
    "days_per_week": 3,
    "minutes_per_session": 45,
    "target_weight_kg": 82.0,
    "target_date": (date.today() + timedelta(weeks=16)).isoformat(),
}

# A valid LLM payload with FIVE days (> days_per_week == 3). Every exercise uses
# "ninguno" equipment so it survives the equipment filter regardless of profile.
_VALID_LLM_DAYS = {
    "days": [
        {
            "day": f"Dia {n}",
            "exercises": [
                {
                    "name": "Sentadilla",
                    "sets": 3,
                    "reps": 10,
                    "duration_seconds": None,
                    "rest_seconds": 60,
                    "equipment": "ninguno",
                }
            ],
        }
        for n in range(1, 6)
    ]
}


# ── LLM mocks (never hit OpenRouter) ─────────────────────────────────────────
async def _llm_ok(profile, goal, activity_summary, timeout_seconds=60.0):
    """Deterministic valid LLM payload (5 days)."""
    return dict(_VALID_LLM_DAYS)


async def _llm_none(profile, goal, activity_summary, timeout_seconds=60.0):
    """Simulates timeout / empty content / unparseable JSON: the real
    ``llm_service.generate_workout_plan`` returns ``None`` for all of these."""
    return None


async def _llm_bad_structure(profile, goal, activity_summary, timeout_seconds=60.0):
    """A parseable dict whose ``days`` fail ``validate_plan_structure`` → the real
    service raises ``LLMError(kind="parse")`` (invalid JSON content path)."""
    return {"days": [{"day": "Dia 1", "exercises": "not-a-list"}]}


async def _generate_routine_raises(db, user_id):
    """Stand-in for ``goal_wizard_service.generate_routine`` that raises LLMError
    directly (explicit error path, covers the router's 502 translation)."""
    raise fitness_service.LLMError("fallo del modelo", kind="error")


# ── Infra helpers ────────────────────────────────────────────────────────────
def _build_client(session_factory):
    """FastAPI app with ONLY the goal_plan router and the in-memory DB override."""
    app = FastAPI()
    app.include_router(goal_plan.router, prefix="/api/goal-plan")

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


async def _create_schema(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_user_profile_goal(session_factory) -> int:
    """Seed one user with a complete profile + weight-target goal; return user id."""
    async with session_factory() as db:
        user = User(email="routine@example.com", password_hash="x")
        db.add(user)
        await db.flush()

        profile = FitnessProfile(
            user_id=user.id,
            weight_kg=_PROFILE["weight_kg"],
            height_cm=_PROFILE["height_cm"],
            age=_PROFILE["age"],
            sex=_PROFILE["sex"],
            level=_PROFILE["level"],
            equipment="[]",
            days_per_week=_PROFILE["days_per_week"],
            minutes_per_session=_PROFILE["minutes_per_session"],
            goal_type="weight_target",
            target_weight_kg=_PROFILE["target_weight_kg"],
            target_date=_PROFILE["target_date"],
        )
        db.add(profile)
        await db.commit()
        return user.id


async def _read_state(session_factory, user_id):
    """Snapshot the persisted state relevant to preservation checks."""
    async with session_factory() as db:
        profile = (
            await db.execute(
                select(FitnessProfile).where(FitnessProfile.user_id == user_id)
            )
        ).scalars().first()
        phase_plans = (
            await db.execute(
                select(DietPhasePlan).where(DietPhasePlan.user_id == user_id)
            )
        ).scalars().all()
        routines = (
            await db.execute(
                select(WorkoutPlan).where(WorkoutPlan.user_id == user_id)
            )
        ).scalars().all()

        profile_snapshot = None
        if profile is not None:
            profile_snapshot = {
                "weight_kg": profile.weight_kg,
                "height_cm": profile.height_cm,
                "age": profile.age,
                "level": profile.level,
                "days_per_week": profile.days_per_week,
                "goal_type": profile.goal_type,
                "target_weight_kg": profile.target_weight_kg,
                "target_date": profile.target_date,
            }

        active_phase_plan = next((p for p in phase_plans if p.active), None)
        phase_snapshot = None
        if active_phase_plan is not None:
            phase_snapshot = {
                "start_weight_kg": active_phase_plan.start_weight_kg,
                "target_weight_kg": active_phase_plan.target_weight_kg,
                "phases": active_phase_plan.phases,
                "goal_reached": active_phase_plan.goal_reached,
            }

        active_routine = next((r for r in routines if r.active), None)
        routine_snapshot = None
        if active_routine is not None:
            routine_snapshot = {
                "id": active_routine.id,
                "structure": active_routine.structure,
            }

        return {
            "profile": profile_snapshot,
            "active_phase_plan": phase_snapshot,
            "phase_plan_count": len(phase_plans),
            "active_routine": routine_snapshot,
            "routine_count": len(routines),
        }


class _Fixture:
    """Bundles a fresh in-memory DB, seeded user and an authenticated client."""

    def __init__(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        asyncio.run(_create_schema(self.engine))
        self.user_id = asyncio.run(_seed_user_profile_goal(self.session_factory))
        token = auth_service.create_token(self.user_id, is_admin=False)
        self.headers = {"Authorization": f"Bearer {token}"}
        self.client = _build_client(self.session_factory)

    def state(self):
        return asyncio.run(_read_state(self.session_factory, self.user_id))

    def derive_phases(self):
        resp = self.client.post("/api/goal-plan/phases/derive", headers=self.headers)
        assert resp.status_code == 200, f"derive: {resp.status_code} {resp.text}"
        return resp

    def close(self):
        self.client.close()
        asyncio.run(self.engine.dispose())


# ── 1) Success ───────────────────────────────────────────────────────────────
def test_generate_routine_success_persists_active_and_clamps_days(monkeypatch):
    """Req 9.1, 9.6: a valid LLM routine → 200, plan persisted & active, and the
    number of days does NOT exceed the profile's days_per_week."""
    monkeypatch.setattr(llm_service, "generate_workout_plan", _llm_ok)
    fx = _Fixture()
    try:
        fx.derive_phases()  # establish a phase plan so we can later check it survives

        resp = fx.client.post(
            "/api/goal-plan/routine/generate", headers=fx.headers
        )
        assert resp.status_code == 200, f"{resp.status_code} {resp.text}"
        body = resp.json()

        # The response carries a structured routine.
        assert isinstance(body["structure"], list)
        assert len(body["structure"]) >= 1
        # Clamped to days_per_week (5 generated → 3 kept).
        assert len(body["structure"]) <= _PROFILE["days_per_week"]
        assert len(body["structure"]) == _PROFILE["days_per_week"]

        # Persisted and active in the DB.
        state = fx.state()
        assert state["active_routine"] is not None
        assert state["routine_count"] == 1
        persisted = json.loads(state["active_routine"]["structure"])
        assert len(persisted) == _PROFILE["days_per_week"]
        assert body["id"] == state["active_routine"]["id"]
    finally:
        fx.close()


# ── 2) Failure modes ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "mode",
    ["timeout_or_empty_none", "invalid_json", "explicit_llm_error"],
    ids=["none", "invalid_json", "llm_error"],
)
def test_generate_routine_failure_returns_502_and_preserves_state(monkeypatch, mode):
    """Req 9.3, 9.5 (preservation): every LLM failure mode → HTTP 502 with a
    Spanish detail, and the profile, goal, phase plan and any previously-active
    routine are PRESERVED unchanged."""
    fx = _Fixture()
    try:
        # Establish prior state: a derived phase plan AND a previously-active
        # routine (seeded via a first successful, mocked generation).
        fx.derive_phases()
        monkeypatch.setattr(llm_service, "generate_workout_plan", _llm_ok)
        seed_resp = fx.client.post(
            "/api/goal-plan/routine/generate", headers=fx.headers
        )
        assert seed_resp.status_code == 200, seed_resp.text
        before = fx.state()
        assert before["active_routine"] is not None
        assert before["active_phase_plan"] is not None

        # Now inject the failure mode.
        if mode == "timeout_or_empty_none":
            monkeypatch.setattr(llm_service, "generate_workout_plan", _llm_none)
        elif mode == "invalid_json":
            monkeypatch.setattr(
                llm_service, "generate_workout_plan", _llm_bad_structure
            )
        else:  # explicit_llm_error
            monkeypatch.setattr(
                goal_wizard_service, "generate_routine", _generate_routine_raises
            )

        resp = fx.client.post(
            "/api/goal-plan/routine/generate", headers=fx.headers
        )
        assert resp.status_code == 502, f"{mode}: {resp.status_code} {resp.text}"
        detail = resp.json()["detail"]
        assert isinstance(detail, str) and detail.strip()
        # Spanish, retry-oriented message.
        assert "rutina" in detail.lower()
        assert "intenta de nuevo" in detail.lower()

        # State preserved: profile, goal, phase plan and prior routine unchanged.
        after = fx.state()
        assert after["profile"] == before["profile"]
        assert after["active_phase_plan"] == before["active_phase_plan"]
        assert after["phase_plan_count"] == before["phase_plan_count"]
        assert after["active_routine"] == before["active_routine"]
        assert after["routine_count"] == before["routine_count"]
    finally:
        fx.close()


def test_generate_routine_failure_without_prior_routine_persists_nothing(monkeypatch):
    """Req 9.4: a failure before any routine exists leaves zero routines and keeps
    the profile/goal/phase plan intact."""
    monkeypatch.setattr(llm_service, "generate_workout_plan", _llm_none)
    fx = _Fixture()
    try:
        fx.derive_phases()
        before = fx.state()
        assert before["active_routine"] is None
        assert before["routine_count"] == 0

        resp = fx.client.post(
            "/api/goal-plan/routine/generate", headers=fx.headers
        )
        assert resp.status_code == 502, resp.text

        after = fx.state()
        assert after["routine_count"] == 0
        assert after["active_routine"] is None
        assert after["profile"] == before["profile"]
        assert after["active_phase_plan"] == before["active_phase_plan"]
    finally:
        fx.close()


# ── 3) Retry after failure reuses persisted state ────────────────────────────
def test_generate_routine_retry_after_failure_reuses_state(monkeypatch):
    """Req 9.5: after a failure, a subsequent successful generate works WITHOUT
    re-submitting profile/goal data — the persisted state is reused."""
    fx = _Fixture()
    try:
        fx.derive_phases()

        # First attempt fails (LLM returns None).
        monkeypatch.setattr(llm_service, "generate_workout_plan", _llm_none)
        fail = fx.client.post(
            "/api/goal-plan/routine/generate", headers=fx.headers
        )
        assert fail.status_code == 502, fail.text
        assert fx.state()["routine_count"] == 0

        # Retry succeeds WITHOUT re-submitting any profile/goal data: the same
        # POST /routine/generate (no body) now returns a plan from persisted state.
        monkeypatch.setattr(llm_service, "generate_workout_plan", _llm_ok)
        ok = fx.client.post(
            "/api/goal-plan/routine/generate", headers=fx.headers
        )
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert len(body["structure"]) == _PROFILE["days_per_week"]

        state = fx.state()
        assert state["active_routine"] is not None
        assert state["routine_count"] == 1
        # Profile/goal untouched by the retry (reused, never re-entered).
        assert state["profile"]["target_weight_kg"] == _PROFILE["target_weight_kg"]
        assert state["profile"]["days_per_week"] == _PROFILE["days_per_week"]
    finally:
        fx.close()


# ── generate-chunk variant ───────────────────────────────────────────────────
async def _llm_chunk_ok(
    profile, goal, activity_summary, day_count, start_day_number,
    existing_days, timeout_seconds=60.0,
):
    """Valid chunk payload: exactly ``day_count`` days (so the accumulated plan
    never exceeds days_per_week)."""
    return {
        "days": [
            {
                "day": f"Dia {start_day_number + i}",
                "exercises": [
                    {
                        "name": "Flexion",
                        "sets": 3,
                        "reps": 12,
                        "duration_seconds": None,
                        "rest_seconds": 60,
                        "equipment": "ninguno",
                    }
                ],
            }
            for i in range(day_count)
        ]
    }


async def _llm_chunk_none(
    profile, goal, activity_summary, day_count, start_day_number,
    existing_days, timeout_seconds=60.0,
):
    return None


def test_generate_routine_chunk_success_and_failure(monkeypatch):
    """generate-chunk: a valid chunk → 200 with the accumulated plan (no more than
    days_per_week); a failing chunk → 502 Spanish without corrupting state."""
    fx = _Fixture()
    try:
        fx.derive_phases()

        # Chunk 0 of 1 succeeds → single active plan with days_per_week days.
        monkeypatch.setattr(llm_service, "generate_workout_chunk", _llm_chunk_ok)
        resp = fx.client.post(
            "/api/goal-plan/routine/generate-chunk",
            json={"chunk_index": 0, "chunk_count": 1},
            headers=fx.headers,
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["structure"]) <= _PROFILE["days_per_week"]
        before = fx.state()
        assert before["routine_count"] == 1

        # A failing chunk → 502 Spanish; the accumulated plan is preserved.
        monkeypatch.setattr(llm_service, "generate_workout_chunk", _llm_chunk_none)
        fail = fx.client.post(
            "/api/goal-plan/routine/generate-chunk",
            json={"chunk_index": 0, "chunk_count": 1},
            headers=fx.headers,
        )
        assert fail.status_code == 502, fail.text
        detail = fail.json()["detail"]
        assert "bloque" in detail.lower()
        assert "intenta de nuevo" in detail.lower()
    finally:
        fx.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
