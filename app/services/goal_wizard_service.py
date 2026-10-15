"""Goal_Wizard service — pure phase logic built on top of fitness_service and
meal_service.

This module implements the progressive A→B diet journey, split into discrete
phases. It reuses the verified business logic of ``fitness_service`` and the
pure helpers of ``meal_service`` instead of reimplementing them; it only adds
the phase-splitting logic and a body-aware ``phase_view``.

User-facing text is in Spanish; code identifiers and comments are in English.
"""

from app.services import fitness_service
from app.services import meal_service

# Reuse the internal service exceptions defined in fitness_service. They are
# imported (not redefined) so the router can translate them uniformly.
from app.services.fitness_service import (
    ValidationError,
    GoalRequiredError,
    EquipmentError,
    LLMError,
)

# ── Constants ────────────────────────────────────────────────────────────────
PHASE_MAX_KG = 2.5          # Phase_Size_Rule: <= 2.5 kg per phase
PHASE_MAX_WEEKS = 4.0       # Phase_Size_Rule: <= 4 weeks per phase
PHASE_TOLERANCE_KG = 0.5    # Phase_Tolerance
MIN_PHASE_WEEKS = 1.0       # minimum 1 week per phase

WIZARD_STEPS = ["profile", "goal", "equipment", "diet",
                "training_days", "routine", "summary"]

DISCLAIMER = fitness_service.MEDICAL_DISCLAIMER  # reuse the Spanish disclaimer


# ── Pure helpers ─────────────────────────────────────────────────────────────
def _is_number(value) -> bool:
    """True if value is a real number (int/float) and not a bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _build_phase_view(profile: dict, start_weight: float,
                      end_weight: float) -> dict:
    """Build the ``phase_view`` that both ``estimate_maintenance_kcal`` and
    ``derive_nutrition_targets`` consume. Combines the profile body data with the
    phase's current (start) and target (end) weight. Does NOT touch
    ``meal_planner_view()`` so the meal-planner dependency stays intact.
    """
    return {
        "weight_kg": start_weight,            # BMR input (estimate_maintenance_kcal)
        "current_weight_kg": start_weight,    # protein/kg input (derive_nutrition_targets)
        "height_cm": profile.get("height_cm"),
        "age": profile.get("age"),
        "sex": profile.get("sex"),
        "goal_type": "weight_target",
        "target_weight_kg": end_weight,
        "target_date": None,
    }


# ── Wizard step resolution (Req 1.2, 1.5, 1.6) ───────────────────────────────
def is_profile_complete(profile: dict | None) -> bool:
    """PURE. True iff weight_kg/height_cm/age/level/days_per_week/
    minutes_per_session are present and in range. Reuses
    ``fitness_service.validate_profile_fields`` for the range checks.
    """
    if not profile:
        return False
    try:
        fitness_service.validate_profile_fields(
            weight_kg=profile.get("weight_kg"),
            height_cm=profile.get("height_cm"),
            age=profile.get("age"),
            level=profile.get("level"),
            days_per_week=profile.get("days_per_week"),
            minutes_per_session=profile.get("minutes_per_session"),
            sex=profile.get("sex"),
            equipment=profile.get("equipment") or [],
        )
    except ValidationError:
        return False
    return True


def _has_goal(profile: dict | None) -> bool:
    """True iff the profile carries a defined goal_type."""
    return bool(profile and profile.get("goal_type"))


def _has_equipment(profile: dict | None) -> bool:
    """True iff the profile declares at least one equipment item."""
    return bool(profile and (profile.get("equipment") or []))


def _has_training_days(profile: dict | None) -> bool:
    """True iff days_per_week is present and in range (1..7)."""
    if not profile:
        return False
    days = profile.get("days_per_week")
    return _is_number(days) and 1 <= days <= 7


def _has_phases(plan: dict | None) -> bool:
    """True iff a derived phase plan with at least one phase exists."""
    return bool(plan and (plan.get("phases") or []))


def resolve_wizard_step(profile: dict | None, plan: dict | None,
                        has_routine: bool) -> str:
    """PURE. Return the first incomplete Wizard_Step in ``WIZARD_STEPS`` order.

    Order: profile → goal → equipment → diet → training_days → routine → summary.
    A step is incomplete when its required data is missing; the first such step is
    returned. When everything is complete the result is ``"summary"``.
    """
    if not is_profile_complete(profile):
        return "profile"
    if not _has_goal(profile):
        return "goal"
    if not _has_equipment(profile):
        return "equipment"
    if not _has_phases(plan):
        return "diet"
    if not _has_training_days(profile):
        return "training_days"
    if not has_routine:
        return "routine"
    return "summary"


# ── Phase splitting (Req 5.1-5.6) ────────────────────────────────────────────
def split_into_phases(
    start_weight: float, target_weight: float, rate_kg_per_week: float,
) -> list[dict]:
    """PURE. Split the A→B journey into ordered phases per Phase_Size_Rule.

    Each phase spans at most ``PHASE_MAX_KG`` (2.5 kg) OR ``PHASE_MAX_WEEKS``
    (4 wk), whichever comes first. Phase ``i`` start_weight == phase ``i-1``
    end_weight; phase 0 start == A; the last phase end == B exactly. If
    ``|A-B| <= PHASE_MAX_KG`` → exactly one phase ending at B. ``weeks`` per phase
    = ``max(|phase_change|/|rate|, MIN_PHASE_WEEKS)`` capped at ``PHASE_MAX_WEEKS``.
    Direction (lose vs gain) is inferred from ``sign(B-A)``.

    Returns a list of phase dicts WITHOUT nutrition targets (filled later by
    ``derive_phase_targets``). Raises ``ValidationError`` if A == B or rate == 0.
    """
    if start_weight is None or target_weight is None:
        raise ValidationError(
            "Faltan el peso inicial o el peso objetivo para dividir en fases."
        )
    if start_weight == target_weight:
        raise ValidationError(
            "El peso inicial y el objetivo no pueden ser iguales."
        )
    if not rate_kg_per_week:
        raise ValidationError(
            "El ritmo semanal no puede ser cero para dividir en fases."
        )

    total_change = target_weight - start_weight          # signed
    direction = 1.0 if total_change > 0 else -1.0        # +gain / -loss
    abs_rate = abs(rate_kg_per_week)

    # Per-phase change cap in kg: the smaller of PHASE_MAX_KG and the kg that fit
    # into PHASE_MAX_WEEKS at the given rate (so weeks per phase stay <= 4).
    kg_per_max_weeks = abs_rate * PHASE_MAX_WEEKS
    step_kg = min(PHASE_MAX_KG, kg_per_max_weeks)
    if step_kg <= 0:
        step_kg = PHASE_MAX_KG

    phases: list[dict] = []
    current_start = float(start_weight)
    index = 0
    # Guard against pathological loops; the number of phases is bounded by
    # |total_change| / step_kg rounded up, with a generous safety ceiling.
    remaining = abs(total_change)
    while remaining > 1e-9:
        phase_change = min(step_kg, remaining)           # magnitude for this phase
        current_end = current_start + direction * phase_change
        # Snap the final phase exactly to B (avoid float drift / overshoot).
        if phase_change >= remaining - 1e-9:
            current_end = float(target_weight)

        weeks = max(phase_change / abs_rate, MIN_PHASE_WEEKS)
        weeks = min(weeks, PHASE_MAX_WEEKS)

        phases.append({
            "index": index,
            "start_weight": round(current_start, 2),
            "end_weight": round(current_end, 2),
            "weeks": round(weeks, 2),
            "status": "active" if index == 0 else "pending",
            "start_date": None,
            "end_date": None,
            "maintenance": False,
            "kcal": None,
            "protein_g": None,
            "fat_g": None,
            "carbs_g": None,
        })

        remaining = abs(target_weight - current_end)
        current_start = current_end
        index += 1
        if index > 1000:  # safety ceiling; never expected in valid ranges
            break

    return phases


# ── Phase target derivation (Req 6.1-6.4) ────────────────────────────────────
def derive_phase_targets(profile: dict, phase: dict) -> dict:
    """PURE. Return a copy of ``phase`` with kcal/protein_g/fat_g/carbs_g filled.

    Builds a ``phase_view`` (body data + phase start_weight as current weight +
    phase end_weight as target) and a per-phase target_rate via
    ``fitness_service.compute_target_rate(start, end, weeks)``; then calls
    ``meal_service.derive_nutrition_targets(phase_view, target_rate)``.

    Deterministic (no LLM). Guarantees the macro post-condition inherited from
    ``derive_nutrition_targets``: ``|protein*4 + carbs*4 + fat*9 - kcal| <= 10``.
    """
    start_weight = phase.get("start_weight")
    end_weight = phase.get("end_weight")
    weeks = phase.get("weeks") or MIN_PHASE_WEEKS

    phase_view = _build_phase_view(profile, start_weight, end_weight)

    target_rate = fitness_service.compute_target_rate(
        start_weight, end_weight, weeks
    )
    targets = meal_service.derive_nutrition_targets(phase_view, target_rate)

    result = dict(phase)
    result["kcal"] = targets["kcal"]
    result["protein_g"] = targets["protein_g"]
    result["fat_g"] = targets["fat_g"]
    result["carbs_g"] = targets["carbs_g"]
    return result


def maintenance_phase(profile: dict, target_weight: float) -> dict:
    """PURE. Build a final maintenance phase at weight B.

    Direction mantenimiento: ``derive_nutrition_targets`` with no deficit/surplus
    (a ``maintain`` goal). ``status='active'``, ``maintenance=True``.
    """
    phase_view = _build_phase_view(profile, target_weight, target_weight)
    phase_view["goal_type"] = "maintain"
    phase_view["target_weight_kg"] = target_weight

    targets = meal_service.derive_nutrition_targets(phase_view, None)

    return {
        "index": 0,  # re-indexed by the caller when appended
        "start_weight": round(float(target_weight), 2),
        "end_weight": round(float(target_weight), 2),
        "weeks": MIN_PHASE_WEEKS,
        "status": "active",
        "start_date": None,
        "end_date": None,
        "maintenance": True,
        "kcal": targets["kcal"],
        "protein_g": targets["protein_g"],
        "fat_g": targets["fat_g"],
        "carbs_g": targets["carbs_g"],
    }


# ── Phase advancement on weigh-in (Req 7.1-7.5) ──────────────────────────────
def _end_reached(start_weight: float, end_weight: float,
                 current_weight: float) -> bool:
    """True iff ``current_weight`` reached the phase end in the goal direction
    within ``PHASE_TOLERANCE_KG``.

    Loss phase (end < start): reached when current <= end + tolerance.
    Gain phase (end > start): reached when current >= end - tolerance.
    Flat phase (end == start): reached when |current - end| <= tolerance.
    """
    if end_weight < start_weight:          # losing weight
        return current_weight <= end_weight + PHASE_TOLERANCE_KG
    if end_weight > start_weight:          # gaining weight
        return current_weight >= end_weight - PHASE_TOLERANCE_KG
    return abs(current_weight - end_weight) <= PHASE_TOLERANCE_KG


def advance_phase_on_weight(
    profile: dict, phases: list[dict], current_weight: float,
    active_elapsed_weeks: float,
) -> list[dict]:
    """PURE. Update ``phases`` given the user's current weight and how many weeks
    the active phase has been running. Returns the updated list; performs no I/O.

    Rules:
    - If current_weight reached the active phase end within PHASE_TOLERANCE_KG (in
      the goal direction): mark it completed; mark completed every subsequent phase
      whose end is also reached/overshot; activate the first remaining pending phase
      and re-derive its targets from current_weight (Req 7.1, 7.2, 7.4).
    - Else if active_elapsed_weeks >= active phase weeks and the end is not reached:
      EXTEND the active phase — recompute weeks and targets from current_weight
      (do NOT skip) (Req 7.3).
    - If the last phase becomes completed: activate a maintenance phase at B and set
      every plan's goal_reached (handled by the caller via the returned list)
      (Req 7.5).
    """
    # Work on a shallow copy of each phase dict.
    phases = [dict(p) for p in phases]
    if not phases:
        return phases

    # Locate the active phase.
    active_idx = next(
        (i for i, p in enumerate(phases) if p.get("status") == "active"),
        None,
    )
    if active_idx is None:
        return phases

    active = phases[active_idx]
    reached = _end_reached(
        active["start_weight"], active["end_weight"], current_weight
    )

    if not reached:
        # Extension path: enough time elapsed but target not met → extend.
        if active_elapsed_weeks is not None and \
                active_elapsed_weeks >= active.get("weeks", MIN_PHASE_WEEKS):
            # Re-anchor the phase at the current weight; keep the same end target.
            prior_weeks = active.get("weeks") or MIN_PHASE_WEEKS
            implied_rate = abs(active["end_weight"] - active["start_weight"]) \
                / max(prior_weeks, 1e-9)
            active["start_weight"] = round(float(current_weight), 2)
            remaining = abs(active["end_weight"] - current_weight)
            # Estimate the new duration from the leftover change at the phase's
            # implied weekly rate; keep within [MIN_PHASE_WEEKS, PHASE_MAX_WEEKS].
            if implied_rate > 1e-9:
                weeks = min(max(remaining / implied_rate, MIN_PHASE_WEEKS),
                            PHASE_MAX_WEEKS)
            else:
                weeks = MIN_PHASE_WEEKS
            active["weeks"] = round(weeks, 2)
            phases[active_idx] = derive_phase_targets(profile, active)
        return phases

    # Reached: complete the active phase and any subsequent phases already met.
    active["status"] = "completed"
    phases[active_idx] = active

    # Walk forward completing every phase whose end is reached/overshot, in the
    # goal direction, relative to the current weight.
    next_pending_idx = None
    for i in range(active_idx + 1, len(phases)):
        p = phases[i]
        if p.get("maintenance"):
            continue
        if _end_reached(p["start_weight"], p["end_weight"], current_weight):
            p["status"] = "completed"
            phases[i] = p
        else:
            next_pending_idx = i
            break

    if next_pending_idx is not None:
        # Activate the first remaining pending phase; re-anchor to current weight
        # and re-derive its targets from there.
        nxt = phases[next_pending_idx]
        nxt["status"] = "active"
        nxt["start_weight"] = round(float(current_weight), 2)
        phases[next_pending_idx] = derive_phase_targets(profile, nxt)
        return phases

    # No pending phase left → journey complete: append an active maintenance phase.
    target_b = phases[-1]["end_weight"]
    maint = maintenance_phase(profile, target_b)
    maint["index"] = phases[-1]["index"] + 1
    phases.append(maint)
    return phases
