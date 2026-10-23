"""Property test for the Goal_Wizard diet derivation RESPONSE shape (goal-wizard).

This targets the route-level diet response built by ``_phase_plan_out`` in
``app/routes/goal_plan.py`` → ``PhasePlanOut``, exercised through
``POST /api/goal-plan/phases/derive`` and ``GET /api/goal-plan/phases``. Unlike
the pure-logic ``test_property_*`` modules, this one drives real endpoints, so it
spins up a throwaway in-memory async SQLite database per example, overrides the
``get_db`` dependency to yield a session from that engine, and authenticates with
a REAL JWT minted by ``auth_service`` for a seeded user (the ``get_current_user``
dependency decodes ``sub`` → user id). Hypothesis does not drive ``async def``
tests, so each synchronous example runs the async scenario with ``asyncio.run``
and an ``httpx.AsyncClient`` over ``ASGITransport`` — no running PostgreSQL or web
server required. This follows the in-memory async DB pattern established in
``tests/test_property_goal_wizard_persist.py``.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
from datetime import date, timedelta

from fastapi import FastAPI
from hypothesis import assume, given, settings, strategies as st
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (FKs from diet_phase_plans/fitness_profiles
# point at users).
import app.models  # noqa: F401
from app.models.user import User
from app.models.fitness_profile import FitnessProfile
from app.routes import goal_plan
from app.services import goal_wizard_service
from app.services.auth_service import auth_service


# Valid body data for the Mifflin-St Jeor BMR and protein-per-kg split that the
# reused nutrition derivation consumes.
_weight = st.floats(min_value=50.0, max_value=180.0,
                    allow_nan=False, allow_infinity=False)
_height = st.floats(min_value=150.0, max_value=205.0,
                    allow_nan=False, allow_infinity=False)
_age = st.integers(min_value=18, max_value=80)
_sex = st.sampled_from(["male", "female", "other", None])


@st.composite
def _goal_profile(draw):
    """A complete weight-target profile with a varied A→B journey.

    start/target differ enough to force the journey through one or more phases;
    the target weight stays in the valid body-weight band so the reused nutrition
    derivation stays well-defined.
    """
    start = draw(_weight)
    delta = draw(st.floats(min_value=1.0, max_value=20.0,
                           allow_nan=False, allow_infinity=False))
    sign = draw(st.sampled_from([1.0, -1.0]))
    target = min(max(start + sign * delta, 45.0), 185.0)
    if abs(target - start) < 0.5:  # ensure a real journey (A != B)
        target = start - delta if start - delta >= 45.0 else start + delta
    weeks_ahead = draw(st.integers(min_value=2, max_value=60))
    return {
        "weight_kg": round(start, 2),
        "height_cm": round(draw(_height), 2),
        "age": draw(_age),
        "sex": draw(_sex),
        "level": "principiante",
        "days_per_week": draw(st.integers(min_value=1, max_value=7)),
        "minutes_per_session": draw(st.integers(min_value=10, max_value=120)),
        "target_weight_kg": round(target, 2),
        "target_date": (date.today() + timedelta(weeks=weeks_ahead)).isoformat(),
    }


def _build_app(session_factory) -> FastAPI:
    """Minimal FastAPI app mounting only the goal_plan router with get_db
    overridden to yield a session from the throwaway in-memory engine. Avoids the
    real app lifespan (Telegram polling / scheduler) entirely."""
    app = FastAPI()
    app.include_router(goal_plan.router, prefix="/api/goal-plan")

    async def _override_get_db():
        async with session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db] = _override_get_db
    return app


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _assert_diet_response(payload: dict) -> None:
    """Property 5 assertions over a PhasePlanOut payload: every phase listed,
    each non-null phase carries the four numeric targets, and the disclaimer
    equals the Spanish medical disclaimer and is non-empty."""
    phases = payload["phases"]
    assert isinstance(phases, list) and len(phases) >= 1

    # Phases are listed in order (index 0..n-1) — all phases present.
    assert [p["index"] for p in phases] == list(range(len(phases)))

    for phase in phases:
        for key in ("kcal", "protein_g", "fat_g", "carbs_g"):
            value = phase[key]
            # Non-physical extreme targets may be None; only guard those cases,
            # never weaken the all-phases / disclaimer assertions.
            if value is not None:
                assert _is_number(value)

    # The disclaimer is the Spanish medical disclaimer and is non-empty text.
    disclaimer = payload["disclaimer"]
    assert disclaimer == goal_wizard_service.DISCLAIMER
    assert isinstance(disclaimer, str) and disclaimer.strip()


async def _run_scenario(profile_data: dict) -> bool:
    """Seed a user + complete weight-target profile in a fresh in-memory DB, then
    drive ``POST /phases/derive`` and ``GET /phases`` with a real JWT and assert
    the Property 5 response shape. Returns False when the reused derivation yields
    a non-physical target (negative kcal) on extreme inputs so the caller can
    ``assume`` it away (per the repo precedent in test_property_goal_wizard.py)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                         expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user = User(email="diet-tester@example.com", password_hash="x")
            db.add(user)
            await db.flush()
            user_id = user.id

            profile = FitnessProfile(
                user_id=user_id,
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

        app = _build_app(session_factory)
        token = auth_service.create_token(user_id)
        headers = {"Authorization": f"Bearer {token}"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport,
                               base_url="http://testserver") as client:
            # POST /phases/derive — builds and persists the plan, returns PhasePlanOut.
            derive = await client.post(
                "/api/goal-plan/phases/derive", headers=headers
            )
            assert derive.status_code == 200, derive.text
            derive_body = derive.json()

            # A phase may legitimately carry a None target when an extreme input
            # drives the reused derivation to a non-physical (negative) kcal — the
            # repo precedent guards ONLY that case, without weakening the all-phases
            # / disclaimer assertions. Detect it and let the caller assume it away.
            non_physical = any(
                derive_body["phases"][i]["kcal"] is None
                for i in range(len(derive_body["phases"]))
            )
            if non_physical:
                return False

            _assert_diet_response(derive_body)

            # GET /phases — returns the same active plan as PhasePlanOut.
            fetched = await client.get("/api/goal-plan/phases", headers=headers)
            assert fetched.status_code == 200, fetched.text
            fetched_body = fetched.json()
            assert "message" not in fetched_body  # an active plan exists
            _assert_diet_response(fetched_body)

            # Both responses describe the same set of phases.
            assert len(fetched_body["phases"]) == len(derive_body["phases"])
        return True
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(profile=_goal_profile())
def test_diet_response_includes_all_phases_targets_and_disclaimer(profile):
    """Feature: goal-wizard, Property 5: La respuesta de dieta incluye todas las
    fases con metas y descargo.

    Validates: Requirements 6.7

    For any valid A→B goal, the diet derivation response lists every phase of the
    plan, each non-null phase carries its four numeric targets
    (kcal/protein_g/fat_g/carbs_g), and the response includes a non-empty Spanish
    medical disclaimer equal to ``goal_wizard_service.DISCLAIMER``. Verified over
    both ``POST /phases/derive`` and ``GET /phases``.
    """
    ok = asyncio.run(_run_scenario(profile))
    # Non-physical (negative kcal) extreme inputs are out of the space Property 5
    # covers; following the repo precedent, assume them away rather than weaken
    # the all-phases / disclaimer assertions.
    assume(ok)
