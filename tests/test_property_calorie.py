"""Property tests for calorie calculation completeness."""
import pytest
from hypothesis import given, strategies as st, assume
from app.services.calorie_service import calorie_service, DEFAULT_FORMULAS


@given(
    activity=st.sampled_from(list(DEFAULT_FORMULAS.keys())),
    duration=st.integers(min_value=1, max_value=600),
)
def test_positive_calories_for_any_known_activity_with_duration(activity, duration):
    """Property: any known activity with positive duration produces positive calories."""
    result = calorie_service.estimate(activity, duration_minutes=duration)
    assert result > 0


@given(
    activity=st.sampled_from(list(DEFAULT_FORMULAS.keys())),
    duration=st.integers(min_value=1, max_value=600),
)
def test_calories_increase_with_duration(activity, duration):
    """Property: longer duration = more calories (monotonically increasing)."""
    short = calorie_service.estimate(activity, duration_minutes=duration)
    long = calorie_service.estimate(activity, duration_minutes=duration + 10)
    assert long >= short


@given(
    distance=st.floats(min_value=0.1, max_value=100.0),
)
def test_running_distance_always_positive(distance):
    """Property: running with any positive distance produces positive calories."""
    result = calorie_service.estimate("running", distance_km=distance)
    assert result > 0


@given(
    activity=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",))),
    duration=st.integers(min_value=1, max_value=300),
)
def test_unknown_activity_still_calculates(activity, duration):
    """Property: even unknown activities produce a result using default MET."""
    assume(activity.lower().strip() not in DEFAULT_FORMULAS)
    result = calorie_service.estimate(activity, duration_minutes=duration)
    assert result > 0


@given(
    activity=st.sampled_from(list(DEFAULT_FORMULAS.keys())),
)
def test_zero_inputs_return_zero(activity):
    """Property: no duration and no distance returns 0."""
    result = calorie_service.estimate(activity, duration_minutes=0, distance_km=None)
    assert result == 0
