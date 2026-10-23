"""Tests for expired challenge/goal closing logic in the scheduler."""
from datetime import date

import pytest

from app.scheduler import _parse_end_date


class TestParseEndDate:
    def test_valid_iso_date(self):
        assert _parse_end_date("2026-09-22") == date(2026, 9, 22)

    def test_valid_iso_datetime_prefix(self):
        # Accepts a longer string, taking the date prefix.
        assert _parse_end_date("2026-09-22T10:00:00") == date(2026, 9, 22)

    def test_whitespace_trimmed(self):
        assert _parse_end_date("  2026-01-05  ") == date(2026, 1, 5)

    def test_none_returns_none(self):
        assert _parse_end_date(None) is None

    def test_empty_returns_none(self):
        assert _parse_end_date("") is None

    def test_garbage_returns_none(self):
        assert _parse_end_date("not-a-date") is None
        assert _parse_end_date("2026-13-99") is None


class TestModelsHaveClosingFields:
    def test_challenge_has_closed_notified(self):
        from app.models.challenge import Challenge
        assert hasattr(Challenge, "closed_notified")

    def test_goal_has_closed_notified(self):
        from app.models.goal import Goal
        assert hasattr(Goal, "closed_notified")

    def test_reminder_has_challenge_id(self):
        from app.models.reminder import Reminder
        assert hasattr(Reminder, "challenge_id")


class TestSchedulerWiring:
    def test_close_expired_job_registered(self):
        # The close-expired callable must exist and be scheduled.
        from app.scheduler import close_expired_challenges_and_goals
        assert callable(close_expired_challenges_and_goals)


from datetime import date
from app.scheduler import _expected_periods, compute_lifetime_completion


class TestExpectedPeriods:
    def test_daily_inclusive_days(self):
        # Jan 1 to Jan 10 inclusive = 10 days.
        assert _expected_periods(date(2026, 1, 1), date(2026, 1, 10), "daily") == 10

    def test_daily_single_day(self):
        assert _expected_periods(date(2026, 1, 1), date(2026, 1, 1), "daily") == 1

    def test_daily_75_days(self):
        # A "75 días" challenge: Jan 1 .. Mar 16 inclusive = 75 days.
        assert _expected_periods(date(2026, 1, 1), date(2026, 3, 16), "daily") == 75

    def test_weekly_ceils(self):
        # 28 days -> 4 weeks; 29 days -> 5 weeks (ceil).
        assert _expected_periods(date(2026, 1, 1), date(2026, 1, 28), "weekly") == 4
        assert _expected_periods(date(2026, 1, 1), date(2026, 1, 29), "weekly") == 5

    def test_monthly_inclusive_months(self):
        assert _expected_periods(date(2026, 1, 15), date(2026, 3, 10), "monthly") == 3
        assert _expected_periods(date(2026, 1, 1), date(2026, 1, 31), "monthly") == 1

    def test_end_before_start_is_zero(self):
        assert _expected_periods(date(2026, 2, 1), date(2026, 1, 1), "daily") == 0

    def test_unknown_period_defaults_daily(self):
        assert _expected_periods(date(2026, 1, 1), date(2026, 1, 5), "weird") == 5


class TestLifetimeCompletion:
    def test_daily_partial(self):
        # 75 daily target 1, 50 done -> 67%.
        assert compute_lifetime_completion(50, 1, date(2026, 1, 1), date(2026, 3, 16), "daily") == 67

    def test_weekly_full(self):
        # 4 weeks x 3/week = 12 expected, 12 done -> 100%.
        assert compute_lifetime_completion(12, 3, date(2026, 1, 1), date(2026, 1, 28), "weekly") == 100

    def test_weekly_half(self):
        assert compute_lifetime_completion(6, 3, date(2026, 1, 1), date(2026, 1, 28), "weekly") == 50

    def test_capped_at_100(self):
        assert compute_lifetime_completion(999, 1, date(2026, 1, 1), date(2026, 1, 10), "daily") == 100

    def test_zero_done(self):
        assert compute_lifetime_completion(0, 1, date(2026, 1, 1), date(2026, 1, 10), "daily") == 0

    def test_none_target_defaults_one(self):
        # target_count None -> treated as 1.
        assert compute_lifetime_completion(5, None, date(2026, 1, 1), date(2026, 1, 10), "daily") == 50

    def test_empty_span_zero(self):
        # end before start -> expected 0 -> 0%.
        assert compute_lifetime_completion(3, 1, date(2026, 2, 1), date(2026, 1, 1), "daily") == 0
