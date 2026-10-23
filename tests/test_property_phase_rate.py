"""Property tests for the Goal_Wizard per-phase target rate.

These target the PURE function ``derive_phase_targets`` in
``app.services.goal_wizard_service`` together with the reused pure helpers
``fitness_service.compute_target_rate`` and
``meal_service.derive_nutrition_targets``. No DB or I/O is involved, so they
follow the same style as the other ``test_property_*`` modules in this repo.

Property 4 (design.md): the daily caloric adjustment embedded in a phase's
targets must correspond to the ``Target_Rate`` that ``compute_target_rate``
computes over *that phase's* own weight change and duration, NOT the rate of the
full A->B journey.
"""
from hypothesis import given, settings, strategies as st

from app.services import fitness_service, meal_service
from app.services.goal_wizard_service import PHASE_MAX_KG, derive_phase_targets


# ── Generators constrained to the valid input space ──────────────────────────
# Body data accepted by estimate_maintenance_kcal (Mifflin-St Jeor).
_weight = st.floats(min_value=30.0, max_value=300.0,
                    allow_nan=False, allow_infinity=False)
_height = st.floats(min_value=120.0, max_value=230.0,
                    allow_nan=False, allow_infinity=False)
_age = st.integers(min_value=14, max_value=100)
_sex = st.sampled_from(["male", "female", "other"])


@st.composite
def _profile(draw):
    return {
        "weight_kg": draw(_weight),
        "height_cm": draw(_height),
        "age": draw(_age),
        "sex": draw(_sex),
    }


@st.composite
def _phase(draw):
    """A single phase respecting the Phase_Size_Rule: start != end, at most
    PHASE_MAX_KG of change, at least 1 week of duration."""
    start = draw(st.floats(min_value=30.0, max_value=300.0,
                           allow_nan=False, allow_infinity=False))
    # Signed change with magnitude in (0, PHASE_MAX_KG]; keep end in range.
    delta = draw(st.floats(min_value=0.1, max_value=PHASE_MAX_KG,
                           allow_nan=False, allow_infinity=False))
    sign = draw(st.sampled_from([1.0, -1.0]))
    end = start + sign * delta
    # Keep the phase end within the physical weight range.
    end = max(30.0, min(300.0, end))
    weeks = draw(st.floats(min_value=1.0, max_value=4.0,
                           allow_nan=False, allow_infinity=False))
    return {
        "index": 0,
        "start_weight": round(start, 2),
        "end_weight": round(end, 2),
        "weeks": round(weeks, 2),
        "status": "active",
        "maintenance": False,
        "kcal": None, "protein_g": None, "fat_g": None, "carbs_g": None,
    }


# Feature: goal-wizard, Property 4: El ritmo de cada fase corresponde a la fase,
# no al trayecto completo
@settings(max_examples=100)
@given(profile=_profile(), phase=_phase())
def test_phase_targets_use_phase_rate(profile, phase):
    """Feature: goal-wizard, Property 4: El ritmo de cada fase corresponde a la
    fase, no al trayecto completo.

    The kcal embedded in a phase's targets must equal the kcal derived from that
    phase's own compute_target_rate(start, end, weeks), i.e. the per-phase rate.

    Validates: Requirements 6.2
    """
    # Skip degenerate draws where start == end after rounding (no valid rate).
    if phase["start_weight"] == phase["end_weight"]:
        return

    result = derive_phase_targets(profile, phase)

    # Independent reconstruction using ONLY the phase's own start/end/weeks.
    phase_rate = fitness_service.compute_target_rate(
        phase["start_weight"], phase["end_weight"], phase["weeks"]
    )
    phase_view = {
        "weight_kg": phase["start_weight"],
        "current_weight_kg": phase["start_weight"],
        "height_cm": profile["height_cm"],
        "age": profile["age"],
        "sex": profile["sex"],
        "goal_type": "weight_target",
        "target_weight_kg": phase["end_weight"],
        "target_date": None,
    }
    expected = meal_service.derive_nutrition_targets(phase_view, phase_rate)

    assert result["kcal"] == expected["kcal"]
    assert result["protein_g"] == expected["protein_g"]
    assert result["fat_g"] == expected["fat_g"]
    assert result["carbs_g"] == expected["carbs_g"]


# Feature: goal-wizard, Property 4: El ritmo de cada fase corresponde a la fase,
# no al trayecto completo
@settings(max_examples=100)
@given(
    profile=_profile(),
    phase=_phase(),
    journey_weeks=st.floats(min_value=1.0, max_value=260.0,
                            allow_nan=False, allow_infinity=False),
    journey_end=st.floats(min_value=30.0, max_value=300.0,
                          allow_nan=False, allow_infinity=False),
)
def test_phase_rate_not_full_journey_rate(profile, phase, journey_weeks,
                                          journey_end):
    """Feature: goal-wizard, Property 4: El ritmo de cada fase corresponde a la
    fase, no al trayecto completo.

    When the full A->B journey rate differs from the phase rate (so that the
    full-journey rate would produce a different daily_kcal_delta), the phase's
    kcal must follow the PHASE rate, never the full-journey rate.

    Validates: Requirements 6.2
    """
    if phase["start_weight"] == phase["end_weight"]:
        return

    phase_rate = fitness_service.compute_target_rate(
        phase["start_weight"], phase["end_weight"], phase["weeks"]
    )

    # Build a full-journey rate over A -> journey_end across journey_weeks.
    full_start = phase["start_weight"]
    if full_start == journey_end:
        return
    full_rate = fitness_service.compute_target_rate(
        full_start, journey_end, journey_weeks
    )

    # Only meaningful when the two rates imply a different daily kcal delta AND
    # the same goal direction would otherwise make them indistinguishable.
    if full_rate["daily_kcal_delta"] == phase_rate["daily_kcal_delta"]:
        return
    if full_rate["direction"] != phase_rate["direction"]:
        return

    result = derive_phase_targets(profile, phase)

    base_view = {
        "weight_kg": phase["start_weight"],
        "current_weight_kg": phase["start_weight"],
        "height_cm": profile["height_cm"],
        "age": profile["age"],
        "sex": profile["sex"],
        "goal_type": "weight_target",
        "target_weight_kg": phase["end_weight"],
        "target_date": None,
    }
    kcal_from_phase_rate = meal_service.derive_nutrition_targets(
        base_view, phase_rate
    )["kcal"]
    kcal_from_full_rate = meal_service.derive_nutrition_targets(
        base_view, full_rate
    )["kcal"]

    # The phase follows its own rate, and that differs from the full-journey rate.
    assert result["kcal"] == kcal_from_phase_rate
    assert result["kcal"] != kcal_from_full_rate
