"""Fitness Coach API routes (prefix /api/fitness set in main.py).

All endpoints require an Authenticated_User via ``get_current_user`` and scope
every query to ``current_user.id`` (Req 11.1-11.4). Internal service exceptions
are translated to ``HTTPException`` with Spanish ``detail`` messages, following
the Error Handling table of the design. Weight-goal and workout responses always
include the Spanish medical disclaimer (Req 3.5, 11.5).
"""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.middleware import get_current_user
from app.models.fitness_profile import FitnessProfile
from app.models.user import User
from app.services import fitness_service
from app.services.fitness_service import (
    EquipmentError,
    GoalRequiredError,
    LLMError,
    MEDICAL_DISCLAIMER,
    ValidationError,
)

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────
class ProfileIn(BaseModel):
    weight_kg: float
    height_cm: float
    age: int
    sex: str | None = None
    level: str
    equipment: list[str] = []
    days_per_week: int
    minutes_per_session: int


class FitnessProfileOut(BaseModel):
    weight_kg: float
    height_cm: float
    age: int
    sex: str | None = None
    level: str
    equipment: list[str] = []
    days_per_week: int
    minutes_per_session: int
    goal_type: str | None = None
    target_weight_kg: float | None = None
    target_date: str | None = None
    performance_target: str | None = None

    @classmethod
    def from_model(cls, p: FitnessProfile) -> "FitnessProfileOut":
        return cls(
            weight_kg=p.weight_kg,
            height_cm=p.height_cm,
            age=p.age,
            sex=p.sex,
            level=p.level,
            equipment=p.equipment_list(),
            days_per_week=p.days_per_week,
            minutes_per_session=p.minutes_per_session,
            goal_type=p.goal_type,
            target_weight_kg=p.target_weight_kg,
            target_date=p.target_date,
            performance_target=p.performance_target,
        )


class GoalIn(BaseModel):
    goal_type: str
    target_weight_kg: float | None = None
    target_date: str | None = None
    performance_target: str | None = None


class GoalOut(BaseModel):
    goal_type: str
    target_weight_kg: float | None = None
    target_date: str | None = None
    performance_target: str | None = None
    target_rate: dict | None = None
    disclaimer: str


class WeightIn(BaseModel):
    weight_kg: float
    entry_date: str


class WeightEntryOut(BaseModel):
    id: int
    weight_kg: float
    entry_date: str


class WorkoutPlanOut(BaseModel):
    id: int
    goal_type: str
    structure: list
    disclaimer: str


class ProgressOut(BaseModel):
    series: list
    target_weight_kg: float | None = None


class AdherenceOut(BaseModel):
    available: bool
    completed: int | None = None
    planned: int | None = None
    ratio: float | None = None
    message: str | None = None


# ── Profile (Req 1) ──────────────────────────────────────────────────────────
@router.get("/profile", response_model=FitnessProfileOut)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await fitness_service._get_profile(db, current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tienes un perfil fitness todavía.",
        )
    return FitnessProfileOut.from_model(profile)


@router.put("/profile", response_model=FitnessProfileOut)
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
            equipment=body.equipment,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    profile = await fitness_service._get_profile(db, current_user.id)
    equipment_json = json.dumps(list(body.equipment or []), ensure_ascii=False)

    if profile is None:
        profile = FitnessProfile(
            user_id=current_user.id,
            weight_kg=body.weight_kg,
            height_cm=body.height_cm,
            age=body.age,
            sex=body.sex,
            level=body.level,
            equipment=equipment_json,
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
        profile.equipment = equipment_json
        profile.days_per_week = body.days_per_week
        profile.minutes_per_session = body.minutes_per_session

    await db.flush()
    return FitnessProfileOut.from_model(profile)


# ── Goal (Req 2, 3) ──────────────────────────────────────────────────────────
@router.put("/goal", response_model=GoalOut)
async def put_goal(
    body: GoalIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        fitness_service.validate_goal_fields(
            goal_type=body.goal_type,
            target_weight_kg=body.target_weight_kg,
            target_date=body.target_date,
            performance_target=body.performance_target,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    profile = await fitness_service._get_profile(db, current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primero crea tu perfil fitness.",
        )

    profile.goal_type = body.goal_type
    profile.target_weight_kg = body.target_weight_kg
    profile.target_date = body.target_date
    profile.performance_target = body.performance_target

    target_rate: dict | None = None
    if body.goal_type == "weight_target":
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
        goal_type=body.goal_type,
        target_weight_kg=body.target_weight_kg,
        target_date=body.target_date,
        performance_target=body.performance_target,
        target_rate=target_rate,
        disclaimer=MEDICAL_DISCLAIMER,
    )


# ── Weight (Req 7) ───────────────────────────────────────────────────────────
@router.post("/weight", response_model=WeightEntryOut)
async def post_weight(
    body: WeightIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        entry = await fitness_service.add_weight_entry(
            db, current_user.id, body.weight_kg, body.entry_date
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return WeightEntryOut(
        id=entry.id, weight_kg=entry.weight_kg, entry_date=entry.entry_date
    )


@router.get("/weight", response_model=list[WeightEntryOut])
async def get_weight(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entries = await fitness_service.list_weight_entries(db, current_user.id)
    return [
        WeightEntryOut(id=e.id, weight_kg=e.weight_kg, entry_date=e.entry_date)
        for e in entries
    ]


# ── Plan generation & active plan (Req 5, 6) ─────────────────────────────────
@router.post("/plan/generate", response_model=WorkoutPlanOut)
async def generate_plan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        plan = await fitness_service.generate_workout_plan(db, current_user.id)
    except GoalRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LLMError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except EquipmentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return WorkoutPlanOut(
        id=plan.id,
        goal_type=plan.goal_type,
        structure=plan.structure_list(),
        disclaimer=MEDICAL_DISCLAIMER,
    )


@router.get("/plan")
async def get_plan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await fitness_service.get_active_plan(db, current_user.id)
    if plan is None:
        return {"message": "No tienes una rutina activa. Puedes generar una."}
    return WorkoutPlanOut(
        id=plan.id,
        goal_type=plan.goal_type,
        structure=plan.structure_list(),
        disclaimer=MEDICAL_DISCLAIMER,
    )


# ── Progress & adherence (Req 8) ─────────────────────────────────────────────
@router.get("/progress", response_model=ProgressOut)
async def get_progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await fitness_service.get_progress(db, current_user.id)
    return ProgressOut(
        series=data["series"], target_weight_kg=data["target_weight_kg"]
    )


@router.get("/adherence", response_model=AdherenceOut)
async def get_adherence(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await fitness_service.compute_adherence(db, current_user.id)
    return AdherenceOut(**data)
