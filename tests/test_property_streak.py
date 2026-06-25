"""Property tests for streak calculation correctness."""
import pytest
from datetime import datetime, timedelta, date
from hypothesis import given, strategies as st, assume
from app.routes.dashboard import _calc_streak


@given(n=st.integers(min_value=1, max_value=30))
def test_consecutive_days_from_today(n):
    """Property: n consecutive days from today produces streak of n."""
    today = datetime.utcnow().date()
    dates = [today - timedelta(days=i) for i in range(n)]
    assert _calc_streak(dates) == n


@given(n=st.integers(min_value=1, max_value=30))
def test_consecutive_days_from_yesterday(n):
    """Property: n consecutive days starting from yesterday produces streak of n."""
    yesterday = datetime.utcnow().date() - timedelta(days=1)
    dates = [yesterday - timedelta(days=i) for i in range(n)]
    # Starting from yesterday: first day counts as 1
    result = _calc_streak(dates)
    assert result == n


@given(
    streak_len=st.integers(min_value=1, max_value=10),
    gap=st.integers(min_value=2, max_value=10),
    old_len=st.integers(min_value=1, max_value=10),
)
def test_gap_limits_streak(streak_len, gap, old_len):
    """Property: a gap stops the streak count."""
    today = datetime.utcnow().date()
    # Recent streak
    recent = [today - timedelta(days=i) for i in range(streak_len)]
    # Old activities after gap
    gap_start = today - timedelta(days=streak_len + gap)
    old = [gap_start - timedelta(days=i) for i in range(old_len)]
    
    all_dates = recent + old
    result = _calc_streak(all_dates)
    assert result == streak_len


def test_empty_returns_zero():
    """Property: empty list always returns 0."""
    assert _calc_streak([]) == 0


@given(days_ago=st.integers(min_value=3, max_value=100))
def test_old_single_date_returns_zero(days_ago):
    """Property: a single date far in the past returns 0."""
    old = datetime.utcnow().date() - timedelta(days=days_ago)
    assert _calc_streak([old]) == 0
