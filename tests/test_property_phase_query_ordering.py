"""Property test for querying the active phase plan (goal-wizard).

Property 13 (Req 11.2): querying a user's active ``DietPhasePlan`` returns its
phases ordered ascending by ``index`` and correctly signals the active phase.

The guarantee is owned by the read path: ``goal_wizard_service.get_active_phase_plan``
returns the persisted plan, and ``DietPhasePlan.phases_list`` / ``active_phase``
expose the stored ordering without re-sorting. So the faithful test persists a
real plan via ``derive_and_persist_plan`` (which owns how phases are ordered on
write) and then queries it back through ``get_active_phase_plan`` to assert the
read order and the signalled active phase.

Like ``test_property_goal_wizard_persist.py``, this needs a live async session,
so it spins up a throwaway in-memory SQLite database per example and drives the
async calls with ``asyncio.run`` from inside a synchronous Hypothesis test
(Hypothesis does not drive ``async def`` tests itself).

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
from datetime import date, timedelta

from hypothesis import given, settings, strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (FKs from diet_phase_plans/fitness_profiles
# point at users).
import app.models  # noqa: F401
from app.models.user import User
from app.models.fitness_profile import FitnessProfile
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

    start/target differ enough to force the journey through several phases (so
    the ordering assertion is meaningful), while the target weight stays inside
    the valid body-weight band so the reused nutrition derivation is well-defined.
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


async def _run_scenario(profile_data: dict) -> None:
    """Create a fresh in-memory DB, seed one user + profile, persist a phase plan
    and assert the query returns phases ordered ascending by index with the
    active phase correctly signalled."""
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

            await goal_wizard_service.derive_and_persist_plan(db, user.id)
            await db.flush()

            # Query the active plan through the read path (Req 11.2).
            plan = await goal_wizard_service.get_active_phase_plan(db, user.id)
            assert plan is not None, "Expected an active plan after derivation."

            phases = plan.phases_list()
            assert phases, "The active plan must expose at least one phase."

            indices = [p["index"] for p in phases]

            # Phases are returned ordered ascending by index.
            assert indices == sorted(indices), (
                f"Phases not ordered ascending by index: {indices}"
            )

            # Indices are a contiguous 0..n-1 sequence (ordered list, no gaps).
            assert indices == list(range(len(phases))), (
                f"Phase indices are not a contiguous 0..n-1 sequence: {indices}"
            )

            # The query signals exactly one active phase, and it is the first one
            # (the newly persisted plan activates phase 0).
            active = plan.active_phase()
            active_phases = [p for p in phases if p.get("status") == "active"]
            assert len(active_phases) == 1, (
                f"Expected exactly one active phase, found {len(active_phases)}"
            )
            assert active == active_phases[0], (
                "active_phase() must return the first phase with status 'active'."
            )
            assert active["index"] == 0, (
                f"A freshly derived plan must start active at index 0, "
                f"got {active['index']}."
            )
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(profile=_goal_profile())
def test_query_returns_phases_ordered_by_index(profile):
    """Feature: goal-wizard, Property 13: Consulta con fases ordenadas por índice.

    Validates: Requirements 11.2

    Querying a user's active ``DietPhasePlan`` returns its phases ordered
    ascending by ``index`` and correctly signals the active phase.
    """
    asyncio.run(_run_scenario(profile))
