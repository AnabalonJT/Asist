"""Property tests for schedule format validation."""
import pytest
from hypothesis import given, strategies as st


def validate_schedule(schedule: str) -> bool:
    """Validate HH:MM schedule format."""
    parts = schedule.split(":")
    if len(parts) != 2:
        return False
    try:
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False


@given(
    h=st.integers(min_value=0, max_value=23),
    m=st.integers(min_value=0, max_value=59),
)
def test_valid_schedule_accepted(h, m):
    """Property: any valid HH:MM (0-23:0-59) is accepted."""
    schedule = f"{h:02d}:{m:02d}"
    assert validate_schedule(schedule) is True


@given(
    h=st.integers(min_value=24, max_value=99),
    m=st.integers(min_value=0, max_value=59),
)
def test_invalid_hour_rejected(h, m):
    """Property: hours >= 24 are rejected."""
    schedule = f"{h:02d}:{m:02d}"
    assert validate_schedule(schedule) is False


@given(
    h=st.integers(min_value=0, max_value=23),
    m=st.integers(min_value=60, max_value=99),
)
def test_invalid_minute_rejected(h, m):
    """Property: minutes >= 60 are rejected."""
    schedule = f"{h:02d}:{m:02d}"
    assert validate_schedule(schedule) is False


@given(s=st.text(min_size=0, max_size=10))
def test_random_strings_dont_crash(s):
    """Property: random strings don't crash the validator."""
    result = validate_schedule(s)
    assert isinstance(result, bool)
