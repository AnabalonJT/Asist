"""Property test: medical disclaimer on Goal_Wizard responses that carry
Phase_Targets (metas) or a routine (goal-wizard).

# Feature: goal-wizard, Property 16: Descargo médico en respuestas con metas o rutina

Validates: Requirements 12.5

Property 16 (design.md): *For any* Goal_Wizard response that contains
Phase_Targets or a Workout_Plan, the response must include the non-empty Spanish
medical disclaimer. Concretely, every ``/api/goal-plan/*`` response that carries
metas or a routine includes ``goal_wizard_service.DISCLAIMER``.

This is a ROUTE-level property test with NO conftest.py: it builds a throwaway
FastAPI app wired only to the ``goal_plan`` router, overrides ``get_db`` with an
in-memory async SQLite session (same pattern as
``tests/test_property_goal_wizard_persist.py``), authenticates with a real JWT
minted by ``auth_service`` for a seeded user with a complete profile + goal, and
MOCKS the LLM (``fitness_service.generate_workout_plan`` /
``generate_workout_plan_chunk``) so the routine responses are deterministic and
the real OpenRouter API is never called.

Hypothesis varies the profile/goal inputs; across every generated case the
metas-bearing responses (``PUT /goal``, ``POST /phases/derive``,
``GET /phases``, ``PUT /phases/active/targets``, ``POST /weight``) and the
routine-bearing responses (``POST /routine/generate``,
``POST /routine/generate-chunk``, ``PUT /routine``) must carry a non-empty
``disclaimer`` equal to ``goal_wizard_service.DISCLAIMER``.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (FKs from diet_phase_plans/fitness_profiles/
# workout_plans point at users).
import app.models  # noqa: F401
from app.models.user import User
from app.models.fitness_profile import FitnessProfile
from app.models.workout_plan import WorkoutPlan
from app.routes import goal_plan
from app.services import fitness_service
from app.services import goal_wizard_service
from app.services.auth_service import auth_service


# A deterministic, non-truncated routine used to stand in for the LLM result.
_FAKE_ROUTINE = [
    {
        "day": "Dia 1",
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
]


async def _fake_generate_workout_plan(db, user_id, overrides=None):
    """Deterministic stand-in for the LLM-backed routine generator.

    Persists a single active WorkoutPlan (deactivating any prior one) exactly
    like the real service would, but without ever calling OpenRouter.
    """
    from sqlalchemy import select
    import json

    existing = (
        await db.execute(
            select(WorkoutPlan).where(
                WorkoutPlan.user_id == user_id,
                WorkoutPlan.active == True,  # noqa: E712
            )
        )
    ).scalars().all()
    for plan in existing:
        plan.active = False

    plan = WorkoutPlan(
        user_id=user_id,
        goal_type="weight_target",
        structure=json.dumps(_FAKE_ROUTINE, ensure_ascii=False),
        active=True,
    )
    db.add(plan)
    await db.flush()
    return plan


async def _fake_generate_workout_plan_chunk(
    db, user_id, chunk_index, chunk_count, overrides=None
):
    """Deterministic stand-in for the chunked LLM routine generator."""
    return await _fake_generate_workout_plan(db, user_id, overrides=overrides)


# ── Input strategy ────────────────────────────────────────────────────────────
_weight = st.floats(min_value=50.0, max_value=180.0,
                    allow_nan=False, allow_infinity=False)
_height = st.floats(min_value=150.0, max_value=200.0,
                    allow_nan=False, allow_infinity=False)
_age = st.integers(min_value=18, max_value=80)
_sex = st.sampled_from(["male", "female", "other", None])


@st.composite
def _goal_profile(draw):
    """A complete weight-target profile with a non-trivial A→B journey, kept well
    inside the valid body-weight band so the reused nutrition derivation and the
    phase split stay well-defined."""
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


async def _seed(session_factory, profile_data) -> int:
    """Seed one user with a complete profile + goal; return the user id."""
    async with session_factory() as db:
        user = User(email="disclaimer@example.com", password_hash="x")
        db.add(user)
        await db.flush()

        profile = FitnessProfile(
            user_id=user.id,
            weight_kg=profile_data["weight_kg"],
            height_cm=profile_data["height_cm"],
            age=profile_data["age"],
            sex=profile_data["sex"],
            level=profile_data["level"],
            equipment="[]",
            days_per_week=profile_data["days_per_week"],
            minutes_per_session=profile_data["minutes_per_session"],
            goal_type="weight_target",
            target_weight_kg=profile_data["target_weight_kg"],
            target_date=profile_data["target_date"],
        )
        db.add(profile)
        await db.commit()
        return user.id


def _assert_disclaimer(payload, where):
    """Assert the response payload carries the exact non-empty Spanish disclaimer."""
    assert "disclaimer" in payload, f"{where}: missing disclaimer field"
    disclaimer = payload["disclaimer"]
    assert isinstance(disclaimer, str) and disclaimer.strip(), (
        f"{where}: disclaimer is empty"
    )
    assert disclaimer == goal_wizard_service.DISCLAIMER, (
        f"{where}: disclaimer does not match goal_wizard_service.DISCLAIMER"
    )


@settings(max_examples=100, deadline=None)
@given(profile=_goal_profile())
def test_disclaimer_present_on_metas_or_routine_responses(profile):
    """Feature: goal-wizard, Property 16: Descargo médico en respuestas con metas
    o rutina.

    Validates: Requirements 12.5

    Every ``/api/goal-plan/*`` response that carries Phase_Targets (metas) or a
    routine includes the non-empty Spanish medical disclaimer equal to
    ``goal_wizard_service.DISCLAIMER``.
    """
    # Mock the LLM so routine responses are deterministic (never hit OpenRouter).
    # A manual MonkeyPatch context manager (instead of the function-scoped pytest
    # fixture) is reset for EACH generated input, as Hypothesis requires.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            fitness_service, "generate_workout_plan", _fake_generate_workout_plan
        )
        mp.setattr(
            fitness_service,
            "generate_workout_plan_chunk",
            _fake_generate_workout_plan_chunk,
        )
        _run_disclaimer_scenario(profile)


def _run_disclaimer_scenario(profile):
    """Drive one full Goal_Wizard happy path against a fresh in-memory DB and
    assert the disclaimer on every metas-/routine-bearing response."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _create_schema():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    try:
        asyncio.run(_create_schema())
        user_id = asyncio.run(_seed(session_factory, profile))
        token = auth_service.create_token(user_id, is_admin=False)
        headers = {"Authorization": f"Bearer {token}"}

        client = _build_client(engine, session_factory)

        # 1) PUT /goal → GoalOut carries target_rate (metas) + disclaimer.
        resp = client.put(
            "/api/goal-plan/goal",
            json={
                "target_weight_kg": profile["target_weight_kg"],
                "target_date": profile["target_date"],
            },
            headers=headers,
        )
        assert resp.status_code == 200, f"PUT /goal: {resp.status_code} {resp.text}"
        _assert_disclaimer(resp.json(), "PUT /goal")

        # 2) POST /phases/derive → PhasePlanOut with Phase_Targets + disclaimer.
        resp = client.post("/api/goal-plan/phases/derive", headers=headers)
        assert resp.status_code == 200, (
            f"POST /phases/derive: {resp.status_code} {resp.text}"
        )
        derive_body = resp.json()
        _assert_disclaimer(derive_body, "POST /phases/derive")
        active_phase = derive_body.get("active_phase")
        assert active_phase is not None, "derive produced no active phase"

        # 3) GET /phases → PhasePlanOut + disclaimer.
        resp = client.get("/api/goal-plan/phases", headers=headers)
        assert resp.status_code == 200, (
            f"GET /phases: {resp.status_code} {resp.text}"
        )
        _assert_disclaimer(resp.json(), "GET /phases")

        # 4) POST /routine/generate (LLM mocked) → WorkoutPlanOut + disclaimer.
        resp = client.post("/api/goal-plan/routine/generate", headers=headers)
        assert resp.status_code == 200, (
            f"POST /routine/generate: {resp.status_code} {resp.text}"
        )
        _assert_disclaimer(resp.json(), "POST /routine/generate")

        # 5) POST /routine/generate-chunk (LLM mocked) → WorkoutPlanOut + disclaimer.
        resp = client.post(
            "/api/goal-plan/routine/generate-chunk",
            json={"chunk_index": 0, "chunk_count": 1},
            headers=headers,
        )
        assert resp.status_code == 200, (
            f"POST /routine/generate-chunk: {resp.status_code} {resp.text}"
        )
        _assert_disclaimer(resp.json(), "POST /routine/generate-chunk")

        # 6) PUT /routine → WorkoutPlanOut + disclaimer.
        resp = client.put(
            "/api/goal-plan/routine",
            json={"structure": _FAKE_ROUTINE},
            headers=headers,
        )
        assert resp.status_code == 200, (
            f"PUT /routine: {resp.status_code} {resp.text}"
        )
        _assert_disclaimer(resp.json(), "PUT /routine")

        # 7) PUT /phases/active/targets → PhasePlanOut + disclaimer. Use fixed
        #    values inside the MANUAL_* ranges (the edit endpoint validates the
        #    manual input, which is independent of Property 16 — the derived
        #    per-phase targets can legitimately fall below the manual-edit floor
        #    for a very light body).
        resp = client.put(
            "/api/goal-plan/phases/active/targets",
            json={
                "kcal": 2000.0,
                "protein_g": 150.0,
                "fat_g": 60.0,
                "carbs_g": 220.0,
            },
            headers=headers,
        )
        assert resp.status_code == 200, (
            f"PUT /phases/active/targets: {resp.status_code} {resp.text}"
        )
        _assert_disclaimer(resp.json(), "PUT /phases/active/targets")

        # 8) POST /weight → PhasePlanOut + disclaimer. Report the current weight
        #    so the active phase is not auto-completed; response still carries metas.
        resp = client.post(
            "/api/goal-plan/weight",
            json={
                "weight_kg": profile["weight_kg"],
                "entry_date": date.today().isoformat(),
            },
            headers=headers,
        )
        assert resp.status_code == 200, (
            f"POST /weight: {resp.status_code} {resp.text}"
        )
        _assert_disclaimer(resp.json(), "POST /weight")

        client.close()
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
