"""Property test: state preservation when routine generation fails (goal-wizard).

# Feature: goal-wizard, Property 14: Preservación del estado ante fallo de generación de rutina

Validates: Requirements 9.3, 9.4

Property 14 (design.md): *For any* LLM_Service failure mode during routine
generation (timeout, error, empty response, or uninterpretable content), the
user's Fitness_Profile, goal (Weight_Goal), DietPhasePlan and previously-active
WorkoutPlan must remain unchanged.

Requirement 9.3: on failure (timeout / error / empty / uninterpretable content)
the Goal_Wizard returns a Spanish retryable error and preserves the Wizard_State
and prior-step data.
Requirement 9.4: when generation fails, the Fitness_Profile, Weight_Goal,
Diet_Phase_Plan and previously-active Workout_Plan are preserved unchanged.

This is a ROUTE-level property test with NO conftest.py: it builds a throwaway
FastAPI app wired only to the ``goal_plan`` router, overrides ``get_db`` with an
in-memory async SQLite session (same pattern as
``tests/test_property_goal_wizard_disclaimer.py``), authenticates with a real JWT
minted by ``auth_service`` for a seeded user with a complete profile + goal + an
active DietPhasePlan + a pre-existing active WorkoutPlan, and MOCKS the LLM so a
RANDOMLY-CHOSEN failure mode is simulated. The real OpenRouter API is NEVER
called.

Failure modes exercised (one per Hypothesis example, chosen by the input):
  - ``fitness_service.generate_workout_plan`` raises ``LLMError`` (timeout/network)
  - ``fitness_service.generate_workout_plan`` raises a generic ``Exception``
  - ``llm_service.generate_workout_plan`` returns ``None``  (empty response →
    the REAL fitness_service failure path turns it into ``LLMError``)
  - ``llm_service.generate_workout_plan`` returns uninterpretable content
    (invalid shape → the REAL fitness_service parse path raises ``LLMError``)

For every generated case: the ``POST /routine/generate`` call must fail with HTTP
502 (retryable Spanish error), and the profile / goal / diet-phase-plan /
previously-active workout plan must be byte-for-byte unchanged, with no new or
partial active WorkoutPlan persisted.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
import json
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (FKs from diet_phase_plans/fitness_profiles/
# workout_plans point at users).
import app.models  # noqa: F401
from app.models.user import User
from app.models.fitness_profile import FitnessProfile
from app.models.workout_plan import WorkoutPlan
from app.models.diet_phase_plan import DietPhasePlan
from app.routes import goal_plan
from app.services import fitness_service
from app.services import llm_service
from app.services.auth_service import auth_service


# A deterministic, pre-existing active routine the user already owns. If state is
# preserved, this exact structure must survive a failed generation.
_PRIOR_ROUTINE = [
    {
        "day": "Dia 1",
        "exercises": [
            {
                "name": "Press banca",
                "sets": 4,
                "reps": 8,
                "duration_seconds": None,
                "rest_seconds": 90,
                "equipment": "barra",
            }
        ],
    }
]

# A deterministic active diet phase plan the user already owns.
_PRIOR_PHASES = [
    {
        "index": 0,
        "start_weight": 90.0,
        "end_weight": 87.5,
        "weeks": 4.0,
        "kcal": 2180.0,
        "protein_g": 144.0,
        "fat_g": 60.4,
        "carbs_g": 272.9,
        "status": "active",
        "start_date": None,
        "end_date": None,
        "maintenance": False,
    },
    {
        "index": 1,
        "start_weight": 87.5,
        "end_weight": 85.0,
        "weeks": 4.0,
        "kcal": 2100.0,
        "protein_g": 140.0,
        "fat_g": 58.0,
        "carbs_g": 260.0,
        "status": "pending",
        "start_date": None,
        "end_date": None,
        "maintenance": False,
    },
]


# ── LLM failure stand-ins (never touch OpenRouter) ────────────────────────────
async def _raise_llm_error(db, user_id, overrides=None):
    """Simulate a timeout/network failure surfaced as LLMError."""
    raise fitness_service.LLMError(
        "No pudimos generar tu rutina en este momento. Intenta de nuevo.",
        kind="timeout",
    )


async def _raise_generic(db, user_id, overrides=None):
    """Simulate an unexpected failure (generic Exception)."""
    raise RuntimeError("boom: unexpected failure mid-generation")


async def _llm_returns_none(profile, goal, activity_summary, timeout_seconds=60.0):
    """Simulate an empty LLM response (None). The REAL fitness_service path then
    retries once and raises LLMError(kind='error')."""
    return None


async def _llm_returns_garbage(profile, goal, activity_summary, timeout_seconds=60.0):
    """Simulate uninterpretable LLM content (wrong shape / no usable days). The
    REAL fitness_service parse path raises LLMError(kind='parse')."""
    return {"days": []}


# Four failure modes. Modes 0/1 patch the service wrapper directly; modes 2/3
# patch the LLM layer so the REAL fitness_service state-preservation path runs.
_FAILURE_MODES = ("llm_error", "generic", "empty_response", "garbage_content")


# ── Input strategy ────────────────────────────────────────────────────────────
_weight = st.floats(min_value=50.0, max_value=180.0,
                    allow_nan=False, allow_infinity=False)
_height = st.floats(min_value=150.0, max_value=200.0,
                    allow_nan=False, allow_infinity=False)
_age = st.integers(min_value=18, max_value=80)
_sex = st.sampled_from(["male", "female", "other", None])


@st.composite
def _scenario(draw):
    """A complete weight-target profile + goal, a randomly-chosen failure mode,
    and whether the user already has a pre-existing active WorkoutPlan."""
    start = draw(_weight)
    delta = draw(st.floats(min_value=2.0, max_value=12.0,
                           allow_nan=False, allow_infinity=False))
    sign = draw(st.sampled_from([1.0, -1.0]))
    target = min(max(start + sign * delta, 45.0), 185.0)
    if abs(target - start) < 1.0:  # ensure a real journey (A != B)
        target = start - delta if start - delta >= 45.0 else start + delta
    weeks_ahead = draw(st.integers(min_value=4, max_value=52))
    return {
        "weight_kg": round(start, 2),
        "height_cm": round(draw(_height), 2),
        "age": draw(_age),
        "sex": draw(_sex),
        "level": "principiante",
        "days_per_week": draw(st.integers(min_value=1, max_value=7)),
        "minutes_per_session": draw(st.integers(min_value=20, max_value=90)),
        "target_weight_kg": round(target, 2),
        "target_date": (date.today() + timedelta(weeks=weeks_ahead)).isoformat(),
        "failure_mode": draw(st.sampled_from(_FAILURE_MODES)),
        "has_prior_routine": draw(st.booleans()),
    }


def _build_client(engine, session_factory):
    """Build a FastAPI app with ONLY the goal_plan router and the in-memory DB
    override, returning a TestClient."""
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


async def _seed(session_factory, data) -> int:
    """Seed one user with a complete profile + goal + active DietPhasePlan and
    (optionally) a pre-existing active WorkoutPlan. Return the user id."""
    async with session_factory() as db:
        user = User(email="preserve@example.com", password_hash="x")
        db.add(user)
        await db.flush()

        profile = FitnessProfile(
            user_id=user.id,
            weight_kg=data["weight_kg"],
            height_cm=data["height_cm"],
            age=data["age"],
            sex=data["sex"],
            level=data["level"],
            equipment="[]",
            days_per_week=data["days_per_week"],
            minutes_per_session=data["minutes_per_session"],
            goal_type="weight_target",
            target_weight_kg=data["target_weight_kg"],
            target_date=data["target_date"],
        )
        db.add(profile)

        diet_plan = DietPhasePlan(
            user_id=user.id,
            start_weight_kg=data["weight_kg"],
            target_weight_kg=data["target_weight_kg"],
            goal_reached=False,
            phases=json.dumps(_PRIOR_PHASES, ensure_ascii=False),
            active=True,
        )
        db.add(diet_plan)

        if data["has_prior_routine"]:
            prior = WorkoutPlan(
                user_id=user.id,
                goal_type="weight_target",
                structure=json.dumps(_PRIOR_ROUTINE, ensure_ascii=False),
                active=True,
            )
            db.add(prior)

        await db.commit()
        return user.id


async def _snapshot(session_factory, user_id) -> dict:
    """Capture the exact persisted state that must survive a failed generation:
    the profile fields, the goal fields, the diet phase plan, and every workout
    plan (so a new/partial active plan would be detected)."""
    async with session_factory() as db:
        profile = (
            await db.execute(
                select(FitnessProfile).where(FitnessProfile.user_id == user_id)
            )
        ).scalar_one()
        diet_plan = (
            await db.execute(
                select(DietPhasePlan).where(DietPhasePlan.user_id == user_id)
            )
        ).scalar_one()
        workouts = (
            await db.execute(
                select(WorkoutPlan)
                .where(WorkoutPlan.user_id == user_id)
                .order_by(WorkoutPlan.id)
            )
        ).scalars().all()

        return {
            "profile": {
                "weight_kg": profile.weight_kg,
                "height_cm": profile.height_cm,
                "age": profile.age,
                "sex": profile.sex,
                "level": profile.level,
                "equipment": profile.equipment,
                "days_per_week": profile.days_per_week,
                "minutes_per_session": profile.minutes_per_session,
                "goal_type": profile.goal_type,
                "target_weight_kg": profile.target_weight_kg,
                "target_date": profile.target_date,
            },
            "diet_plan": {
                "id": diet_plan.id,
                "start_weight_kg": diet_plan.start_weight_kg,
                "target_weight_kg": diet_plan.target_weight_kg,
                "goal_reached": diet_plan.goal_reached,
                "phases": diet_plan.phases,
                "active": diet_plan.active,
            },
            "workouts": [
                {
                    "id": w.id,
                    "goal_type": w.goal_type,
                    "structure": w.structure,
                    "active": w.active,
                }
                for w in workouts
            ],
        }


@settings(max_examples=100, deadline=None)
@given(scenario=_scenario())
def test_routine_failure_preserves_state(scenario):
    """Feature: goal-wizard, Property 14: Preservación del estado ante fallo de
    generación de rutina.

    Validates: Requirements 9.3, 9.4

    When routine generation fails (LLM timeout / error / empty / uninterpretable),
    the route returns a retryable 502 and the profile, goal, diet phase plan and
    previously-active workout plan are preserved byte-for-byte, with no new or
    partial active WorkoutPlan persisted.
    """
    # A manual MonkeyPatch context (not the function-scoped pytest fixture) is
    # reset for EACH generated input, as Hypothesis re-runs the body.
    with pytest.MonkeyPatch.context() as mp:
        mode = scenario["failure_mode"]
        if mode == "llm_error":
            mp.setattr(fitness_service, "generate_workout_plan", _raise_llm_error)
        elif mode == "generic":
            mp.setattr(fitness_service, "generate_workout_plan", _raise_generic)
        elif mode == "empty_response":
            # Let the REAL fitness_service run; only the LLM layer "fails".
            mp.setattr(llm_service, "generate_workout_plan", _llm_returns_none)
        elif mode == "garbage_content":
            mp.setattr(llm_service, "generate_workout_plan", _llm_returns_garbage)
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unknown failure mode: {mode}")

        _run_preservation_scenario(scenario)


def _run_preservation_scenario(scenario):
    """Drive one failed routine generation against a fresh in-memory DB and assert
    full state preservation."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _create_schema():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    try:
        asyncio.run(_create_schema())
        user_id = asyncio.run(_seed(session_factory, scenario))

        before = asyncio.run(_snapshot(session_factory, user_id))

        token = auth_service.create_token(user_id, is_admin=False)
        headers = {"Authorization": f"Bearer {token}"}
        client = _build_client(engine, session_factory)

        # The generate call must FAIL with a retryable 502 (Req 9.3).
        resp = client.post("/api/goal-plan/routine/generate", headers=headers)
        assert resp.status_code == 502, (
            f"expected 502 on failed generation ({scenario['failure_mode']}), "
            f"got {resp.status_code}: {resp.text}"
        )
        # Retryable Spanish error message, no stack trace leaked.
        detail = resp.json().get("detail", "")
        assert isinstance(detail, str) and detail.strip(), "empty error detail"
        assert "rutina" in detail.lower(), (
            f"error detail is not the Spanish routine message: {detail!r}"
        )

        client.close()

        after = asyncio.run(_snapshot(session_factory, user_id))

        # Req 9.4: profile, goal and diet phase plan are byte-for-byte unchanged.
        assert after["profile"] == before["profile"], (
            f"profile/goal changed after failed generation "
            f"({scenario['failure_mode']}): {before['profile']} -> {after['profile']}"
        )
        assert after["diet_plan"] == before["diet_plan"], (
            f"diet phase plan changed after failed generation "
            f"({scenario['failure_mode']}): {before['diet_plan']} -> {after['diet_plan']}"
        )

        # Req 9.4: no new/partial WorkoutPlan persisted; a previously-active
        # routine (if any) remains exactly as it was.
        assert after["workouts"] == before["workouts"], (
            f"workout plans changed after failed generation "
            f"({scenario['failure_mode']}): {before['workouts']} -> {after['workouts']}"
        )
        # Explicit: at most one active plan, and only the pre-existing one (if any).
        active_after = [w for w in after["workouts"] if w["active"]]
        if scenario["has_prior_routine"]:
            assert len(active_after) == 1, (
                f"expected exactly the pre-existing active routine to survive, "
                f"found {len(active_after)} active plans"
            )
            assert active_after[0]["structure"] == json.dumps(
                _PRIOR_ROUTINE, ensure_ascii=False
            ), "the pre-existing active routine was mutated"
        else:
            assert active_after == [], (
                "a new active WorkoutPlan was persisted despite generation failure"
            )
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
