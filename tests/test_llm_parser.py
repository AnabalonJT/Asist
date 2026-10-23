"""Unit tests for LLM response parsing logic."""
import pytest
from app.services.llm_service import (
    parse_activity,
    parse_reminder,
    parse_goal,
    ActivityData,
    ReminderData,
    GoalData,
)


class TestParseActivity:
    """Tests for parsing activity data from LLM responses."""

    def test_parse_valid_sport(self):
        response = {
            "intent": "activity",
            "data": {
                "activity_type": "running",
                "category": "sport",
                "duration_minutes": 30,
                "distance_km": 5.0,
                "detail": None,
                "confidence": 0.9,
            }
        }
        result = parse_activity(response)
        assert result is not None
        assert result.activity_type == "running"
        assert result.category == "sport"
        assert result.duration_minutes == 30
        assert result.distance_km == 5.0
        assert result.confidence == 0.9

    def test_parse_valid_strength(self):
        response = {
            "intent": "activity",
            "data": {
                "activity_type": "weights",
                "category": "strength",
                "duration_minutes": 10,
                "distance_km": None,
                "detail": "4x100kg press banca",
                "confidence": 0.85,
            }
        }
        result = parse_activity(response)
        assert result is not None
        assert result.category == "strength"
        assert result.detail == "4x100kg press banca"

    def test_parse_valid_habit(self):
        response = {
            "intent": "activity",
            "data": {
                "activity_type": "reading",
                "category": "habit",
                "duration_minutes": 30,
                "distance_km": None,
                "detail": None,
                "confidence": 0.8,
            }
        }
        result = parse_activity(response)
        assert result is not None
        assert result.category == "habit"
        assert result.duration_minutes == 30

    def test_parse_low_confidence_returns_none(self):
        response = {
            "intent": "activity",
            "data": {
                "activity_type": "unknown",
                "category": "sport",
                "duration_minutes": None,
                "distance_km": None,
                "detail": None,
                "confidence": 0.2,
            }
        }
        result = parse_activity(response)
        assert result is None

    def test_parse_empty_data_returns_none(self):
        response = {"intent": "activity", "data": {}}
        result = parse_activity(response)
        assert result is None  # confidence defaults to 0.0

    def test_parse_missing_data_key(self):
        response = {"intent": "activity"}
        result = parse_activity(response)
        assert result is None


class TestParseReminder:
    """Tests for parsing reminder data from LLM responses."""

    def test_parse_create_reminder(self):
        response = {
            "intent": "reminder",
            "data": {
                "action": "create",
                "message": "meditar",
                "schedule": "08:00",
                "frequency": "daily",
            }
        }
        result = parse_reminder(response)
        assert result is not None
        assert result.action == "create"
        assert result.message == "meditar"
        assert result.schedule == "08:00"
        assert result.frequency == "daily"

    def test_parse_list_reminder(self):
        response = {
            "intent": "reminder",
            "data": {"action": "list"}
        }
        result = parse_reminder(response)
        assert result is not None
        assert result.action == "list"

    def test_parse_delete_reminder(self):
        response = {
            "intent": "reminder",
            "data": {"action": "delete", "message": "correr"}
        }
        result = parse_reminder(response)
        assert result is not None
        assert result.action == "delete"
        assert result.message == "correr"

    def test_parse_specific_days_reminder(self):
        # "recuérdame correr los lunes y miércoles a las 7:30"
        response = {
            "intent": "reminder",
            "data": {
                "action": "create",
                "message": "correr",
                "schedule": "07:30",
                "frequency": "specific_days",
                "schedule_days": "0,2",
            },
        }
        result = parse_reminder(response)
        assert result is not None
        assert result.action == "create"
        assert result.message == "correr"
        assert result.schedule == "07:30"
        assert result.frequency == "specific_days"
        assert result.schedule_days == "0,2"
        assert result.schedule_date is None

    def test_parse_once_reminder_with_date(self):
        # "el lunes 6 de julio a las 8am ir al Dr"
        response = {
            "intent": "reminder",
            "data": {
                "action": "create",
                "message": "ir al Dr",
                "schedule": "08:00",
                "frequency": "once",
                "schedule_date": "2026-07-06",
            },
        }
        result = parse_reminder(response)
        assert result is not None
        assert result.action == "create"
        assert result.message == "ir al Dr"
        assert result.schedule == "08:00"
        assert result.frequency == "once"
        assert result.schedule_date == "2026-07-06"

    def test_parse_weekends_reminder(self):
        # "recordatorio de gym solo fines de semana"
        response = {
            "intent": "reminder",
            "data": {
                "action": "create",
                "message": "gym",
                "schedule": "10:00",
                "frequency": "weekends",
            },
        }
        result = parse_reminder(response)
        assert result is not None
        assert result.frequency == "weekends"
        assert result.message == "gym"

    def test_parse_biweekly_reminder(self):
        # "cada 2 semanas ir al dentista" — interval lives in frequency
        response = {
            "intent": "reminder",
            "data": {
                "action": "create",
                "message": "ir al dentista",
                "frequency": "biweekly",
            },
        }
        result = parse_reminder(response)
        assert result is not None
        assert result.action == "create"
        assert result.message == "ir al dentista"
        # "biweekly" must survive as a frequency value (not coerced to daily)
        assert result.frequency == "biweekly"

    def test_parse_no_action_returns_none(self):
        response = {"intent": "reminder", "data": {}}
        result = parse_reminder(response)
        assert result is None

    def test_parse_missing_data_returns_none(self):
        response = {"intent": "reminder"}
        result = parse_reminder(response)
        assert result is None


class TestParseGoal:
    """Tests for parsing goal data from LLM responses."""

    def test_parse_weekly_goal(self):
        # "quiero correr 3 veces por semana"
        response = {
            "intent": "goal",
            "data": {
                "action": "create",
                "activity_type": "running",
                "target_count": 3,
                "period": "weekly",
                "description": "Correr 3x/semana",
                "ends_at": None,
            },
        }
        result = parse_goal(response)
        assert result is not None
        assert isinstance(result, GoalData)
        assert result.action == "create"
        assert result.activity_type == "running"
        assert result.target_count == 3
        assert result.period == "weekly"
        assert result.ends_at is None

    def test_parse_daily_goal(self):
        # "meta: meditar todos los días por 75 días"
        response = {
            "intent": "goal",
            "data": {
                "action": "create",
                "activity_type": "meditation",
                "target_count": 1,
                "period": "daily",
                "description": "Meditar diario",
                "ends_at": "2026-09-14",
            },
        }
        result = parse_goal(response)
        assert result is not None
        assert result.activity_type == "meditation"
        assert result.target_count == 1
        assert result.period == "daily"
        assert result.ends_at == "2026-09-14"

    def test_parse_specific_days_goal_maps_to_weekly_count(self):
        # "quiero correr los lunes, miércoles y viernes" → weekly, target_count=3
        response = {
            "intent": "goal",
            "data": {
                "action": "create",
                "activity_type": "running",
                "target_count": 3,
                "period": "weekly",
                "description": "Correr lun/mie/vie",
                "ends_at": None,
            },
        }
        result = parse_goal(response)
        assert result is not None
        assert result.activity_type == "running"
        assert result.period == "weekly"
        assert result.target_count == 3

    def test_parse_list_goal(self):
        response = {"intent": "goal", "data": {"action": "list"}}
        result = parse_goal(response)
        assert result is not None
        assert result.action == "list"
        # tolerant defaults when fields are absent
        assert result.target_count == 1
        assert result.period == "weekly"
        assert result.activity_type is None

    def test_parse_delete_goal(self):
        response = {
            "intent": "goal",
            "data": {"action": "delete", "activity_type": "running"},
        }
        result = parse_goal(response)
        assert result is not None
        assert result.action == "delete"
        assert result.activity_type == "running"

    def test_parse_no_action_returns_none(self):
        response = {"intent": "goal", "data": {}}
        result = parse_goal(response)
        assert result is None

    def test_parse_missing_data_returns_none(self):
        response = {"intent": "goal"}
        result = parse_goal(response)
        assert result is None
