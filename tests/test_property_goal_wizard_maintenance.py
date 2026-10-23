"""Property test for the Goal_Wizard maintenance-phase transition (Property 10).

Targets the PURE functions ``advance_phase_on_weight`` and ``maintenance_phase``
in ``app.services.goal_wizard_service``. No DB or I/O is involved, so this
follows the same style as the sibling ``test_property_goal_wizard_*`` modules.

Property 10 (design.md), Validates: Requirements 7.5:
When the current weight reaches or overshoots the end weight of the LAST phase,
``advance_phase_on_weight`` must produce an ACTIVE maintenance phase whose target
weight is B, derived with maintenance direction, and the overall journey must be
marked as reached (an active maintenance phase exists in the result).
"""
import math

from hypothesis import assume, given, settings, strategies as st

from app.services import goal_wizard_service as gw
from app.services.goal_wizard_service import (
    derive_phase_targets,
    maintenance_phase,
    split_into_phases,
)


# A valid body-data profile for the pure derivation helpers. The exact body
# values don't change the maintenance transition; they only need to be in a
# plausible range so ``derive_nutrition_targets`` produces real targets.
@st.composite
def _profile(draw):
    return {
        "weight_kg": draw(st.floats(min_value=40.0, max_value=200.0,
                                    allow_nan=False, allow_infinity=False)),
        "height_cm": draw(st.floats(min_value=140.0, max_value=210.0,
                                    allow_nan=False, allow_infinity=False)),
        "age": draw(st.integers(min_value=16, max_value=90)),
        "sex": draw(st.sampled_from(["male", "female", "other", None])),
        "goal_type": "weight_target",
    }


@st.composite
def _plan_at_last_phase(draw):
    """Build a valid phase plan whose ACTIVE phase is the LAST phase, plus a
    current weight that reaches or overshoots that last phase's end (B) within /
    beyond PHASE_TOLERANCE_KG in the goal direction.

    Reaching the end of the last phase is the trigger for the maintenance phase.
    """
    profile = draw(_profile())

    # Build a REAL A→B journey whose magnitude is clearly non-zero. Property 10
    # only concerns a valid phase split with a genuine movement toward B, so we
    # keep |A-B| well above zero (>= 1.0 kg) and inside the 30..300 kg range.
    # ``losing`` is chosen first and the change is applied within the room left on
    # the chosen side, so the clamp can never collapse the journey to ~0.
    start = draw(st.floats(min_value=50.0, max_value=200.0,
                           allow_nan=False, allow_infinity=False))
    losing = draw(st.booleans())
    if losing:
        max_change = start - 30.0        # room down to the 30 kg floor
    else:
        max_change = 300.0 - start       # room up to the 300 kg ceiling
    # Guaranteed headroom: start in [50, 200] leaves >= 20 kg on either side.
    change = draw(st.floats(min_value=1.0, max_value=max_change,
                            allow_nan=False, allow_infinity=False))
    target = start - change if losing else start + change

    rate_mag = draw(st.floats(min_value=0.1, max_value=1.5,
                              allow_nan=False, allow_infinity=False))
    rate = -rate_mag if target < start else rate_mag

    # Phases come straight from the production split — we take the ACTUAL last
    # phase it emits (never a fabricated zero-movement phase).
    phases = split_into_phases(start, target, rate)
    phases = [derive_phase_targets(profile, p) for p in phases]

    last = phases[-1]
    # Drop any residual degenerate draw where float drift made the last phase a
    # zero-movement phase; Property 10 presupposes a real movement toward B.
    assume(last["start_weight"] != last["end_weight"])

    # Force the LAST phase to be the active one and all prior phases completed,
    # so the next weigh-in that reaches B completes the journey.
    for p in phases[:-1]:
        p["status"] = "completed"
    phases[-1]["status"] = "active"

    b = last["end_weight"]
    # A current weight that reaches or overshoots B in the goal direction.
    overshoot = draw(st.floats(min_value=0.0, max_value=5.0,
                               allow_nan=False, allow_infinity=False))
    if last["end_weight"] < last["start_weight"]:    # losing: go below B
        current_weight = b - overshoot
    else:                                            # gaining: go above B
        current_weight = b + overshoot

    return profile, phases, b, current_weight


@given(data=_plan_at_last_phase())
@settings(max_examples=100)
def test_advance_creates_active_maintenance_phase_at_B(data):
    """# Feature: goal-wizard, Property 10: Fase de mantenimiento al completar el trayecto

    When the current weight reaches/overshoots the end of the LAST phase,
    ``advance_phase_on_weight`` appends an ACTIVE maintenance phase whose target
    weight is B, derived with maintenance direction, and the journey is reached.

    Validates: Requirements 7.5.
    """
    profile, phases, b, current_weight = data

    updated = gw.advance_phase_on_weight(profile, phases, current_weight,
                                         active_elapsed_weeks=0.0)

    # The previously-active last phase is now completed.
    completed = [p for p in updated if p.get("status") == "completed"]
    assert any(not p.get("maintenance") for p in completed)

    # Exactly one active phase, and it is the maintenance phase.
    active_phases = [p for p in updated if p.get("status") == "active"]
    assert len(active_phases) == 1
    maint = active_phases[0]
    assert maint.get("maintenance") is True

    # The maintenance phase sits at B (start == end == B).
    assert math.isclose(maint["start_weight"], round(float(b), 2), abs_tol=1e-9)
    assert math.isclose(maint["end_weight"], round(float(b), 2), abs_tol=1e-9)

    # Its index follows the last real phase (appended at the end).
    assert maint["index"] == phases[-1]["index"] + 1
    assert updated[-1] is maint or updated[-1]["index"] == maint["index"]

    # The journey is reached: an active maintenance phase exists (the flag the
    # async layer reads to set goal_reached).
    goal_reached = any(p.get("maintenance") and p.get("status") == "active"
                       for p in updated)
    assert goal_reached is True

    # Maintenance derivation direction: targets equal a direct maintenance_phase
    # derivation at B (no deficit/surplus), and honor the macro post-condition.
    expected = maintenance_phase(profile, b)
    for key in ("kcal", "protein_g", "fat_g", "carbs_g"):
        assert maint[key] is not None
        assert math.isclose(maint[key], expected[key], abs_tol=1e-9)

    # The macro-kcal post-condition is defined for realistic diets. For a very
    # light body the reused ``derive_nutrition_targets`` can return a non-physical
    # maintenance target (kcal <= 0, or a protein floor that alone exceeds kcal so
    # no carbs/fat can balance it). That region is outside the postcondition
    # (Req 6.4 / meal_service Req 4.5), same edge case guarded in Property 3/7.
    assume(maint["kcal"] > 0)
    assume(maint["protein_g"] * 4 <= maint["kcal"])

    macro_kcal = (maint["protein_g"] * 4 + maint["carbs_g"] * 4
                  + maint["fat_g"] * 9)
    assert abs(macro_kcal - maint["kcal"]) <= 10.0
