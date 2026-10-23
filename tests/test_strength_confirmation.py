"""Unit tests for the Telegram strength-activity confirmation message builder.

Covers the pure helpers in ``app.services.telegram_bot`` so we can verify the
message format (exercise name as title, sets detail line, total volume instead
of calories, and graceful fallbacks) without a real Telegram update.
"""
from app.services.telegram_bot import _build_strength_confirmation, _format_set


class TestFormatSet:
    def test_reps_and_weight(self):
        assert _format_set({"reps": 10, "weight_kg": 40}) == "10×40kg"

    def test_drops_trailing_zero_decimal(self):
        assert _format_set({"reps": 8, "weight_kg": 60.0}) == "8×60kg"

    def test_keeps_real_decimal(self):
        assert _format_set({"reps": 5, "weight_kg": 42.5}) == "5×42.5kg"

    def test_null_weight_shows_only_reps(self):
        assert _format_set({"reps": 10, "weight_kg": None}) == "10 reps"

    def test_non_dict_is_empty(self):
        assert _format_set("nope") == ""


class TestBuildStrengthConfirmation:
    def test_shows_exercise_name_sets_and_volume(self):
        msg = _build_strength_confirmation(
            icon="💪",
            exercise_name="Press Banca",
            activity_type="Press Banca",
            sets=[
                {"reps": 10, "weight_kg": 40},
                {"reps": 10, "weight_kg": 50},
                {"reps": 8, "weight_kg": 60},
            ],
            detail=None,
            duration_minutes=None,
            calories=120,
        )
        # Title is the exercise name, not a generic word.
        assert "*Press Banca*" in msg
        assert "Strength" not in msg and "Weights" not in msg
        # Sets detail line: N series + each "reps×weightkg".
        assert "3 series: 10×40kg, 10×50kg, 8×60kg" in msg
        # Total volume: 10*40 + 10*50 + 8*60 = 1380, with thousands separator.
        assert "Vol: 1,380 kg" in msg
        # Calories are NOT shown for a detailed strength entry.
        assert "cal" not in msg

    def test_uses_activity_type_when_no_exercise_name(self):
        msg = _build_strength_confirmation(
            icon="💪",
            exercise_name=None,
            activity_type="sentadillas",
            sets=[{"reps": 12, "weight_kg": 70}],
            detail=None,
            duration_minutes=None,
            calories=0,
        )
        assert "*Sentadillas*" in msg
        assert "1 series: 12×70kg" in msg
        assert "Vol: 840 kg" in msg

    def test_null_weight_set_is_handled(self):
        msg = _build_strength_confirmation(
            icon="💪",
            exercise_name="Dominadas",
            activity_type="Dominadas",
            sets=[{"reps": 10, "weight_kg": None}, {"reps": 8, "weight_kg": None}],
            detail=None,
            duration_minutes=None,
            calories=0,
        )
        assert "2 series: 10 reps, 8 reps" in msg
        # No weight anywhere → volume is 0, so no volume line.
        assert "Vol:" not in msg

    def test_no_sets_falls_back_to_duration_and_calories(self):
        # e.g. "hice gym 40 min" with no weights.
        msg = _build_strength_confirmation(
            icon="🏋️",
            exercise_name=None,
            activity_type="gym",
            sets=None,
            detail=None,
            duration_minutes=40,
            calories=200,
        )
        assert "*Gym*" in msg
        assert "40 min" in msg
        assert "~200 cal" in msg
        assert "series" not in msg
        assert "Vol:" not in msg

    def test_no_sets_with_detail(self):
        msg = _build_strength_confirmation(
            icon="💪",
            exercise_name=None,
            activity_type="crossfit",
            sets=[],
            detail="WOD Murph",
            duration_minutes=None,
            calories=0,
        )
        assert "*Crossfit*" in msg
        assert "WOD Murph" in msg

    def test_large_volume_uses_thousands_separator(self):
        msg = _build_strength_confirmation(
            icon="💪",
            exercise_name="Peso Muerto",
            activity_type="Peso Muerto",
            sets=[{"reps": 10, "weight_kg": 120}, {"reps": 10, "weight_kg": 130}],
            detail=None,
            duration_minutes=None,
            calories=0,
        )
        # 10*120 + 10*130 = 2500
        assert "Vol: 2,500 kg" in msg
