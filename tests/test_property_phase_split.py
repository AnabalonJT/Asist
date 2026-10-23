"""Property tests for the progressive A→B phase-splitting (goal-wizard).

These target the PURE function ``split_into_phases`` in
``app.services.goal_wizard_service``. No DB or I/O is involved, so they follow
the same style as the other ``test_property_*`` modules in this repo.
"""
import math

from hypothesis import assume, given, settings, strategies as st

from app.services.goal_wizard_service import (
    split_into_phases,
    PHASE_MAX_KG,
    PHASE_MAX_WEEKS,
    MIN_PHASE_WEEKS,
)

# Rounding to 2 decimals in the implementation introduces up to 0.005 kg of
# drift per boundary; use a small tolerance on the kg/chaining invariants.
_ROUND_TOL = 0.011

# Weights in the supported body-weight range (30–300 kg).
_weight = st.floats(min_value=30.0, max_value=300.0,
                    allow_nan=False, allow_infinity=False)
# A non-zero weekly rate. The sign is irrelevant to the split (direction is
# inferred from sign(B - A)); magnitude drives per-phase duration. The floor of
# 0.1 kg/week keeps the phase count for the widest journey (30→300 kg) well under
# the implementation's internal safety ceiling, so the plan always completes at B
# rather than being cut short by that guard (a guard that only fires for
# physically unrealistic rate/journey combinations).
_rate = st.floats(min_value=0.1, max_value=5.0,
                  allow_nan=False, allow_infinity=False)


@settings(max_examples=100)
@given(start_weight=_weight, target_weight=_weight, rate=_rate)
def test_split_into_phases_invariants(start_weight, target_weight, rate):
    """Feature: goal-wizard, Property 2: Invariantes del fraccionamiento en fases.

    Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
    """
    # A non-trivial journey: A and B meaningfully distinct (not lost to rounding).
    assume(abs(start_weight - target_weight) >= 0.1)
    phases = split_into_phases(start_weight, target_weight, rate)

    # There is always at least one phase for a non-trivial journey.
    assert len(phases) >= 1

    direction = 1.0 if target_weight > start_weight else -1.0

    for i, phase in enumerate(phases):
        change = abs(phase["end_weight"] - phase["start_weight"])

        # Req 5.1 — each phase spans at most 2.5 kg of weight change ...
        assert change <= PHASE_MAX_KG + _ROUND_TOL

        # Req 5.1 — ... and at most 4 weeks of estimated duration.
        assert phase["weeks"] <= PHASE_MAX_WEEKS + 1e-9

        # Req 5.5 — duration is at least MIN_PHASE_WEEKS (1 week) per phase.
        assert phase["weeks"] >= MIN_PHASE_WEEKS - 1e-9

        # Req 5.2 — phase 0 starts at A; each later phase starts at the previous
        # phase's end weight (chained).
        if i == 0:
            assert math.isclose(phase["start_weight"], start_weight,
                                abs_tol=_ROUND_TOL)
        else:
            assert math.isclose(phase["start_weight"],
                                phases[i - 1]["end_weight"], abs_tol=_ROUND_TOL)

        # Req 5.2 — end weights advance toward B without overshooting it.
        progressed = (phase["end_weight"] - phase["start_weight"]) * direction
        assert progressed >= -_ROUND_TOL  # moves in the goal direction
        if direction > 0:  # gaining: never exceed B
            assert phase["end_weight"] <= target_weight + _ROUND_TOL
        else:              # losing: never drop below B
            assert phase["end_weight"] >= target_weight - _ROUND_TOL

    # Req 5.3 — the last phase ends exactly at B.
    assert phases[-1]["end_weight"] == round(float(target_weight), 2)


@settings(max_examples=100)
@given(start_weight=_weight,
       delta=st.floats(min_value=0.1, max_value=PHASE_MAX_KG,
                       allow_nan=False, allow_infinity=False),
       sign=st.sampled_from([1.0, -1.0]),
       rate=_rate)
def test_split_small_journey_is_single_phase(start_weight, delta, sign, rate):
    """Feature: goal-wizard, Property 2: Invariantes del fraccionamiento en fases.

    Req 5.4 — when |A - B| <= 2.5 kg (and the weekly rate is fast enough that the
    4-week cap does not force a split) the plan contains exactly one phase ending
    at B. A phase is bounded by ``min(PHASE_MAX_KG, rate * PHASE_MAX_WEEKS)``, so
    the single-phase guarantee needs the journey to fit under that combined cap.

    Validates: Requirements 5.4
    """
    target_weight = start_weight + sign * delta
    # Keep B inside the supported range.
    if not (30.0 <= target_weight <= 300.0):
        target_weight = start_weight - sign * delta

    # The journey must fit in one phase under the actual Phase_Size_Rule: both
    # the 2.5 kg cap and the 4-week cap (rate * 4 kg) must admit it.
    assume(delta <= min(PHASE_MAX_KG, rate * PHASE_MAX_WEEKS) + 1e-9)

    phases = split_into_phases(start_weight, target_weight, rate)

    assert len(phases) == 1
    assert phases[0]["end_weight"] == round(float(target_weight), 2)
