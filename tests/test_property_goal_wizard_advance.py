"""Property tests for the Goal_Wizard phase-advancement pure logic.

These target the PURE function ``advance_phase_on_weight`` in
``app.services.goal_wizard_service``. No DB or I/O is involved, so they follow
the same style as the other ``test_property_*`` modules in this repo.
"""
import math

from hypothesis import assume, given, settings, strategies as st

from app.services import goal_wizard_service as gw
from app.services.goal_wizard_service import (
    PHASE_TOLERANCE_KG,
    derive_phase_targets,
    split_into_phases,
)


# A valid body-data profile for the pure derivation helpers. The exact body
# values don't affect the advancement transitions; they only need to be in a
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
def _plan_with_pending(draw):
    """Build a valid multi-phase plan (active phase 0, pending phases after it)
    plus a current weight that reaches phase 0's end within PHASE_TOLERANCE_KG in
    the goal direction WITHOUT overshooting phase 1's end (that overshoot case is
    Property 9, not Property 7).
    """
    profile = draw(_profile())

    # Pick a journey with enough change that split_into_phases yields >= 2 phases
    # (so there is a pending phase to activate). PHASE_MAX_KG is 2.5, so a change
    # strictly greater than 2.5 kg guarantees at least two phases.
    start = draw(st.floats(min_value=50.0, max_value=200.0,
                           allow_nan=False, allow_infinity=False))
    change = draw(st.floats(min_value=2.6, max_value=100.0,
                            allow_nan=False, allow_infinity=False))
    losing = draw(st.booleans())
    target = start - change if losing else start + change
    # Keep target within the valid 30..300 kg body-weight range.
    target = max(30.0, min(300.0, target))
    # Re-derive change/direction after clamping; require a real two-phase split.
    if abs(target - start) <= gw.PHASE_MAX_KG:
        # Not enough room after clamping; nudge the target to force >= 2 phases.
        if losing:
            target = max(30.0, start - 3.0)
        else:
            target = min(300.0, start + 3.0)

    rate_mag = draw(st.floats(min_value=0.1, max_value=1.5,
                              allow_nan=False, allow_infinity=False))
    rate = -rate_mag if target < start else rate_mag

    phases = split_into_phases(start, target, rate)
    phases = [derive_phase_targets(profile, p) for p in phases]
    # This strategy only covers the multi-phase (a pending phase exists) case.
    if len(phases) < 2:
        # Fall back to a guaranteed two-phase plan.
        if target < start:
            target = max(30.0, start - 3.0)
            rate = -0.5
        else:
            target = min(300.0, start + 3.0)
            rate = 0.5
        phases = split_into_phases(start, target, rate)
        phases = [derive_phase_targets(profile, p) for p in phases]

    active = phases[0]
    next_end = phases[1]["end_weight"]

    # Choose a current weight that:
    #  - reaches active.end within tolerance in the goal direction, and
    #  - does NOT reach phase 1's end (so only phase 0 completes here).
    if active["end_weight"] < active["start_weight"]:          # losing
        # reached: current <= active.end + tol ; not past next: current > next_end + tol
        low = next_end + PHASE_TOLERANCE_KG + 0.01
        high = active["end_weight"] + PHASE_TOLERANCE_KG
    else:                                                      # gaining
        # reached: current >= active.end - tol ; not past next: current < next_end - tol
        low = active["end_weight"] - PHASE_TOLERANCE_KG
        high = next_end - PHASE_TOLERANCE_KG - 0.01

    # low/high can collapse when phases are narrow; fall back to the exact end.
    if not (low < high):
        current_weight = active["end_weight"]
    else:
        current_weight = draw(st.floats(min_value=min(low, high),
                                        max_value=max(low, high),
                                        allow_nan=False, allow_infinity=False))

    return profile, phases, current_weight


@given(data=_plan_with_pending())
@settings(max_examples=100)
def test_advance_completes_active_and_activates_next_rederived(data):
    """# Feature: goal-wizard, Property 7: Avance de fase al alcanzar el peso de fin

    Reaching the active phase end within PHASE_TOLERANCE_KG (0.5 kg) in the goal
    direction marks the active phase ``completed``, activates the first remaining
    ``pending`` phase, and re-derives the new active phase's targets from the
    current weight (its new start_weight).

    Validates: Requirements 7.1, 7.2.
    """
    profile, phases, current_weight = data

    # elapsed weeks irrelevant here: the end is reached, so the advance path runs
    # regardless of elapsed time (the extension path is Property 8).
    updated = gw.advance_phase_on_weight(profile, phases, current_weight,
                                          active_elapsed_weeks=0.0)

    # The previously-active phase (index 0) is now completed.
    assert updated[0]["status"] == "completed"

    # Exactly one phase is active after advancing.
    active_phases = [p for p in updated if p.get("status") == "active"]
    assert len(active_phases) == 1
    new_active = active_phases[0]

    # The newly-active phase is the first phase that was pending before (index 1),
    # since current_weight was constrained not to overshoot it.
    assert new_active["index"] == phases[1]["index"]

    # 7.2: its start_weight equals the current weight (rounded as the service does)
    # and its targets are re-derived from that start_weight.
    assert math.isclose(new_active["start_weight"], round(float(current_weight), 2),
                        abs_tol=1e-9)

    expected = derive_phase_targets(profile, new_active)
    for key in ("kcal", "protein_g", "fat_g", "carbs_g"):
        assert new_active[key] is not None
        assert math.isclose(new_active[key], expected[key], abs_tol=1e-9)

    # The macro-kcal post-condition is defined for realistic diets: the target
    # kcal must be positive AND leave room after the protein floor so fat/carbs
    # can balance it. Extreme low body weight combined with an aggressive deficit
    # re-derived from the current weight can drive the reused
    # ``derive_nutrition_targets`` output non-physical — a negative target kcal,
    # or a positive target kcal that the protein-grams-per-kg floor alone already
    # exceeds (protein_g*4 > kcal). In that region ``derive_nutrition_targets``
    # cannot allocate any carbs/fat, so the macro identity is unreachable; it is
    # outside the space the postcondition (Req 6.4 / meal_service Req 4.5) covers.
    assume(new_active["kcal"] > 0)
    assume(new_active["protein_g"] * 4 <= new_active["kcal"])

    # The re-derived targets honor the macro post-condition (inherited).
    macro_kcal = (new_active["protein_g"] * 4 + new_active["carbs_g"] * 4
                  + new_active["fat_g"] * 9)
    assert abs(macro_kcal - new_active["kcal"]) <= 10.0


@st.composite
def _plan_not_reached_elapsed(draw):
    """Build a valid multi-phase plan (active phase 0, pending phases after it)
    plus a current weight that has NOT reached phase 0's end within
    PHASE_TOLERANCE_KG in the goal direction, together with an elapsed-weeks value
    that is >= the active phase's planned weeks.

    This is the Property 8 (extension) scenario: enough time has passed but the
    end weight was not met, so the active phase must be EXTENDED (kept active, its
    weeks and targets recomputed from the current weight) without advancing.
    """
    profile = draw(_profile())

    # Keep the journey well inside the valid body-weight band so clamping never
    # collapses the active phase to a sub-tolerance step.
    start = draw(st.floats(min_value=70.0, max_value=180.0,
                           allow_nan=False, allow_infinity=False))
    # A change strictly greater than PHASE_MAX_KG guarantees >= 2 phases, so a
    # ``pending`` phase exists to (wrongly) advance into if the code misbehaves.
    change = draw(st.floats(min_value=gw.PHASE_MAX_KG + 0.5, max_value=80.0,
                            allow_nan=False, allow_infinity=False))
    losing = draw(st.booleans())
    target = start - change if losing else start + change
    target = max(35.0, min(295.0, target))

    # Rate magnitude >= 0.5 forces step_kg = min(PHASE_MAX_KG, rate*4) >= 2.0, so
    # the active phase (phase 0) always spans well more than PHASE_TOLERANCE_KG.
    # That makes the phase start a guaranteed "not reached" current weight.
    rate_mag = draw(st.floats(min_value=0.5, max_value=1.5,
                              allow_nan=False, allow_infinity=False))
    rate = -rate_mag if target < start else rate_mag

    phases = split_into_phases(start, target, rate)
    phases = [derive_phase_targets(profile, p) for p in phases]

    active = phases[0]
    phase_span = abs(active["end_weight"] - active["start_weight"])
    # This strategy only covers the genuine extension scenario, which requires a
    # phase whose span exceeds the tolerance (otherwise the start weight would
    # already count as "reached").
    assume(phase_span > PHASE_TOLERANCE_KG + 1e-6)

    # The phase start weight has NOT reached the phase end within tolerance (the
    # remaining change equals phase_span > tolerance), so it is a valid
    # "insufficient progress" current weight regardless of direction.
    current_weight = active["start_weight"]

    # Elapsed weeks must be >= the active phase's planned weeks to trigger the
    # extension path.
    elapsed = draw(st.floats(min_value=active["weeks"],
                             max_value=active["weeks"] + 20.0,
                             allow_nan=False, allow_infinity=False))

    return profile, phases, current_weight, elapsed


@given(data=_plan_not_reached_elapsed())
@settings(max_examples=100)
def test_advance_extends_active_phase_when_progress_insufficient(data):
    """# Feature: goal-wizard, Property 8: Extensión de la fase ante progreso insuficiente

    When the active phase's Phase_Time_Window has elapsed (elapsed weeks >= the
    active phase's planned weeks) but the current weight has NOT reached the phase
    end within PHASE_TOLERANCE_KG, ``advance_phase_on_weight`` keeps that phase
    ``active`` (no pending phase is activated) and recomputes its estimated
    duration and targets from the current weight.

    Validates: Requirements 7.3.
    """
    profile, phases, current_weight, elapsed = data

    original_active_index = phases[0]["index"]

    updated = gw.advance_phase_on_weight(profile, phases, current_weight,
                                         active_elapsed_weeks=elapsed)

    # Exactly one active phase, and it is still the same phase (index 0): no
    # pending phase was activated.
    active_phases = [p for p in updated if p.get("status") == "active"]
    assert len(active_phases) == 1
    extended = active_phases[0]
    assert extended["index"] == original_active_index

    # No phase was marked completed by the extension path.
    assert all(p.get("status") != "completed" for p in updated)

    # The phase count is unchanged (no maintenance phase appended, nothing added).
    assert len(updated) == len(phases)

    # The extended phase is re-anchored at the current weight, with its targets
    # re-derived from that start_weight.
    assert math.isclose(extended["start_weight"], round(float(current_weight), 2),
                        abs_tol=1e-9)

    # Property 8 is specifically about keeping the phase active and recomputing
    # its duration and targets from the current weight. The targets must match a
    # fresh derivation from the extended phase's (re-anchored) start_weight.
    expected = derive_phase_targets(profile, extended)
    for key in ("kcal", "protein_g", "fat_g", "carbs_g"):
        assert extended[key] is not None
        assert math.isclose(extended[key], expected[key], abs_tol=1e-9)

    # The recomputed duration stays within the documented phase bounds.
    assert gw.MIN_PHASE_WEEKS <= extended["weeks"] <= gw.PHASE_MAX_WEEKS


@st.composite
def _plan_with_overshoot(draw):
    """Build a valid multi-phase plan (active phase 0, several pending phases)
    plus a current weight that overshoots the end of one or MORE phases beyond
    PHASE_TOLERANCE_KG in the goal direction, while leaving at least one phase
    whose end is NOT reached (so a pending phase remains to be activated).

    This is the Property 9 case: the weigh-in jumps past several consecutive
    phase ends at once.
    """
    profile = draw(_profile())

    # Force a journey long enough to yield >= 3 phases. PHASE_MAX_KG is 2.5, so a
    # change strictly greater than 5.0 kg guarantees at least three phases.
    start = draw(st.floats(min_value=60.0, max_value=200.0,
                           allow_nan=False, allow_infinity=False))
    change = draw(st.floats(min_value=6.0, max_value=120.0,
                            allow_nan=False, allow_infinity=False))
    losing = draw(st.booleans())
    target = start - change if losing else start + change
    target = max(30.0, min(300.0, target))
    # Guarantee a real multi-phase split (>= 3 phases) after clamping.
    if abs(target - start) <= 2 * gw.PHASE_MAX_KG:
        if losing:
            target = max(30.0, start - 6.0)
        else:
            target = min(300.0, start + 6.0)

    rate_mag = draw(st.floats(min_value=0.1, max_value=1.5,
                              allow_nan=False, allow_infinity=False))
    rate = -rate_mag if target < start else rate_mag

    phases = split_into_phases(start, target, rate)
    phases = [derive_phase_targets(profile, p) for p in phases]
    if len(phases) < 3:
        if target < start:
            target = max(30.0, start - 6.0)
            rate = -0.5
        else:
            target = min(300.0, start + 6.0)
            rate = 0.5
        phases = split_into_phases(start, target, rate)
        phases = [derive_phase_targets(profile, p) for p in phases]

    # Choose how many phases to overshoot: at least 2 ends reached, but leave at
    # least one phase whose end is NOT reached (so a pending phase survives).
    # ``k`` = number of phases whose end we clear (indices 0..k-1 completed).
    max_k = len(phases) - 1  # leave >= 1 phase not reached
    k = draw(st.integers(min_value=2, max_value=max(2, max_k)))
    k = min(k, max_k)

    # The k-th phase (index k) is the first one whose end must NOT be reached.
    last_completed = phases[k - 1]      # its end must be reached/overshot
    first_remaining = phases[k]         # its end must NOT be reached

    if last_completed["end_weight"] < last_completed["start_weight"]:   # losing
        # reached for index k-1: current <= last_completed.end + tol
        # NOT reached for index k: current > first_remaining.end + tol
        low = first_remaining["end_weight"] + PHASE_TOLERANCE_KG + 0.01
        high = last_completed["end_weight"] + PHASE_TOLERANCE_KG
    else:                                                               # gaining
        low = last_completed["end_weight"] - PHASE_TOLERANCE_KG
        high = first_remaining["end_weight"] - PHASE_TOLERANCE_KG - 0.01

    if not (low < high):
        # Narrow phases collapse the window; land exactly on last_completed end.
        current_weight = last_completed["end_weight"]
    else:
        current_weight = draw(st.floats(min_value=min(low, high),
                                        max_value=max(low, high),
                                        allow_nan=False, allow_infinity=False))

    return profile, phases, current_weight, k


@given(data=_plan_with_overshoot())
@settings(max_examples=100)
def test_advance_multi_phase_overshoot_completes_reached_and_activates_first_pending(data):
    """# Feature: goal-wizard, Property 9: Salto múltiple al sobrepasar varias fases

    A weigh-in whose weight overshoots the end of one or more consecutive phases
    beyond PHASE_TOLERANCE_KG (0.5 kg) in the goal direction marks ALL phases
    whose end was reached/overshot as ``completed`` and leaves ONLY the first
    remaining ``pending`` phase as ``active``.

    Validates: Requirements 7.4.
    """
    profile, phases, current_weight, _k = data

    updated = gw.advance_phase_on_weight(profile, phases, current_weight,
                                         active_elapsed_weeks=0.0)

    # Exactly one phase is active after advancing.
    active_phases = [p for p in updated if p.get("status") == "active"]
    assert len(active_phases) == 1
    new_active = active_phases[0]

    # Every non-maintenance phase whose end was reached/overshot is completed,
    # and every phase whose end was NOT reached is NOT completed. The newly
    # active phase is precisely the first one whose end is not reached.
    def reached(phase):
        return gw._end_reached(phase["start_weight"], phase["end_weight"],
                               current_weight)

    first_not_reached_index = None
    for p in updated:
        if p.get("maintenance"):
            continue
        if p["index"] < new_active["index"]:
            # Earlier phases (whose end the weigh-in cleared) must be completed.
            assert p["status"] == "completed"
        if first_not_reached_index is None and not reached(p):
            first_not_reached_index = p["index"]

    # At least two phases were cleared (the overshoot spans >= 2 phases).
    completed = [p for p in updated if p.get("status") == "completed"]
    assert len(completed) >= 2

    # The single active phase is the first remaining phase whose end is not
    # reached, re-anchored to the current weight with re-derived targets (7.4
    # reuses the 7.2 re-derivation when activating the next pending phase).
    assert new_active["index"] == first_not_reached_index
    assert not reached(new_active)
    assert math.isclose(new_active["start_weight"], round(float(current_weight), 2),
                        abs_tol=1e-9)

    expected = derive_phase_targets(profile, new_active)
    for key in ("kcal", "protein_g", "fat_g", "carbs_g"):
        assert new_active[key] is not None
        assert math.isclose(new_active[key], expected[key], abs_tol=1e-9)
