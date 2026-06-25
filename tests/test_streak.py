"""Unit tests for streak calculation logic."""
import pytest
from datetime import datetime, timedelta, date
from app.routes.dashboard import _calc_streak


class TestStreakCalculation:
    """Tests for streak calculation."""

    def test_empty_dates_returns_zero(self):
        assert _calc_streak([]) == 0

    def test_single_day_today(self):
        today = datetime.utcnow().date()
        assert _calc_streak([today]) == 1

    def test_single_day_yesterday(self):
        """Activity only yesterday still counts as streak of 1."""
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        assert _calc_streak([yesterday]) == 1

    def test_two_consecutive_days(self):
        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        assert _calc_streak([today, yesterday]) == 2

    def test_three_consecutive_days(self):
        today = datetime.utcnow().date()
        dates = [today - timedelta(days=i) for i in range(3)]
        assert _calc_streak(dates) == 3

    def test_gap_breaks_streak(self):
        """A gap resets the streak."""
        today = datetime.utcnow().date()
        # today, yesterday, then skip a day, then 2 days ago
        dates = [today, today - timedelta(days=1), today - timedelta(days=3)]
        assert _calc_streak(dates) == 2

    def test_only_old_dates(self):
        """Dates from a week ago with no recent activity = 0."""
        today = datetime.utcnow().date()
        old = today - timedelta(days=5)
        assert _calc_streak([old]) == 0

    def test_seven_day_streak(self):
        today = datetime.utcnow().date()
        dates = [today - timedelta(days=i) for i in range(7)]
        assert _calc_streak(dates) == 7

    def test_dates_must_be_sorted_desc(self):
        """Function expects dates sorted descending."""
        today = datetime.utcnow().date()
        dates = sorted([today - timedelta(days=i) for i in range(5)], reverse=True)
        assert _calc_streak(dates) == 5
