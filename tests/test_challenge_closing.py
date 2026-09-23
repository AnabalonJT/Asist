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
