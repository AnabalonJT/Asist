"""Property tests for Goal_Wizard initial step resolution.

Feature: goal-wizard, Property 1: Resolución del paso inicial del asistente
Validates: Requirements 1.2, 1.5, 1.6

These tests exercise the pure functions ``resolve_wizard_step`` and
``is_profile_complete`` from ``app.services.goal_wizard_service``. No I/O or LLM
is involved, so the property can be checked across many generated user states.
"""
import pytest
from hypothesis import given, settings, strategies as st

from app.services.goal_wizard_service import (
    resolve_wizard_step,
    is_profile_complete,
    WIZARD_STEPS,
)
from app.services.fitness_service import (
    VALID_LEVELS,
    VALID_SEX,
    VALID_GOAL_TYPES,
    EQUIPMENT_CATALOG,
)

# ── Smart generators ─────────────────────────────────────────────────────────
# Body/availability fields: each may be in-range (valid) or out-of-range/missing
# (invalid), so generated profiles span both Profile_Complete and incomplete.
_weights = st.one_of(
    st.floats(min_value=30, max_value=300),          # valid
    st.floats(min_value=0, max_value=29),            # too low
    st.just(None),                                   # missing
)
_heights = st.one_of(
    st.floats(min_value=100, max_value=250),         # valid
    st.floats(min_value=0, max_value=99),            # too low
    st.just(None),
)
_ages = st.one_of(
    st.integers(min_value=13, max_value=100),        # valid
    st.integers(min_value=0, max_value=12),          # too young
    st.just(None),
)
_levels = st.one_of(
    st.sampled_from(sorted(VALID_LEVELS)),           # valid
    st.just("experto"),                              # invalid
    st.just(None),
)
_days = st.one_of(
    st.integers(min_value=1, max_value=7),           # valid
    st.integers(min_value=8, max_value=20),          # out of range
    st.just(0),
    st.just(None),
)
_minutes = st.one_of(
    st.integers(min_value=10, max_value=240),        # valid
    st.integers(min_value=0, max_value=9),           # too short
    st.just(None),
)
_goal_types = st.one_of(
    st.sampled_from(sorted(VALID_GOAL_TYPES)),       # present goal
    st.just(None),                                   # no goal
    st.just(""),                                     # empty / falsy
)
_sexes = st.one_of(st.sampled_from(sorted(VALID_SEX)), st.just(None))
_equipment = st.lists(
    st.sampled_from(sorted(EQUIPMENT_CATALOG)), max_size=3, unique=True
)


@st.composite
def _profiles(draw):
    """Generate a profile dict (or None) spanning complete and incomplete states."""
    if draw(st.booleans()) and draw(st.integers(0, 9)) == 0:
        # Occasionally yield a wholly-missing profile.
        return None
    return {
        "weight_kg": draw(_weights),
        "height_cm": draw(_heights),
        "age": draw(_ages),
        "level": draw(_levels),
        "days_per_week": draw(_days),
        "minutes_per_session": draw(_minutes),
        "sex": draw(_sexes),
        "goal_type": draw(_goal_types),
        "equipment": draw(_equipment),
    }


_plans = st.one_of(
    st.just(None),
    st.just({"phases": []}),                          # plan with no phases
    st.just({"phases": [{"index": 0, "status": "active"}]}),  # has phases
)


# ── Reference implementation of the expected step (independent of production) ──
def _expected_step(profile, plan, has_routine):
    """Independently compute the first incomplete step per the spec order."""
    if not is_profile_complete(profile):
        return "profile"
    if not (profile and profile.get("goal_type")):
        return "goal"
    if not (profile and (profile.get("equipment") or [])):
        return "equipment"
    if not (plan and (plan.get("phases") or [])):
        return "diet"
    days = profile.get("days_per_week") if profile else None
    days_ok = isinstance(days, (int, float)) and not isinstance(days, bool) \
        and 1 <= days <= 7
    if not days_ok:
        return "training_days"
    if not has_routine:
        return "routine"
    return "summary"


# ── Property 1 ────────────────────────────────────────────────────────────────
@settings(max_examples=100)
@given(profile=_profiles(), plan=_plans, has_routine=st.booleans())
def test_resolve_returns_first_incomplete_step(profile, plan, has_routine):
    """Property 1: resolve_wizard_step returns the first incomplete Wizard_Step in
    the canonical order, and never ``profile`` when the profile is already
    Profile_Complete. Validates Requirements 1.2, 1.5, 1.6."""
    step = resolve_wizard_step(profile, plan, has_routine)

    # Result is always a valid Wizard_Step.
    assert step in WIZARD_STEPS

    # Result matches the independently computed first-incomplete step (Req 1.2).
    assert step == _expected_step(profile, plan, has_routine)

    # If the profile is Profile_Complete the step is never `profile` (Req 1.5).
    if is_profile_complete(profile):
        assert step != "profile"
    else:
        # Conversely, an incomplete profile must stop at the `profile` step.
        assert step == "profile"
