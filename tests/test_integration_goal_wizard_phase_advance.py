"""Example-based integration tests for phase advancement via weigh-in (goal-wizard).

These are ROUTE-LEVEL integration tests (no conftest.py). Each test spins up a
throwaway FastAPI app that mounts the real ``app.routes.goal_plan`` router under
``/api/goal-plan`` and overrides ``app.database.get_db`` with a single in-memory
async SQLite session, so every request in one test shares the same database.

The setup mirrors ``tests/test_property_goal_wizard_privacy.py``: seed a user +
a complete weight-target FitnessProfile, derive an active DietPhasePlan via
``goal_wizard_service.derive_and_persist_plan``, then (for deterministic
scenarios) overwrite the plan's ``phases`` JSON with a hand-built layout so the
A→B journey and per-phase boundaries are fully predictable. Requests flow
through the genuine ``get_current_user`` dependency with a real JWT.

Each test exercises ``POST /api/goal-plan/weight`` (handler ``post_weight`` →
``register_weight_and_advance`` → pure ``advance_phase_on_weight``) and asserts
the resulting ``PhasePlanOut`` (and a follow-up ``GET /phases``) reflect the
expected phase statuses, covering Requirement 7:

* 7.1/7.2 — a weigh-in reaching the active phase end advances to the next phase,
  which is re-anchored/re-derived from the current weight.
* 7.4 — a weigh-in overshooting several phase ends completes all reached phases
  and activates the first remaining pending phase.
* 7.3 — insufficient progress once the phase window has elapsed EXTENDS the
  active phase instead of advancing.
* 7.5 — reaching the end of the LAST phase produces an active maintenance phase
  and ``goal_reached=True``.
* 7.6 — the updated phase statuses are persisted and restored on a later read.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
import json
from datetime import date, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (FKs from diet_phase_plans / fitness_profiles
# / weight_entries point at users).
import app.models  # noqa: F401
from app.models.diet_phase_plan import DietPhasePlan
from app.models.fitness_profile import FitnessProfile
from app.models.user import User
from app.routes import goal_plan
from app.services import goal_wizard_service
from app.services.auth_service import auth_service


# ── Shared infra helpers ─────────────────────────────────────────────────────
def _build_app(db: AsyncSession) -> FastAPI:
    """A minimal app exposing the real goal_plan router, with get_db overridden
    to yield the single shared in-memory session."""
    app = FastAPI()
    app.include_router(goal_plan.router, prefix="/api/goal-plan")

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    return app


def _auth(user: User) -> dict:
    """Bearer header carrying a genuine JWT for the user (non-admin)."""
    token = auth_service.create_token(user.id, is_admin=False)
    return {"Authorization": f"Bearer {token}"}


async def _seed_user_with_plan(db: AsyncSession, email: str) -> User:
    """Create a non-admin user + weight-target FitnessProfile (losing weight,
    80 kg → 75 kg over 8 weeks) and derive an active DietPhasePlan.

    The concrete numbers make the A→B journey a weight-loss trajectory so the
    ``_end_reached`` direction logic (``current <= end + tolerance``) is easy to
    reason about in each scenario.
    """
    user = User(email=email, password_hash="x", is_admin=False)
    db.add(user)
    await db.flush()

    profile = FitnessProfile(
        user_id=user.id,
        weight_kg=80.0,
        height_cm=175.0,
        age=30,
        sex="male",
        level="principiante",
        equipment="[]",
        days_per_week=3,
        minutes_per_session=45,
        goal_type="weight_target",
        target_weight_kg=75.0,
        target_date=(date.today() + timedelta(weeks=8)).isoformat(),
    )
    db.add(profile)
    await db.flush()

    await goal_wizard_service.derive_and_persist_plan(db, user.id)
    await db.flush()
    return user


def _phase(index, start, end, status, *, weeks=2.0, start_date=None,
           maintenance=False):
    """Build one phase dict with deterministic nutrition targets.

    The targets are placeholders; phase advancement re-derives them from the
    current weight for any phase it activates, so their exact values don't drive
    the transitions under test.
    """
    return {
        "index": index,
        "start_weight": start,
        "end_weight": end,
        "weeks": weeks,
        "status": status,
        "start_date": start_date,
        "end_date": None,
        "maintenance": maintenance,
        "kcal": 2000.0,
        "protein_g": 150.0,
        "fat_g": 60.0,
        "carbs_g": 200.0,
    }


async def _set_phases(db: AsyncSession, user_id: int,
                      phases: list[dict]) -> DietPhasePlan:
    """Overwrite the user's active plan phases with a hand-built layout and
    reset goal_reached, for a fully deterministic scenario."""
    plan = await goal_wizard_service.get_active_phase_plan(db, user_id)
    assert plan is not None
    plan.phases = json.dumps(phases, ensure_ascii=False)
    plan.goal_reached = False
    plan.start_weight_kg = phases[0]["start_weight"]
    plan.target_weight_kg = phases[-1]["end_weight"]
    await db.flush()
    await db.commit()
    return plan


def _statuses(phases: list[dict]) -> list[str]:
    return [p["status"] for p in phases]


# ── Scenario runners ─────────────────────────────────────────────────────────
async def _scenario_single_advance() -> None:
    """Req 7.1/7.2: a weigh-in reaching the active phase end advances to the next
    phase, which is re-anchored to the current weight."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                          expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user = await _seed_user_with_plan(db, "advance@example.com")
            # Two phases: 80→77.5 (active), 77.5→75 (pending).
            await _set_phases(db, user.id, [
                _phase(0, 80.0, 77.5, "active"),
                _phase(1, 77.5, 75.0, "pending"),
            ])

            app = _build_app(db)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://test") as client:
                head = _auth(user)
                # Weigh-in exactly at phase-0 end → reached within tolerance.
                res = await client.post(
                    "/api/goal-plan/weight", headers=head,
                    json={"weight_kg": 77.5,
                          "entry_date": date.today().isoformat()},
                )
                assert res.status_code == 200
                body = res.json()
                phases = body["phases"]

                # Phase 0 completed, phase 1 now active (advanced by exactly one).
                assert _statuses(phases) == ["completed", "active"]
                assert body["goal_reached"] is False
                assert body["active_phase"]["index"] == 1
                # The newly activated phase was re-anchored to the current weight
                # (Req 7.2: re-derive from the user's current weight).
                assert phases[1]["start_weight"] == pytest.approx(77.5)
                assert phases[1]["end_weight"] == pytest.approx(75.0)

                # Req 7.6: the advance is persisted — a fresh read agrees.
                reread = (await client.get("/api/goal-plan/phases",
                                           headers=head)).json()
                assert _statuses(reread["phases"]) == ["completed", "active"]
                assert reread["active_phase"]["index"] == 1
    finally:
        await engine.dispose()


async def _scenario_multi_overshoot() -> None:
    """Req 7.4: a weigh-in overshooting several phase ends completes all reached
    phases and activates the first remaining pending phase."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                          expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user = await _seed_user_with_plan(db, "overshoot@example.com")
            # Three phases: 80→77.5 (active), 77.5→75 (pending), 75→72.5 (pending).
            await _set_phases(db, user.id, [
                _phase(0, 80.0, 77.5, "active"),
                _phase(1, 77.5, 75.0, "pending"),
                _phase(2, 75.0, 72.5, "pending"),
            ])

            app = _build_app(db)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://test") as client:
                head = _auth(user)
                # Weigh-in 74.0 overshoots phase 0 (end 77.5) and phase 1
                # (end 75.0, since 74.0 <= 75.5), but NOT phase 2 (end 72.5,
                # since 74.0 > 73.0). Expect phases 0 and 1 completed, phase 2
                # active, re-anchored to 74.0.
                res = await client.post(
                    "/api/goal-plan/weight", headers=head,
                    json={"weight_kg": 74.0,
                          "entry_date": date.today().isoformat()},
                )
                assert res.status_code == 200
                body = res.json()
                phases = body["phases"]

                assert _statuses(phases) == ["completed", "completed", "active"]
                assert body["goal_reached"] is False
                assert body["active_phase"]["index"] == 2
                assert phases[2]["start_weight"] == pytest.approx(74.0)
                assert phases[2]["end_weight"] == pytest.approx(72.5)

                # Req 7.6: persisted across a re-read.
                reread = (await client.get("/api/goal-plan/phases",
                                           headers=head)).json()
                assert _statuses(reread["phases"]) == [
                    "completed", "completed", "active"]
    finally:
        await engine.dispose()


async def _scenario_insufficient_extends() -> None:
    """Req 7.3: once the active phase window has elapsed and the end is not
    reached, the active phase is EXTENDED (stays active), not advanced."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                          expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user = await _seed_user_with_plan(db, "extend@example.com")
            # Single active phase 80→75, planned for 4 weeks, started 5 weeks ago
            # so elapsed (~5 wk) >= weeks (4) → the extension path is eligible.
            started = (date.today() - timedelta(weeks=5)).isoformat()
            await _set_phases(db, user.id, [
                _phase(0, 80.0, 75.0, "active", weeks=4.0, start_date=started),
                _phase(1, 75.0, 70.0, "pending"),
            ])

            app = _build_app(db)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://test") as client:
                head = _auth(user)
                # Weigh-in 79.0: NOT reached (79.0 > 75.5), but the window has
                # elapsed → extend the active phase, re-anchored to 79.0.
                res = await client.post(
                    "/api/goal-plan/weight", headers=head,
                    json={"weight_kg": 79.0,
                          "entry_date": date.today().isoformat()},
                )
                assert res.status_code == 200
                body = res.json()
                phases = body["phases"]

                # Phase 0 is still active (extended), phase 1 still pending — no
                # advance happened.
                assert _statuses(phases) == ["active", "pending"]
                assert body["goal_reached"] is False
                assert body["active_phase"]["index"] == 0
                # Extension re-anchors the active phase start to the current
                # weight while keeping the same end target (Req 7.3).
                assert phases[0]["start_weight"] == pytest.approx(79.0)
                assert phases[0]["end_weight"] == pytest.approx(75.0)

                # Req 7.6: persisted across a re-read.
                reread = (await client.get("/api/goal-plan/phases",
                                           headers=head)).json()
                assert _statuses(reread["phases"]) == ["active", "pending"]
                assert reread["active_phase"]["start_weight"] == pytest.approx(79.0)
    finally:
        await engine.dispose()


async def _scenario_last_phase_maintenance() -> None:
    """Req 7.5: reaching the end of the LAST phase produces an active maintenance
    phase and sets goal_reached=True."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                          expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user = await _seed_user_with_plan(db, "maintain@example.com")
            # Single (last) active phase 80→75.
            await _set_phases(db, user.id, [
                _phase(0, 80.0, 75.0, "active"),
            ])

            app = _build_app(db)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://test") as client:
                head = _auth(user)
                # Weigh-in 75.0 reaches the last phase end → maintenance.
                res = await client.post(
                    "/api/goal-plan/weight", headers=head,
                    json={"weight_kg": 75.0,
                          "entry_date": date.today().isoformat()},
                )
                assert res.status_code == 200
                body = res.json()
                phases = body["phases"]

                # The original phase is completed and a maintenance phase was
                # appended as the active one.
                assert phases[0]["status"] == "completed"
                maint = phases[-1]
                assert maint["maintenance"] is True
                assert maint["status"] == "active"
                assert maint["start_weight"] == pytest.approx(75.0)
                assert maint["end_weight"] == pytest.approx(75.0)
                assert body["goal_reached"] is True
                assert body["active_phase"]["maintenance"] is True

                # Req 7.6: goal_reached + maintenance persist across a re-read,
                # and the DB row records the reached goal.
                reread = (await client.get("/api/goal-plan/phases",
                                           headers=head)).json()
                assert reread["goal_reached"] is True
                assert reread["active_phase"]["maintenance"] is True

                plan = await goal_wizard_service.get_active_phase_plan(db, user.id)
                assert plan.goal_reached is True
    finally:
        await engine.dispose()


# ── Tests ────────────────────────────────────────────────────────────────────
def test_weighin_reaching_phase_end_advances_to_next_phase():
    """Req 7.1/7.2: a weigh-in at the active phase end completes it and activates
    (re-anchoring) the next pending phase."""
    asyncio.run(_scenario_single_advance())


def test_weighin_overshooting_several_phases_activates_first_remaining_pending():
    """Req 7.4: a weigh-in past several phase ends completes all reached phases
    and activates the first remaining pending phase."""
    asyncio.run(_scenario_multi_overshoot())


def test_insufficient_progress_after_window_extends_active_phase():
    """Req 7.3: when the phase window has elapsed without reaching the end, the
    active phase is extended rather than advanced."""
    asyncio.run(_scenario_insufficient_extends())


def test_reaching_last_phase_end_produces_active_maintenance_and_goal_reached():
    """Req 7.5/7.6: completing the last phase yields an active maintenance phase
    with goal_reached=True, persisted for later reads."""
    asyncio.run(_scenario_last_phase_maintenance())
