"""Property test for Goal_Wizard endpoint privacy / tenant isolation (goal-wizard).

This is a ROUTE-LEVEL property test (no conftest.py). It spins up a throwaway
FastAPI app that includes the real ``app.routes.goal_plan`` router under the
``/api/goal-plan`` prefix and overrides ``app.database.get_db`` with a single
in-memory async SQLite session, so every request in one example shares the same
database. Two DISTINCT non-admin users are seeded, each with their own
FitnessProfile and a derived DietPhasePlan. A real JWT is minted per user via
``app.services.auth_service.auth_service`` so requests flow through the genuine
``get_current_user`` dependency.

The property under test (design Property 15): every ``/api/goal-plan/*`` query is
scoped to ``current_user.id``. A non-admin user A can only ever read its own
phase plan / profile / routine, and a mutation made by A (``POST /weight``,
``PUT /phases/active/targets``) must never change user B's active plan, and
vice-versa.

Hypothesis does not drive ``async def`` tests, so the async scenario runs under
``asyncio.run`` from inside a synchronous Hypothesis test, mirroring
``tests/test_property_goal_wizard_persist.py``.

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
# create_all builds the full schema (FKs from diet_phase_plans / fitness_profiles
# point at users).
import app.models  # noqa: F401
from app.models.user import User
from app.models.fitness_profile import FitnessProfile
from app.routes import goal_plan
from app.services import goal_wizard_service
from app.services.auth_service import auth_service


# ── Strategies ───────────────────────────────────────────────────────────────
# Valid body data for the Mifflin-St Jeor BMR + protein-per-kg split consumed by
# ``derive_and_persist_plan`` (reused through the seeded phase plans).
_weight = st.floats(min_value=40.0, max_value=200.0,
                    allow_nan=False, allow_infinity=False)
_height = st.floats(min_value=140.0, max_value=210.0,
                    allow_nan=False, allow_infinity=False)
_age = st.integers(min_value=18, max_value=90)
_sex = st.sampled_from(["male", "female", "other", None])


@st.composite
def _goal_profile(draw):
    """A complete weight-target profile with a non-trivial A→B journey."""
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


# ── Helpers ──────────────────────────────────────────────────────────────────
def _build_app(db: AsyncSession) -> FastAPI:
    """A minimal app exposing the real goal_plan router, with get_db overridden
    to yield the single shared in-memory session."""
    app = FastAPI()
    app.include_router(goal_plan.router, prefix="/api/goal-plan")

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    return app


async def _seed_user(db: AsyncSession, email: str, profile_data: dict) -> User:
    """Create a non-admin user + FitnessProfile and derive an active phase plan."""
    user = User(email=email, password_hash="x", is_admin=False)
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
    return user


def _auth(user: User) -> dict:
    """Bearer header carrying a genuine JWT for the user (non-admin)."""
    token = auth_service.create_token(user.id, is_admin=False)
    return {"Authorization": f"Bearer {token}"}


def _targets_of(phases: list[dict]) -> dict | None:
    """The active phase's nutrition targets, or None if there is no active phase."""
    for phase in phases:
        if phase.get("status") == "active":
            return {
                "kcal": phase.get("kcal"),
                "protein_g": phase.get("protein_g"),
                "fat_g": phase.get("fat_g"),
                "carbs_g": phase.get("carbs_g"),
            }
    return None


async def _run_scenario(profile_a: dict, profile_b: dict) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                         expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user_a = await _seed_user(db, "a@example.com", profile_a)
            user_b = await _seed_user(db, "b@example.com", profile_b)
            await db.commit()

            app = _build_app(db)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                head_a = _auth(user_a)
                head_b = _auth(user_b)

                # ── Each user reads ONLY its own phase plan (Req 12.3) ──────────
                res_a = await client.get("/api/goal-plan/phases", headers=head_a)
                res_b = await client.get("/api/goal-plan/phases", headers=head_b)
                assert res_a.status_code == 200
                assert res_b.status_code == 200
                plan_a = res_a.json()
                plan_b = res_b.json()

                # Each plan reflects that user's own A→B journey, not the other's.
                assert plan_a["phases"][0]["start_weight"] == profile_a["weight_kg"]
                assert plan_a["phases"][-1]["end_weight"] == profile_a["target_weight_kg"]
                assert plan_b["phases"][0]["start_weight"] == profile_b["weight_kg"]
                assert plan_b["phases"][-1]["end_weight"] == profile_b["target_weight_kg"]

                # ── Each user reads ONLY its own profile via /state ────────────
                st_a = (await client.get("/api/goal-plan/state", headers=head_a)).json()
                st_b = (await client.get("/api/goal-plan/state", headers=head_b)).json()
                assert st_a["weight_kg"] == profile_a["weight_kg"]
                assert st_a["target_weight_kg"] == profile_a["target_weight_kg"]
                assert st_b["weight_kg"] == profile_b["weight_kg"]
                assert st_b["target_weight_kg"] == profile_b["target_weight_kg"]

                # ── A mutates ITS OWN targets; B's plan must be untouched ──────
                b_before = _targets_of(plan_b["phases"])
                new_targets = {
                    "kcal": 2000.0,
                    "protein_g": 150.0,
                    "fat_g": 60.0,
                    "carbs_g": 200.0,
                }
                edit = await client.put(
                    "/api/goal-plan/phases/active/targets",
                    headers=head_a, json=new_targets,
                )
                assert edit.status_code == 200
                # A's active phase now carries the edited targets.
                a_after = _targets_of(edit.json()["phases"])
                assert a_after == new_targets

                # B re-reads: its active-phase targets are exactly what they were,
                # proving A's mutation did not leak across the tenant boundary.
                b_reread = (
                    await client.get("/api/goal-plan/phases", headers=head_b)
                ).json()
                assert _targets_of(b_reread["phases"]) == b_before

                # ── B registers a weigh-in; A's plan must be untouched ─────────
                a_before_weight = (
                    await client.get("/api/goal-plan/phases", headers=head_a)
                ).json()["phases"]
                weigh = await client.post(
                    "/api/goal-plan/weight",
                    headers=head_b,
                    json={
                        "weight_kg": profile_b["weight_kg"],
                        "entry_date": date.today().isoformat(),
                    },
                )
                assert weigh.status_code == 200
                a_after_weight = (
                    await client.get("/api/goal-plan/phases", headers=head_a)
                ).json()["phases"]
                # A's phases are byte-for-byte unchanged by B's weigh-in.
                assert a_after_weight == a_before_weight

                # ── Requests with no JWT are rejected, exposing no data ────────
                no_auth = await client.get("/api/goal-plan/phases")
                assert no_auth.status_code in (401, 403)
    finally:
        await engine.dispose()


# ── Property 15 ──────────────────────────────────────────────────────────────
@settings(max_examples=100, deadline=None)
@given(profile_a=_goal_profile(), profile_b=_goal_profile())
def test_goal_plan_endpoints_are_scoped_to_the_requesting_user(profile_a, profile_b):
    """Feature: goal-wizard, Property 15: Privacidad — solo registros propios.

    Validates: Requirements 12.3, 12.4

    For any pair of distinct non-admin users, every ``/api/goal-plan/*`` query is
    scoped to ``current_user.id``: user A reads only its own phase plan / profile,
    a mutation by A never changes B's active plan (and a weigh-in by B never
    changes A's), and an unauthenticated request is rejected without exposing
    data.
    """
    asyncio.run(_run_scenario(profile_a, profile_b))
