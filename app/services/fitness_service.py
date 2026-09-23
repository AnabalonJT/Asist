"""Fitness Coach service: constants, exceptions and pure logic.

This module holds the pure, I/O-free building blocks of the Fitness_Coach:
field validation, target-rate computation and workout-plan structure/equipment
validation. Async, DB-backed functions live in later tasks. All user-facing
messages are in Spanish; identifiers and comments are in English.
"""
from datetime import date, datetime

# ── Equipment catalog & exercise → equipment map (Req 1.2, 1.7, 5.4) ─────────
EQUIPMENT_CATALOG: set[str] = {
    "mancuernas",
    "barra",
    "banco",
    "kettlebell",
    "bandas",
    "peso corporal",
    "acceso a gimnasio",
    "máquinas",
}

# Default equipment when an exercise is unknown: "peso corporal" (bodyweight).
DEFAULT_EQUIPMENT = "peso corporal"

# Required equipment per exercise keyword. Matching is by keyword contained in
# the (lowercased) exercise name; unknown exercises fall back to bodyweight.
EXERCISE_EQUIPMENT: dict[str, str] = {
    "press banca": "banco",
    "press de banca": "banco",
    "sentadilla con barra": "barra",
    "peso muerto": "barra",
    "hip thrust": "barra",
    "curl con mancuerna": "mancuernas",
    "press con mancuerna": "mancuernas",
    "swing": "kettlebell",
    "goblet": "kettlebell",
    "remo con banda": "bandas",
    "banda": "bandas",
    "prensa": "máquinas",
    "polea": "máquinas",
    "máquina": "máquinas",
    "flexiones": "peso corporal",
    "dominadas": "peso corporal",
    "plancha": "peso corporal",
    "fondos": "peso corporal",
}

VALID_LEVELS: set[str] = {"principiante", "intermedio", "avanzado"}
VALID_SEX: set[str] = {"male", "female", "other"}
VALID_GOAL_TYPES: set[str] = {
    "weight_target",
    "lose_weight",
    "gain_muscle",
    "maintain",
    "improve_endurance",
    "performance",
}

KCAL_PER_KG = 7700.0
ACTIVITY_WINDOW_DAYS = 28

MEDICAL_DISCLAIMER = (
    "Esta información es una estimación orientativa, no constituye consejo ni "
    "diagnóstico médico. Consulta a un profesional de la salud antes de iniciar "
    "un plan de entrenamiento o cambios en tu alimentación."
)


# ── Internal service exceptions ──────────────────────────────────────────────
class ValidationError(Exception):
    """Raised when a field is out of range or has an invalid format.

    The message is in Spanish and identifies the offending field.
    """


class EquipmentError(Exception):
    """Raised when a generated plan requires equipment the user does not have."""


class GoalRequiredError(Exception):
    """Raised when a routine is requested without a profile+goal defined."""


class LLMError(Exception):
    """Raised on LLM failures during plan generation.

    ``kind`` is one of "timeout" | "error" | "parse" (optional).
    """

    def __init__(self, message: str, kind: str | None = None):
        super().__init__(message)
        self.kind = kind


# ── Profile validation (Req 1) ───────────────────────────────────────────────
def validate_profile_fields(
    weight_kg: float,
    height_cm: float,
    age: int,
    level: str,
    days_per_week: int,
    minutes_per_session: int,
    sex: str | None,
    equipment: list[str],
) -> None:
    """Validate profile fields. Raise ``ValidationError`` (Spanish) identifying
    the invalid field and its valid range.

    Ranges: weight 30..300 kg, height 100..250 cm, age 13..100, days 1..7,
    minutes 10..240; level in VALID_LEVELS; sex None or in VALID_SEX;
    equipment ⊆ EQUIPMENT_CATALOG.
    """
    if weight_kg is None or not (30 <= weight_kg <= 300):
        raise ValidationError(
            "El peso actual debe estar entre 30 y 300 kg."
        )
    if height_cm is None or not (100 <= height_cm <= 250):
        raise ValidationError(
            "La altura debe estar entre 100 y 250 cm."
        )
    if age is None or not (13 <= age <= 100):
        raise ValidationError(
            "La edad debe estar entre 13 y 100 años."
        )
    if days_per_week is None or not (1 <= days_per_week <= 7):
        raise ValidationError(
            "Los días por semana deben estar entre 1 y 7."
        )
    if minutes_per_session is None or not (10 <= minutes_per_session <= 240):
        raise ValidationError(
            "Los minutos por sesión deben estar entre 10 y 240."
        )
    if level not in VALID_LEVELS:
        raise ValidationError(
            "El nivel es inválido; debe ser 'principiante', 'intermedio' o 'avanzado'."
        )
    if sex is not None and sex not in VALID_SEX:
        raise ValidationError(
            "El sexo es inválido; debe ser 'male', 'female' u 'other'."
        )
    for item in equipment or []:
        if item not in EQUIPMENT_CATALOG:
            raise ValidationError(
                f"El equipo '{item}' no pertenece al catálogo disponible."
            )


# ── Goal validation (Req 2) ──────────────────────────────────────────────────
def _parse_iso_date(value: str) -> date:
    """Parse an ISO 'YYYY-MM-DD' date string. Raise ValidationError (es) if invalid."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValidationError(
            "La fecha objetivo es inválida; usa el formato AAAA-MM-DD."
        )


def validate_goal_fields(
    goal_type: str,
    target_weight_kg: float | None,
    target_date: str | None,
    performance_target: str | None,
) -> None:
    """Validate goal fields. Raise ``ValidationError`` (Spanish) identifying the
    invalid or missing field.

    Checks: goal_type in VALID_GOAL_TYPES; if weight_target: target_weight in
    30..300 and target_date > today; if performance: performance_target length 1..200.
    """
    if goal_type not in VALID_GOAL_TYPES:
        raise ValidationError(
            "El tipo de objetivo es inválido."
        )

    if goal_type == "weight_target":
        if target_weight_kg is None or not (30 <= target_weight_kg <= 300):
            raise ValidationError(
                "El peso objetivo debe estar entre 30 y 300 kg."
            )
        if not target_date:
            raise ValidationError(
                "La fecha objetivo es obligatoria para un objetivo de peso."
            )
        parsed = _parse_iso_date(target_date)
        if parsed <= date.today():
            raise ValidationError(
                "La fecha objetivo debe ser posterior a la fecha actual."
            )

    if goal_type == "performance":
        if performance_target is None or not (1 <= len(performance_target) <= 200):
            raise ValidationError(
                "La descripción de la marca objetivo debe tener entre 1 y 200 caracteres."
            )


# ── Target rate (Req 3) — PURE, no I/O ───────────────────────────────────────
def compute_target_rate(
    current_weight: float,
    target_weight: float,
    weeks: float,
) -> dict:
    """Compute the weekly target rate and derived daily caloric delta (pure).

    Returns a dict with ``rate_kg_per_week``, ``daily_kcal_delta``, ``direction``,
    ``warning`` (bool), ``warning_message`` (str|None) and ``disclaimer``.

    Raise ``ValidationError`` if ``weeks < 1`` (includes 0) or if current/target
    weight is missing.
    """
    if current_weight is None or target_weight is None:
        raise ValidationError(
            "Faltan el peso actual o el peso objetivo para calcular el ritmo."
        )
    if weeks is None or weeks < 1:
        raise ValidationError(
            "El plazo debe ser de al menos 1 semana."
        )

    rate = round((target_weight - current_weight) / weeks, 2)
    daily_kcal_delta = round(abs(rate) * KCAL_PER_KG / 7)

    if rate < 0:
        direction = "déficit"
    elif rate > 0:
        direction = "superávit"
    else:
        direction = "mantenimiento"

    # Healthy_Rate_Threshold: |rate| > 1.0 kg/week OR |rate| > 1.0% of current/week.
    percent_threshold = current_weight * 0.01
    warning = abs(rate) > 1.0 or abs(rate) > percent_threshold

    warning_message: str | None = None
    if warning:
        warning_message = (
            "El ritmo objetivo es agresivo o poco realista para un cambio de peso "
            "saludable. Considera ampliar el plazo para alcanzar tu objetivo de "
            "forma más segura."
        )

    return {
        "rate_kg_per_week": rate,
        "daily_kcal_delta": daily_kcal_delta,
        "direction": direction,
        "warning": warning,
        "warning_message": warning_message,
        "disclaimer": MEDICAL_DISCLAIMER,
    }


# ── Plan structure & equipment validation (Req 5) — PURE ─────────────────────
def validate_plan_structure(structure: list[dict]) -> None:
    """Validate a workout plan structure. Raise ``ValidationError`` (Spanish) if:

    - not 1..7 days,
    - any day not 1..20 exercises,
    - any exercise name not 1..100 chars,
    - sets/reps XOR duration is violated (sets 1..20 with reps 1..100, OR
      duration 1..7200 s, but not both/neither),
    - rest not 0..3600 s.
    """
    if not isinstance(structure, list) or not (1 <= len(structure) <= 7):
        raise ValidationError(
            "La rutina debe contener entre 1 y 7 días."
        )

    for day in structure:
        exercises = day.get("exercises") if isinstance(day, dict) else None
        if not isinstance(exercises, list) or not (1 <= len(exercises) <= 20):
            raise ValidationError(
                "Cada día debe contener entre 1 y 20 ejercicios."
            )

        for exercise in exercises:
            if not isinstance(exercise, dict):
                raise ValidationError(
                    "Cada ejercicio debe ser un objeto válido."
                )

            name = exercise.get("name")
            if not isinstance(name, str) or not (1 <= len(name) <= 100):
                raise ValidationError(
                    "El nombre de cada ejercicio debe tener entre 1 y 100 caracteres."
                )

            sets = exercise.get("sets")
            reps = exercise.get("reps")
            duration = exercise.get("duration_seconds")

            has_sets_reps = sets is not None and reps is not None
            has_duration = duration is not None

            # XOR: exactly one of {sets+reps, duration}.
            if has_sets_reps == has_duration:
                raise ValidationError(
                    "Cada ejercicio debe definir series y repeticiones, o bien una "
                    "duración, pero no ambos ni ninguno."
                )

            if has_sets_reps:
                if not (1 <= sets <= 20):
                    raise ValidationError(
                        "Las series de cada ejercicio deben estar entre 1 y 20."
                    )
                if not (1 <= reps <= 100):
                    raise ValidationError(
                        "Las repeticiones de cada ejercicio deben estar entre 1 y 100."
                    )
            else:  # has_duration
                if not (1 <= duration <= 7200):
                    raise ValidationError(
                        "La duración de cada ejercicio debe estar entre 1 y 7200 segundos."
                    )

            rest = exercise.get("rest_seconds")
            if rest is None or not (0 <= rest <= 3600):
                raise ValidationError(
                    "El descanso de cada ejercicio debe estar entre 0 y 3600 segundos."
                )


def required_equipment(exercise_name: str) -> str:
    """Return the equipment keyword required for an exercise.

    Matches by keyword contained in the lowercased name; unknown exercises fall
    back to ``DEFAULT_EQUIPMENT`` ("peso corporal").
    """
    if not exercise_name:
        return DEFAULT_EQUIPMENT
    name = exercise_name.lower()
    for keyword, equipment in EXERCISE_EQUIPMENT.items():
        if keyword in name:
            return equipment
    return DEFAULT_EQUIPMENT


def validate_plan_equipment(structure: list[dict], available: list[str]) -> None:
    """Raise ``EquipmentError`` (Spanish, offers retry) if any exercise requires
    equipment not present in ``available``.

    "peso corporal" (bodyweight) never requires equipment and is always allowed.
    """
    available_set = set(available or [])
    for day in structure:
        for exercise in day.get("exercises", []):
            needed = required_equipment(exercise.get("name", ""))
            if needed == DEFAULT_EQUIPMENT:
                continue
            if needed not in available_set:
                raise EquipmentError(
                    "La rutina generada usa equipo que no tienes disponible. "
                    "Intenta generarla de nuevo."
                )


def clamp_days_to_availability(
    structure: list[dict], days_per_week: int
) -> list[dict]:
    """Trim the plan to at most ``days_per_week`` days.

    Returns the first ``min(len(days), days_per_week)`` days.
    """
    if not structure:
        return structure
    limit = min(len(structure), max(0, days_per_week))
    return structure[:limit]


# ── Async, DB-backed functions (Tasks 4.1, 4.3, 4.6, 6.1) ────────────────────
import json
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.fitness_profile import FitnessProfile
from app.models.weight_entry import WeightEntry
from app.models.workout_plan import WorkoutPlan
from app.services import llm_service
from app.services.activity_types import normalize_activity_type


async def _get_profile(db: AsyncSession, user_id: int) -> FitnessProfile | None:
    """Load the FitnessProfile for a user, or None."""
    result = await db.execute(
        select(FitnessProfile).where(FitnessProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


# ── Activity summary (Req 4.1-4.4) ───────────────────────────────────────────
async def build_activity_summary(
    db: AsyncSession,
    user_id: int,
    window_days: int = ACTIVITY_WINDOW_DAYS,
) -> dict:
    """Aggregate the user's Activity over the last ``window_days`` days.

    Returns ``{"frequency": int, "total_minutes": int, "types": list[str]}``.
    ``frequency`` counts every Activity in the window (including those without a
    duration); ``total_minutes`` sums ``duration_minutes`` treating ``None`` as 0;
    ``types`` is the list of distinct activity types present in the window. With no
    activities in the window → ``{"frequency": 0, "total_minutes": 0, "types": []}``.
    """
    window_start = datetime.utcnow() - timedelta(days=window_days)
    result = await db.execute(
        select(Activity).where(
            Activity.user_id == user_id,
            Activity.timestamp >= window_start,
        )
    )
    activities = result.scalars().all()

    frequency = len(activities)
    total_minutes = sum(a.duration_minutes or 0 for a in activities)
    types: list[str] = []
    for a in activities:
        if a.activity_type is not None and a.activity_type not in types:
            types.append(a.activity_type)

    return {
        "frequency": frequency,
        "total_minutes": int(total_minutes),
        "types": types,
    }


# ── Weight entries (Req 7.1-7.5) ─────────────────────────────────────────────
async def add_weight_entry(
    db: AsyncSession,
    user_id: int,
    weight_kg: float,
    entry_date: str,
) -> WeightEntry:
    """Create a Weight_Entry after validating the weight range (30..300 kg).

    Raise ``ValidationError`` (Spanish, with the valid range) if out of range. If
    ``entry_date`` is the most recent among the user's entries, update the current
    weight of the user's FitnessProfile (when a profile exists).
    """
    if weight_kg is None or not (30 <= weight_kg <= 300):
        raise ValidationError(
            "El peso registrado debe estar entre 30 y 300 kg."
        )

    entry = WeightEntry(
        user_id=user_id,
        weight_kg=weight_kg,
        entry_date=entry_date,
    )
    db.add(entry)
    await db.flush()

    # If this is the most recent entry date, sync the profile's current weight.
    result = await db.execute(
        select(func.max(WeightEntry.entry_date)).where(
            WeightEntry.user_id == user_id
        )
    )
    latest_date = result.scalar()
    if latest_date is not None and entry_date >= latest_date:
        profile = await _get_profile(db, user_id)
        if profile is not None:
            profile.weight_kg = weight_kg
            await db.flush()

    return entry


async def list_weight_entries(db: AsyncSession, user_id: int) -> list[WeightEntry]:
    """Return the user's Weight_Entry records ordered ascending by ``entry_date``.

    Empty list if the user has no entries.
    """
    result = await db.execute(
        select(WeightEntry)
        .where(WeightEntry.user_id == user_id)
        .order_by(WeightEntry.entry_date.asc())
    )
    return list(result.scalars().all())


# ── Progress & adherence (Req 8.1-8.5) ───────────────────────────────────────
async def get_progress(db: AsyncSession, user_id: int) -> dict:
    """Return the user's weight progress.

    ``{"series": [{"date": entry_date, "weight_kg": w}, ...] asc by date,
       "target_weight_kg": float | None}``. ``target_weight_kg`` is included only
    when the user's FitnessProfile has ``goal_type == "weight_target"``.
    """
    entries = await list_weight_entries(db, user_id)
    series = [
        {"date": e.entry_date, "weight_kg": e.weight_kg} for e in entries
    ]

    target_weight_kg: float | None = None
    profile = await _get_profile(db, user_id)
    if profile is not None and profile.goal_type == "weight_target":
        target_weight_kg = profile.target_weight_kg

    return {"series": series, "target_weight_kg": target_weight_kg}


async def compute_adherence(db: AsyncSession, user_id: int) -> dict:
    """Compute adherence to the user's active Workout_Plan.

    No active plan → ``{"available": False, "message": <es>}``. If the active plan
    has zero planned sessions → ``{"available": False, "message": <es>}`` (avoids a
    division by zero). Otherwise → ``{"available": True, "completed": int,
    "planned": int, "ratio": round(completed/planned, 2)}`` where ``completed`` is
    the number of Activity records logged in the plan's period (from the plan's
    ``created_at`` to now).
    """
    plan = await get_active_plan(db, user_id)
    if plan is None:
        return {
            "available": False,
            "message": "No hay una rutina activa; no se puede calcular la adherencia todavía.",
        }

    planned = len(plan.structure_list())
    if planned == 0:
        return {
            "available": False,
            "message": "La rutina activa no tiene sesiones planificadas; no se puede calcular la adherencia.",
        }

    result = await db.execute(
        select(func.count())
        .select_from(Activity)
        .where(
            Activity.user_id == user_id,
            Activity.timestamp >= plan.created_at,
        )
    )
    completed = int(result.scalar() or 0)

    return {
        "available": True,
        "completed": completed,
        "planned": planned,
        "ratio": round(completed / planned, 2),
    }


# ── Workout plan generation & active plan (Req 5, 6, 10.4, 10.5) ─────────────
async def get_active_plan(db: AsyncSession, user_id: int) -> WorkoutPlan | None:
    """Return the user's active Workout_Plan, or None."""
    result = await db.execute(
        select(WorkoutPlan).where(
            WorkoutPlan.user_id == user_id,
            WorkoutPlan.active == True,  # noqa: E712 (SQLAlchemy boolean filter)
        )
    )
    return result.scalars().first()


async def generate_workout_plan(
    db: AsyncSession,
    user_id: int,
    overrides: dict | None = None,
) -> WorkoutPlan:
    """Generate and persist a Workout_Plan for the user.

    Loads the FitnessProfile (missing profile or goal → ``GoalRequiredError``).
    Optional ``overrides`` (``goal_type``, ``equipment``, ``days_per_week``) are
    applied over a copy of the profile data WITHOUT persisting them onto the
    profile. Builds the Activity_Summary, calls the LLM_Service (60s timeout),
    parses and validates the returned structure, clamps to the available days and
    validates equipment.

    On ANY failure (``LLMError`` for timeout/error/parse, or ``EquipmentError`` for
    unavailable equipment) the previous active plan, profile and goal are left
    untouched. On success the previous active plan is deactivated, the new plan is
    persisted as active and returned.
    """
    overrides = overrides or {}

    profile = await _get_profile(db, user_id)
    if profile is None or not profile.goal_type:
        raise GoalRequiredError(
            "Primero completa tu perfil y objetivo para generar una rutina."
        )

    # Effective values (overrides win, but are NOT persisted onto the profile).
    effective_goal_type = overrides.get("goal_type") or profile.goal_type
    effective_equipment = overrides.get("equipment")
    if effective_equipment is None:
        effective_equipment = profile.equipment_list()
    effective_days = overrides.get("days_per_week") or profile.days_per_week

    activity_summary = await build_activity_summary(db, user_id)

    profile_dict = {
        "equipment": effective_equipment,
        "days_per_week": effective_days,
        "level": profile.level,
    }
    goal_dict = {
        "goal_type": effective_goal_type,
        "performance_target": profile.performance_target,
        "target_weight_kg": profile.target_weight_kg,
        "target_date": profile.target_date,
    }

    parsed = await llm_service.generate_workout_plan(
        profile_dict, goal_dict, activity_summary, timeout_seconds=60.0
    )
    if parsed is None:
        raise LLMError(
            "No pudimos generar tu rutina en este momento. Intenta de nuevo.",
            kind="error",
        )

    # Extract the list of days: LLM returns {"days": [...]}, tolerate a raw list.
    if isinstance(parsed, dict):
        days = parsed.get("days", [])
    elif isinstance(parsed, list):
        days = parsed
    else:
        days = []

    if not isinstance(days, list) or not days:
        raise LLMError(
            "No pudimos interpretar la rutina generada. Intenta de nuevo.",
            kind="parse",
        )

    # Validate structure. Any ValidationError becomes an LLMError (parse) so the
    # previous plan stays untouched and the router can offer a retry.
    try:
        validate_plan_structure(days)
    except ValidationError:
        raise LLMError(
            "No pudimos interpretar la rutina generada. Intenta de nuevo.",
            kind="parse",
        )

    days = clamp_days_to_availability(days, effective_days)

    # Equipment validation propagates as EquipmentError (router translates it).
    # Nothing is persisted, so the previous plan/profile/goal remain intact.
    validate_plan_equipment(days, effective_equipment)

    # Success: deactivate the previous active plan and persist the new one.
    previous = await get_active_plan(db, user_id)
    if previous is not None:
        previous.active = False

    plan = WorkoutPlan(
        user_id=user_id,
        goal_type=effective_goal_type,
        structure=json.dumps(days, ensure_ascii=False),
        active=True,
    )
    db.add(plan)
    await db.flush()
    return plan


# ── Meal_Planner integration view (Req 3.5, 1.9) ─────────────────────────────
async def get_meal_planner_view(db: AsyncSession, user_id: int) -> dict | None:
    """Expose the profile view for the Meal_Planner, plus the target rate.

    Returns ``profile.meal_planner_view()`` merged with ``target_rate`` (computed
    via ``compute_target_rate`` using the weeks remaining until ``target_date``)
    when the goal is a ``weight_target`` with the required data. Returns ``None``
    when the user has no FitnessProfile.
    """
    profile = await _get_profile(db, user_id)
    if profile is None:
        return None

    view = profile.meal_planner_view()
    view["target_rate"] = None

    if (
        profile.goal_type == "weight_target"
        and profile.weight_kg is not None
        and profile.target_weight_kg is not None
        and profile.target_date
    ):
        try:
            target = _parse_iso_date(profile.target_date)
            days_remaining = (target - date.today()).days
            weeks = days_remaining / 7.0
            view["target_rate"] = compute_target_rate(
                profile.weight_kg, profile.target_weight_kg, weeks
            )
        except ValidationError:
            # Not enough runway (e.g. <1 week) or invalid date: leave target_rate None.
            view["target_rate"] = None

    return view
