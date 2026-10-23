"""Property tests for the Goal_Wizard async DB persistence invariant (goal-wizard).

This targets the async functions ``derive_and_persist_plan`` and
``get_active_phase_plan`` in ``app.services.goal_wizard_service``. Unlike the
other ``test_property_*`` modules (which exercise the PURE phase logic), this one
needs a live async SQLAlchemy session, so it spins up a throwaway in-memory
SQLite database per example and drives the async calls with ``asyncio.run`` from
inside a synchronous Hypothesis test (Hypothesis does not drive ``async def``
tests itself). This keeps Hypothesis and the project's async SQLAlchemy stack
compatible without requiring a running PostgreSQL instance.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
from datetime import date, timedelta

from hypothesis import given, settings, strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (FKs from diet_phase_plans/fitness_profiles
# point at users).
import app.models  # noqa: F401
from app.models.user import User
from app.models.fitness_profile import FitnessProfile
from app.models.diet_phase_plan import DietPhasePlan
from app.services import goal_wizard_service


# Valid body data for the Mifflin-St Jeor BMR and protein-per-kg split that
# ``derive_phase_targets`` (reused by ``derive_and_persist_plan``) consumes.
_weight = st.floats(min_value=40.0, max_value=200.0,
                    allow_nan=False, allow_infinity=False)
_height = st.floats(min_value=140.0, max_value=210.0,
                    allow_nan=False, allow_infinity=False)
_age = st.integers(min_value=18, max_value=90)
_sex = st.sampled_from(["male", "female", "other", None])


@st.composite
def _goal_profile(draw):
    """A complete weight-target profile with a non-trivial A→B journey.

    start/target differ enough to force the journey through several phases, and
    the target weight stays inside the valid body-weight band so the reused
    nutrition derivation stays well-defined.
    """
    start = draw(_weight)
    delta = draw(st.floats(min_value=1.0, max_value=12.0,
                           allow_nan=False, allow_infinity=False))
    sign = draw(st.sampled_from([1.0, -1.0]))
    target = min(max(start + sign * delta, 40.0), 200.0)
    if abs(target - start) < 0.5:  # ensure a real journey (A != B)
        target = start - delta if start - delta >= 40.0 else start + delta
    weeks_ahead = draw(st.integers(min_value=2, max_value=52))
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


async def _run_scenario(profile_data: dict, derivations: int) -> None:
    """Create a fresh in-memory DB, seed one user + profile, derive the phase
    plan ``derivations`` times and assert the single-active-plan invariant after
    EACH derivation."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                         expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user = User(email="tester@example.com", password_hash="x")
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
            await db.flush()

            for _ in range(derivations):
                plan = await goal_wizard_service.derive_and_persist_plan(
                    db, user.id
                )
                await db.flush()

                # Invariant (Req 5.6, 11.1): at most one active plan per user.
                active = (
                    await db.execute(
                        select(DietPhasePlan).where(
                            DietPhasePlan.user_id == user.id,
                            DietPhasePlan.active == True,  # noqa: E712
                        )
                    )
                ).scalars().all()
                assert len(active) == 1, (
                    f"Expected exactly one active plan, found {len(active)}"
                )

                # The active plan is the one just derived; the helper agrees.
                assert active[0].id == plan.id
                fetched = await goal_wizard_service.get_active_phase_plan(
                    db, user.id
                )
                assert fetched is not None and fetched.id == plan.id

                # Every OTHER plan for this user is inactive.
                all_plans = (
                    await db.execute(
                        select(DietPhasePlan).where(
                            DietPhasePlan.user_id == user.id
                        )
                    )
                ).scalars().all()
                inactive = [p for p in all_plans if p.id != plan.id]
                assert all(p.active is False for p in inactive)
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(profile=_goal_profile(),
       derivations=st.integers(min_value=1, max_value=4))
def test_at_most_one_active_phase_plan_per_user(profile, derivations):
    """Feature: goal-wizard, Property 12: A lo más un plan de fases activo por
    usuario.

    Validates: Requirements 5.6, 11.1

    After any sequence of calls to ``derive_and_persist_plan`` for a user, exactly
    one ``DietPhasePlan`` is active for that user and every previous plan is
    deactivated.
    """
    asyncio.run(_run_scenario(profile, derivations))
