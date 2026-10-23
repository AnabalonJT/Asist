"""Property test for the Goal_Wizard goal-step response shape (goal-wizard).

This targets the route handler ``put_goal`` in ``app/routes/goal_plan.py``
(``PUT /api/goal-plan/goal`` → ``GoalOut``). Unlike the modules that exercise the
PURE phase logic, this one drives the real async route end to end: it builds a
minimal FastAPI app mounting only the ``goal_plan`` router, overrides
``app.database.get_db`` with a throwaway in-memory SQLite async session, seeds a
user + FitnessProfile, authenticates with a real JWT from
``app.services.auth_service.auth_service``, and asserts the 200 response carries
the computed ``target_rate`` and the Spanish medical disclaimer.

Hypothesis does not drive ``async def`` tests itself, so each example runs its
async scenario with ``asyncio.run`` from inside a synchronous Hypothesis test,
mirroring ``tests/test_property_goal_wizard_persist.py``. No running PostgreSQL
is required.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
from datetime import date, timedelta

import httpx
from fastapi import FastAPI
from hypothesis import given, settings, strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (FKs from fitness_profiles point at users).
import app.models  # noqa: F401
from app.models.user import User
from app.models.fitness_profile import FitnessProfile
from app.routes import goal_plan
from app.services import fitness_service, goal_wizard_service
from app.services.auth_service import auth_service


# Valid body data for a weight-target profile. put_goal returns 400 without a
# seeded profile, so we always seed one with in-range body data.
_weight = st.floats(min_value=40.0, max_value=200.0,
                    allow_nan=False, allow_infinity=False)
_height = st.floats(min_value=140.0, max_value=210.0,
                    allow_nan=False, allow_infinity=False)
_age = st.integers(min_value=18, max_value=90)


@st.composite
def _goal_input(draw):
    """A seeded profile weight plus a valid goal (target weight in 30..300 and a
    strictly future target date), spanning the input space validate_goal_fields
    accepts."""
    current = round(draw(_weight), 2)
    # target_weight_kg must be within the validate_goal_fields band [30, 300].
    target = round(draw(st.floats(min_value=30.0, max_value=300.0,
                                  allow_nan=False, allow_infinity=False)), 2)
    # target_date strictly after today (>= 1 day; a few days to >1 year ahead).
    days_ahead = draw(st.integers(min_value=1, max_value=400))
    return {
        "current_weight_kg": current,
        "height_cm": round(draw(_height), 2),
        "age": draw(_age),
        "target_weight_kg": target,
        "target_date": (date.today() + timedelta(days=days_ahead)).isoformat(),
    }


async def _run_scenario(data: dict) -> None:
    """Fresh in-memory DB + minimal app mounting only the goal_plan router. Seed a
    user and FitnessProfile, authenticate with a real JWT, PUT the goal and assert
    the response shape."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                         expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user = User(email="goaltester@example.com", password_hash="x")
            db.add(user)
            await db.flush()

            # put_goal returns 400 if no profile exists → seed one first.
            profile = FitnessProfile(
                user_id=user.id,
                weight_kg=data["current_weight_kg"],
                height_cm=data["height_cm"],
                age=data["age"],
                sex=None,
                level="principiante",
                equipment="[]",
                days_per_week=3,
                minutes_per_session=45,
            )
            db.add(profile)
            await db.flush()
            await db.commit()

            token = auth_service.create_token(user.id, user.is_admin)

            app = FastAPI()
            app.include_router(goal_plan.router, prefix="/api/goal-plan")

            # Every request shares the same seeded session so the route sees the
            # user/profile and get_current_user resolves against it.
            async def _override_get_db():
                yield db

            app.dependency_overrides[get_db] = _override_get_db

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.put(
                    "/api/goal-plan/goal",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "target_weight_kg": data["target_weight_kg"],
                        "target_date": data["target_date"],
                    },
                )

            assert resp.status_code == 200, (
                f"Expected 200, got {resp.status_code}: {resp.text}"
            )
            payload = resp.json()

            # The response includes the target_rate computed by compute_target_rate.
            rate = payload.get("target_rate")
            assert rate is not None, "target_rate must be present and non-null"
            assert isinstance(rate, dict)
            # The exact keys compute_target_rate returns.
            weeks = max(
                1,
                (fitness_service._parse_iso_date(data["target_date"]) - date.today()).days
                / 7.0,
            )
            expected_rate = fitness_service.compute_target_rate(
                current_weight=data["current_weight_kg"],
                target_weight=data["target_weight_kg"],
                weeks=weeks,
            )
            assert set(rate.keys()) == set(expected_rate.keys()), (
                f"target_rate keys mismatch: {set(rate.keys())}"
            )
            for key in ("rate_kg_per_week", "daily_kcal_delta", "direction"):
                assert key in rate, f"target_rate missing {key}"
                assert rate[key] == expected_rate[key]

            # And the Spanish medical disclaimer.
            assert payload.get("disclaimer") == goal_wizard_service.DISCLAIMER
            assert isinstance(payload["disclaimer"], str) and payload["disclaimer"]
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(data=_goal_input())
def test_goal_response_includes_rate_and_disclaimer(data):
    """Feature: goal-wizard, Property 6: La respuesta de objetivo incluye el ritmo
    y el descargo.

    Validates: Requirements 3.4

    For any valid weight_target goal, PUT /api/goal-plan/goal returns a non-null
    target_rate (with the keys compute_target_rate returns) and the Spanish
    medical disclaimer (goal_wizard_service.DISCLAIMER).
    """
    asyncio.run(_run_scenario(data))
