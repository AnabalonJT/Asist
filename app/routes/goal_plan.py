"""Goal_Wizard API routes (prefix /api/goal-plan set in main.py).

The Goal_Wizard guides an Authenticated_User from a current weight A to a target
weight B with a progressive, phased diet and a part-by-part generated routine.
It orchestrates the pure phase logic of ``goal_wizard_service`` on top of the
verified ``fitness_service`` / ``meal_service`` helpers.

All endpoints require an Authenticated_User via ``get_current_user`` and scope
every query to ``current_user.id`` (Req 12.1-12.4). Internal service exceptions
are translated to ``HTTPException`` with Spanish ``detail`` messages, following
the Error Handling table of the design. Responses carrying Phase_Targets or a
routine always include the Spanish medical disclaimer (Req 12.5).
"""
import json
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.middleware import get_current_user
from app.models.fitness_profile import FitnessProfile
from app.models.user import User
from app.services import fitness_service
from app.services import goal_wizard_service
from app.services import meal_service
from app.services.fitness_service import (
    EquipmentError,
    GoalRequiredError,
    LLMError,
    ValidationError,
)

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────
class WizardStateOut(BaseModel):
    step: str
    profile_complete: bool
    has_goal: bool
    has_plan: bool
    has_routine: bool


class ProfileIn(BaseModel):
    weight_kg: float
    height_cm: float
    age: int
    sex: str | None = None
    level: str
    days_per_week: int
    minutes_per_session: int


class ProfileOut(BaseModel):
    weight_kg: float
    height_cm: float
    age: int
    sex: str | None = None
    level: str
    days_per_week: int
    minutes_per_session: int


class GoalIn(BaseModel):
    target_weight_kg: float
    target_date: str


class GoalOut(BaseModel):
    goal_type: str
    target_weight_kg: float | None = None
    target_date: str | None = None
    target_rate: dict | None = None
    disclaimer: str


class EquipmentIn(BaseModel):
    equipment: list[str]


class EquipmentOut(BaseModel):
    equipment: list[str]


class TrainingDaysIn(BaseModel):
    days_per_week: int


class TrainingDaysOut(BaseModel):
    days_per_week: int


class PhaseOut(BaseModel):
    index: int
    start_weight: float
    end_weight: float
    weeks: float
    kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    status: str
    maintenance: bool


class PhasePlanOut(BaseModel):
    phases: list[PhaseOut]
    active_phase: PhaseOut | None = None
    goal_reached: bool
    disclaimer: str


class TargetsIn(BaseModel):
    kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float


class WeightIn(BaseModel):
    weight_kg: float
    entry_date: str


class WorkoutPlanOut(BaseModel):
    id: int
    goal_type: str
    structure: list
    disclaimer: str


class WorkoutPlanIn(BaseModel):
    structure: list


class RoutineChunkIn(BaseModel):
    """One block of a chunked routine generation request. The GoalWizard sends
    ``chunk_count`` requests with ``chunk_index`` 0..n-1 so the free LLM returns
    small, non-truncated JSON and the user sees real per-block progress."""

    chunk_index: int
    chunk_count: int


# ── Helpers ──────────────────────────────────────────────────────────────────
def _profile_dict(profile: FitnessProfile | None) -> dict | None:
    """Build the plain dict the pure wizard helpers consume from a profile."""
    if profile is None:
        return None
    return {
        "weight_kg": profile.weight_kg,
        "height_cm": profile.height_cm,
        "age": profile.age,
        "sex": profile.sex,
        "level": profile.level,
        "days_per_week": profile.days_per_week,
        "minutes_per_session": profile.minutes_per_session,
        "goal_type": profile.goal_type,
        "target_weight_kg": profile.target_weight_kg,
        "target_date": profile.target_date,
        "equipment": profile.equipment_list(),
    }


def _phase_plan_out(view: dict) -> PhasePlanOut:
    """Build a ``PhasePlanOut`` from a plan view dict (phases/active/goal)."""
    return PhasePlanOut(
        phases=view["phases"],
        active_phase=view.get("active_phase"),
        goal_reached=view.get("goal_reached", False),
        disclaimer=goal_wizard_service.DISCLAIMER,
    )


def _plan_to_view(plan) -> dict:
    """Build a plan view dict from a persisted ``DietPhasePlan``."""
    phases = plan.phases_list()
    return {
        "phases": phases,
        "active_phase": plan.active_phase(),
        "goal_reached": plan.goal_reached,
    }


# ── Wizard state (Req 1.2, 1.5, 1.6) ─────────────────────────────────────────
@router.get("/state", response_model=WizardStateOut)
async def get_state(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await fitness_service._get_profile(db, current_user.id)
    profile_dict = _profile_dict(profile)

    plan = await goal_wizard_service.get_active_phase_plan(db, current_user.id)
    plan_dict = {"phases": plan.phases_list()} if plan is not None else None

    routine = await fitness_service.get_active_plan(db, current_user.id)
    has_routine = routine is not None

    step = goal_wizard_service.resolve_wizard_step(
        profile_dict, plan_dict, has_routine
    )
    return WizardStateOut(
        step=step,
        profile_complete=goal_wizard_service.is_profile_complete(profile_dict),
        has_goal=bool(profile_dict and profile_dict.get("goal_type")),
        has_plan=plan is not None,
        has_routine=has_routine,
    )


# ── Profile (Req 2.1-2.4) ────────────────────────────────────────────────────
@router.put("/profile", response_model=ProfileOut)
async def put_profile(
    body: ProfileIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        fitness_service.validate_profile_fields(
            weight_kg=body.weight_kg,
            height_cm=body.height_cm,
            age=body.age,
            level=body.level,
            days_per_week=body.days_per_week,
            minutes_per_session=body.minutes_per_session,
            sex=body.sex,
            equipment=[],
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    profile = await fitness_service._get_profile(db, current_user.id)
    if profile is None:
        profile = FitnessProfile(
            user_id=current_user.id,
            weight_kg=body.weight_kg,
            height_cm=body.height_cm,
            age=body.age,
            sex=body.sex,
            level=body.level,
            equipment="[]",
            days_per_week=body.days_per_week,
            minutes_per_session=body.minutes_per_session,
        )
        db.add(profile)
    else:
        profile.weight_kg = body.weight_kg
        profile.height_cm = body.height_cm
        profile.age = body.age
        profile.sex = body.sex
        profile.level = body.level
        profile.days_per_week = body.days_per_week
        profile.minutes_per_session = body.minutes_per_session

    await db.flush()
    return ProfileOut(
        weight_kg=profile.weight_kg,
        height_cm=profile.height_cm,
        age=profile.age,
        sex=profile.sex,
        level=profile.level,
        days_per_week=profile.days_per_week,
        minutes_per_session=profile.minutes_per_session,
    )


# ── Goal (Req 3.1-3.4) ───────────────────────────────────────────────────────
@router.put("/goal", response_model=GoalOut)
async def put_goal(
    body: GoalIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        fitness_service.validate_goal_fields(
            goal_type="weight_target",
            target_weight_kg=body.target_weight_kg,
            target_date=body.target_date,
            performance_target=None,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    profile = await fitness_service._get_profile(db, current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primero crea tu perfil.",
        )

    profile.goal_type = "weight_target"
    profile.target_weight_kg = body.target_weight_kg
    profile.target_date = body.target_date

    target = fitness_service._parse_iso_date(body.target_date)
    days_remaining = (target - date.today()).days
    weeks = max(1, days_remaining / 7.0)
    try:
        target_rate = fitness_service.compute_target_rate(
            current_weight=profile.weight_kg,
            target_weight=body.target_weight_kg,
            weeks=weeks,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    await db.flush()
    return GoalOut(
        goal_type="weight_target",
        target_weight_kg=body.target_weight_kg,
        target_date=body.target_date,
        target_rate=target_rate,
        disclaimer=goal_wizard_service.DISCLAIMER,
    )


# ── Equipment (Req 4.1-4.3) ──────────────────────────────────────────────────
@router.put("/equipment", response_model=EquipmentOut)
async def put_equipment(
    body: EquipmentIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for item in body.equipment:
        if item not in fitness_service.EQUIPMENT_CATALOG:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El equipo '{item}' no está en el catálogo.",
            )

    profile = await fitness_service._get_profile(db, current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primero crea tu perfil.",
        )

    profile.equipment = json.dumps(list(body.equipment), ensure_ascii=False)
    await db.flush()
    return EquipmentOut(equipment=profile.equipment_list())


# ── Derive phases (Req 5, 6) ─────────────────────────────────────────────────
@router.post("/phases/derive", response_model=PhasePlanOut)
async def derive_phases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        plan = await goal_wizard_service.derive_and_persist_plan(
            db, current_user.id
        )
    except GoalRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return _phase_plan_out(_plan_to_view(plan))


# ── Query phases (Req 11.2, 11.3) ────────────────────────────────────────────
@router.get("/phases")
async def get_phases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await goal_wizard_service.get_active_phase_plan(db, current_user.id)
    if plan is None:
        return {
            "message": "No tienes un plan de fases activo. "
                       "Inicia el asistente para crearlo."
        }
    return _phase_plan_out(_plan_to_view(plan))


# ── Training days (Req 8.1-8.3) ──────────────────────────────────────────────
@router.put("/training-days", response_model=TrainingDaysOut)
async def put_training_days(
    body: TrainingDaysIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not (1 <= body.days_per_week <= 7):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los días de entrenamiento deben estar entre 1 y 7.",
        )

    profile = await fitness_service._get_profile(db, current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primero crea tu perfil.",
        )

    profile.days_per_week = body.days_per_week
    await db.flush()
    return TrainingDaysOut(days_per_week=profile.days_per_week)


# ── Routine generation (Req 9.1-9.6) ─────────────────────────────────────────
@router.post("/routine/generate", response_model=WorkoutPlanOut)
async def generate_routine(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        plan = await goal_wizard_service.generate_routine(db, current_user.id)
    except GoalRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LLMError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No pudimos generar tu rutina en este momento. Intenta de nuevo.",
        )
    except EquipmentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        # Defense in depth: never surface a raw 500. Any unexpected failure during
        # routine generation becomes a friendly retryable error in Spanish.
        logging.getLogger(__name__).exception(
            "Unexpected error generating routine for user_id=%s", current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No pudimos generar tu rutina en este momento. Intenta de nuevo.",
        )

    return WorkoutPlanOut(
        id=plan.id,
        goal_type=plan.goal_type,
        structure=plan.structure_list(),
        disclaimer=goal_wizard_service.DISCLAIMER,
    )


@router.post("/routine/generate-chunk", response_model=WorkoutPlanOut)
async def generate_routine_chunk(
    body: RoutineChunkIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate ONE block of the routine. Called ``chunk_count`` times by the
    wizard (chunk_index 0..n-1); each call returns the accumulated plan so far."""
    try:
        plan = await goal_wizard_service.generate_routine_chunk(
            db, current_user.id,
            chunk_index=body.chunk_index, chunk_count=body.chunk_count,
        )
    except GoalRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LLMError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No pudimos generar este bloque de la rutina. Intenta de nuevo.",
        )
    except EquipmentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        logging.getLogger(__name__).exception(
            "Unexpected error generating routine chunk %s/%s for user_id=%s",
            body.chunk_index, body.chunk_count, current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No pudimos generar este bloque de la rutina. Intenta de nuevo.",
        )

    return WorkoutPlanOut(
        id=plan.id,
        goal_type=plan.goal_type,
        structure=plan.structure_list(),
        disclaimer=goal_wizard_service.DISCLAIMER,
    )


# ── Routine edition (Req 10.4, 10.5) ─────────────────────────────────────────
@router.put("/routine", response_model=WorkoutPlanOut)
async def put_routine(
    body: WorkoutPlanIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        fitness_service.validate_plan_structure(body.structure)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    plan = await fitness_service.get_active_plan(db, current_user.id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tienes una rutina activa para editar.",
        )

    plan.structure = json.dumps(body.structure, ensure_ascii=False)
    await db.flush()
    return WorkoutPlanOut(
        id=plan.id,
        goal_type=plan.goal_type,
        structure=plan.structure_list(),
        disclaimer=goal_wizard_service.DISCLAIMER,
    )


# ── Active phase targets edition (Req 10.2, 10.3) ────────────────────────────
@router.put("/phases/active/targets", response_model=PhasePlanOut)
async def put_active_targets(
    body: TargetsIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await goal_wizard_service.edit_active_phase_targets(
            db,
            current_user.id,
            kcal=body.kcal,
            protein_g=body.protein_g,
            fat_g=body.fat_g,
            carbs_g=body.carbs_g,
        )
    except meal_service.ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except GoalRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    plan = await goal_wizard_service.get_active_phase_plan(db, current_user.id)
    return _phase_plan_out(_plan_to_view(plan))


# ── Weight register & phase advance (Req 7.1-7.6) ────────────────────────────
@router.post("/weight")
async def post_weight(
    body: WeightIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await goal_wizard_service.register_weight_and_advance(
            db, current_user.id, body.weight_kg, body.entry_date
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if "message" in result:
        return result
    return _phase_plan_out(result)
