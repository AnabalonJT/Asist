"""Unit tests for LLM response parsing logic."""
import pytest
from app.services.llm_service import parse_activity, parse_reminder, ActivityData, ReminderData


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

    def test_parse_no_action_returns_none(self):
        response = {"intent": "reminder", "data": {}}
        result = parse_reminder(response)
        assert result is None

    def test_parse_missing_data_returns_none(self):
        response = {"intent": "reminder"}
        result = parse_reminder(response)
        assert result is None
