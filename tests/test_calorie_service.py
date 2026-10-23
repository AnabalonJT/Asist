"""Unit tests for CalorieService."""
import pytest
from app.services.calorie_service import calorie_service


class TestCalorieEstimation:
    """Tests for calorie estimation logic."""

    def test_running_with_distance(self):
        """Running with distance uses distance_factor (60 cal/km)."""
        result = calorie_service.estimate("running", distance_km=5.0)
        assert result == 300  # 5 * 60

    def test_running_with_duration(self):
        """Running with duration uses MET formula."""
        result = calorie_service.estimate("running", duration_minutes=60)
        # MET 9.8 * 70kg * 1h = 686
        assert result == 686

    def test_running_distance_takes_priority(self):
        """When both distance and duration given, distance_factor wins."""
        result = calorie_service.estimate("running", duration_minutes=30, distance_km=5.0)
        assert result == 300  # distance_factor used

    def test_walking_with_distance(self):
        """Walking distance factor is 40 cal/km."""
        result = calorie_service.estimate("walking", distance_km=3.0)
        assert result == 120

    def test_cycling_with_distance(self):
        """Cycling distance factor is 35 cal/km."""
        result = calorie_service.estimate("cycling", distance_km=10.0)
        assert result == 350

    def test_gym_with_duration(self):
        """Gym uses MET 5.0."""
        result = calorie_service.estimate("gym", duration_minutes=60)
        # 5.0 * 70 * 1.0 = 350
        assert result == 350

    def test_yoga_with_duration(self):
        """Yoga uses MET 3.0."""
        result = calorie_service.estimate("yoga", duration_minutes=30)
        # 3.0 * 70 * 0.5 = 105
        assert result == 105

    def test_swimming_with_duration(self):
        """Swimming uses MET 8.0."""
        result = calorie_service.estimate("swimming", duration_minutes=45)
        # 8.0 * 70 * 0.75 = 420
        assert result == 420

    def test_weights_with_duration(self):
        """Weights uses MET 6.0."""
        result = calorie_service.estimate("weights", duration_minutes=30)
        # 6.0 * 70 * 0.5 = 210
        assert result == 210

    def test_unknown_activity_uses_default_met(self):
        """Unknown activity uses default MET of 5.0."""
        result = calorie_service.estimate("parkour", duration_minutes=60)
        # 5.0 * 70 * 1.0 = 350
        assert result == 350

    def test_zero_duration_returns_zero(self):
        """Zero duration returns 0 calories."""
        result = calorie_service.estimate("running", duration_minutes=0)
        assert result == 0

    def test_no_duration_no_distance_returns_zero(self):
        """No duration and no distance returns 0."""
        result = calorie_service.estimate("gym")
        assert result == 0

    def test_meditation_with_duration(self):
        """Meditation (habit) still calculates if asked."""
        result = calorie_service.estimate("meditation", duration_minutes=20)
        # 1.5 * 70 * (20/60) = 35
        assert result == 35

    def test_case_insensitive(self):
        """Activity type lookup is case-insensitive."""
        result = calorie_service.estimate("Running", distance_km=5.0)
        assert result == 300

    def test_positive_calories_for_any_valid_input(self):
        """Any activity with positive duration should produce positive calories."""
        activities = ["running", "walking", "cycling", "gym", "swimming", "yoga", "weights"]
        for activity in activities:
            result = calorie_service.estimate(activity, duration_minutes=30)
            assert result > 0, f"{activity} with 30min should have calories > 0"
