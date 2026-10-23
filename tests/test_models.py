"""Unit tests for SQLAlchemy models"""
import pytest
from datetime import datetime
from sqlalchemy import inspect

from app.models import User, Activity, Reminder, LinkingToken, CalorieFormula, Goal
from app.database import Base


class TestUserModel:
    """Tests for User model structure"""
    
    def test_user_model_table_name(self):
        """User model should have correct table name"""
        assert User.__tablename__ == "users"
    
    def test_user_model_has_required_columns(self):
        """User model should have all required columns"""
        inspector = inspect(User)
        column_names = [col.key for col in inspector.columns]
        
        required_columns = [
            'id', 'email', 'password_hash', 'is_admin', 
            'telegram_chat_id', 'created_at', 'updated_at'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"
    
    def test_user_model_has_relationships(self):
        """User model should have correct relationships"""
        inspector = inspect(User)
        relationship_names = [rel.key for rel in inspector.relationships]
        
        required_relationships = ['activities', 'reminders', 'linking_tokens']
        
        for rel in required_relationships:
            assert rel in relationship_names, f"Missing relationship: {rel}"
    
    def test_user_model_primary_key(self):
        """User model should have id as primary key"""
        inspector = inspect(User)
        primary_keys = [col.name for col in inspector.primary_key]
        assert 'id' in primary_keys


class TestActivityModel:
    """Tests for Activity model structure"""
    
    def test_activity_model_table_name(self):
        """Activity model should have correct table name"""
        assert Activity.__tablename__ == "activities"
    
    def test_activity_model_has_required_columns(self):
        """Activity model should have all required columns"""
        inspector = inspect(Activity)
        column_names = [col.key for col in inspector.columns]
        
        required_columns = [
            'id', 'user_id', 'activity_type', 'duration_minutes',
            'distance_km', 'calories', 'timestamp', 'created_at'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"
    
    def test_activity_model_has_user_relationship(self):
        """Activity model should have user relationship"""
        inspector = inspect(Activity)
        relationship_names = [rel.key for rel in inspector.relationships]
        assert 'user' in relationship_names
    
    def test_activity_model_foreign_key(self):
        """Activity model should have foreign key to users"""
        inspector = inspect(Activity)
        user_id_col = inspector.columns['user_id']
        assert len(user_id_col.foreign_keys) > 0

    def test_activity_model_has_strength_columns(self):
        """Activity model should have strength-logging columns (nullable)"""
        inspector = inspect(Activity)
        columns = {col.key: col for col in inspector.columns}
        assert 'exercise_name' in columns
        assert 'sets_data' in columns
        # Backward compatible: both must be nullable so legacy rows stay valid
        assert columns['exercise_name'].nullable is True
        assert columns['sets_data'].nullable is True

    def test_sets_list_parses_valid_json(self):
        """sets_list() returns the parsed list of sets"""
        activity = Activity(sets_data='[{"reps": 10, "weight_kg": 50}, {"reps": 8, "weight_kg": 60}]')
        assert activity.sets_list() == [
            {"reps": 10, "weight_kg": 50},
            {"reps": 8, "weight_kg": 60},
        ]

    def test_sets_list_tolerates_none_and_invalid(self):
        """sets_list() returns [] for None, empty, or invalid JSON (backward compatible)"""
        assert Activity(sets_data=None).sets_list() == []
        assert Activity(sets_data="").sets_list() == []
        assert Activity(sets_data="not json").sets_list() == []
        # A JSON object (not a list) is rejected
        assert Activity(sets_data='{"reps": 10}').sets_list() == []

    def test_total_volume_sums_reps_times_weight(self):
        """total_volume() = sum of reps × weight_kg across sets"""
        activity = Activity(sets_data='[{"reps": 10, "weight_kg": 50}, {"reps": 8, "weight_kg": 60}]')
        assert activity.total_volume() == 10 * 50 + 8 * 60

    def test_total_volume_zero_without_strength_data(self):
        """total_volume() returns 0 when there is no strength data"""
        assert Activity(sets_data=None).total_volume() == 0
        assert Activity(sets_data='[{"reps": 10}]').total_volume() == 0


class TestReminderModel:
    """Tests for Reminder model structure"""
    
    def test_reminder_model_table_name(self):
        """Reminder model should have correct table name"""
        assert Reminder.__tablename__ == "reminders"
    
    def test_reminder_model_has_required_columns(self):
        """Reminder model should have all required columns"""
        inspector = inspect(Reminder)
        column_names = [col.key for col in inspector.columns]
        
        required_columns = [
            'id', 'user_id', 'schedule', 'frequency', 'message',
            'active', 'last_sent_at', 'created_at', 'updated_at'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"

    def test_reminder_model_has_flexible_schedule_columns(self):
        """Reminder should have the Phase-2 flexible-schedule columns.

        The spec's schedule_type + schedule_interval are encoded in the single
        'frequency' column (biweekly is a frequency value), so the only new
        columns are schedule_days (CSV) and schedule_date (YYYY-MM-DD), plus the
        optional challenge_id link.
        """
        inspector = inspect(Reminder)
        column_names = [col.key for col in inspector.columns]

        for col in ['schedule_days', 'schedule_date', 'challenge_id']:
            assert col in column_names, f"Missing flexible-schedule column: {col}"

    def test_reminder_flexible_columns_are_nullable(self):
        """Flexible-schedule columns must be nullable (backward compatible).

        Legacy daily/weekdays/weekends reminders have no specific days, date, or
        challenge, so these columns must accept NULL.
        """
        columns = {col.key: col for col in inspect(Reminder).columns}
        assert columns['schedule_days'].nullable is True
        assert columns['schedule_date'].nullable is True
        assert columns['challenge_id'].nullable is True
        # Core scheduling columns stay required.
        assert columns['schedule'].nullable is False
        assert columns['frequency'].nullable is False

    def test_reminder_specific_days_example(self):
        """'lunes y miércoles' maps to frequency='specific_days', schedule_days='0,2'."""
        reminder = Reminder(
            user_id=1,
            schedule="07:30",
            frequency="specific_days",
            message="correr",
            schedule_days="0,2",
        )
        assert reminder.frequency == "specific_days"
        assert reminder.schedule_days == "0,2"

    def test_reminder_weekend_example(self):
        """'fin de semana' ([5,6]) maps to frequency='weekends'."""
        reminder = Reminder(
            user_id=1,
            schedule="10:00",
            frequency="weekends",
            message="gym",
        )
        assert reminder.frequency == "weekends"

    def test_reminder_once_example(self):
        """A one-time reminder uses frequency='once' + schedule_date."""
        reminder = Reminder(
            user_id=1,
            schedule="08:00",
            frequency="once",
            message="ir al Dr",
            schedule_date="2026-07-06",
        )
        assert reminder.frequency == "once"
        assert reminder.schedule_date == "2026-07-06"

    def test_reminder_biweekly_interval_example(self):
        """The spec's 'every_other_week'/'biweekly' interval is a frequency value."""
        reminder = Reminder(
            user_id=1,
            schedule="09:00",
            frequency="biweekly",
            message="revisión",
        )
        assert reminder.frequency == "biweekly"

    def test_reminder_model_has_user_relationship(self):
        """Reminder model should have user relationship"""
        inspector = inspect(Reminder)
        relationship_names = [rel.key for rel in inspector.relationships]
        assert 'user' in relationship_names
    
    def test_reminder_model_foreign_key(self):
        """Reminder model should have foreign key to users"""
        inspector = inspect(Reminder)
        user_id_col = inspector.columns['user_id']
        assert len(user_id_col.foreign_keys) > 0


class TestLinkingTokenModel:
    """Tests for LinkingToken model structure"""
    
    def test_linking_token_model_table_name(self):
        """LinkingToken model should have correct table name"""
        assert LinkingToken.__tablename__ == "linking_tokens"
    
    def test_linking_token_model_has_required_columns(self):
        """LinkingToken model should have all required columns"""
        inspector = inspect(LinkingToken)
        column_names = [col.key for col in inspector.columns]
        
        required_columns = [
            'id', 'user_id', 'token', 'used', 'created_at', 'expires_at'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"
    
    def test_linking_token_model_has_user_relationship(self):
        """LinkingToken model should have user relationship"""
        inspector = inspect(LinkingToken)
        relationship_names = [rel.key for rel in inspector.relationships]
        assert 'user' in relationship_names
    
    def test_linking_token_model_foreign_key(self):
        """LinkingToken model should have foreign key to users"""
        inspector = inspect(LinkingToken)
        user_id_col = inspector.columns['user_id']
        assert len(user_id_col.foreign_keys) > 0


class TestCalorieFormulaModel:
    """Tests for CalorieFormula model structure"""
    
    def test_calorie_formula_model_table_name(self):
        """CalorieFormula model should have correct table name"""
        assert CalorieFormula.__tablename__ == "calorie_formulas"
    
    def test_calorie_formula_model_has_required_columns(self):
        """CalorieFormula model should have all required columns"""
        inspector = inspect(CalorieFormula)
        column_names = [col.key for col in inspector.columns]
        
        required_columns = [
            'id', 'activity_type', 'met_value', 'distance_factor',
            'created_at', 'updated_at'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"
    
    def test_calorie_formula_model_primary_key(self):
        """CalorieFormula model should have id as primary key"""
        inspector = inspect(CalorieFormula)
        primary_keys = [col.name for col in inspector.primary_key]
        assert 'id' in primary_keys


class TestGoalModel:
    """Tests for Goal model structure (habit goals system)"""

    def test_goal_model_table_name(self):
        """Goal model should map to the 'goals' table"""
        assert Goal.__tablename__ == "goals"

    def test_goal_model_has_required_columns(self):
        """Goal model should have all spec columns.

        The spec's 'target_frequency (times per period)' is represented by
        target_count + period together.
        """
        inspector = inspect(Goal)
        column_names = [col.key for col in inspector.columns]

        required_columns = [
            'id', 'user_id', 'challenge_id', 'activity_type', 'description',
            'target_count', 'period', 'ends_at', 'active', 'closed_notified',
            'created_at',
        ]

        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"

    def test_goal_model_primary_key(self):
        """Goal model should have id as primary key"""
        inspector = inspect(Goal)
        primary_keys = [col.name for col in inspector.primary_key]
        assert 'id' in primary_keys

    def test_goal_model_nullable_columns(self):
        """challenge_id and ends_at are optional; user_id/activity_type are required"""
        columns = {col.key: col for col in inspect(Goal).columns}
        assert columns['challenge_id'].nullable is True
        assert columns['ends_at'].nullable is True
        assert columns['user_id'].nullable is False
        assert columns['activity_type'].nullable is False

    def test_goal_model_column_defaults(self):
        """target_count, period and active have sensible defaults"""
        columns = {col.key: col for col in inspect(Goal).columns}
        assert columns['target_count'].default.arg == 1
        assert columns['period'].default.arg == "weekly"
        assert columns['active'].default.arg is True
        assert columns['closed_notified'].default.arg is False

    def test_goal_model_foreign_keys(self):
        """Goal references users and (optionally) challenges"""
        columns = {col.key: col for col in inspect(Goal).columns}
        assert len(columns['user_id'].foreign_keys) > 0
        assert len(columns['challenge_id'].foreign_keys) > 0

    def test_goal_model_has_relationships(self):
        """Goal should relate to user and challenge"""
        relationship_names = [rel.key for rel in inspect(Goal).relationships]
        assert 'user' in relationship_names
        assert 'challenge' in relationship_names

    def test_goal_supports_weekly_frequency_example(self):
        """'correr 3 veces por semana' maps to target_count=3, period='weekly'"""
        goal = Goal(
            user_id=1,
            activity_type="correr",
            description="correr 3 veces por semana",
            target_count=3,
            period="weekly",
        )
        assert goal.target_count == 3
        assert goal.period == "weekly"

    def test_goal_supports_daily_example(self):
        """'meditar todos los días' maps to period='daily'"""
        goal = Goal(
            user_id=1,
            activity_type="meditar",
            description="meditar todos los días",
            period="daily",
        )
        assert goal.period == "daily"


class TestModelInheritance:
    """Tests for model inheritance from Base"""
    
    def test_all_models_inherit_from_base(self):
        """All models should inherit from Base"""
        models = [User, Activity, Reminder, LinkingToken, CalorieFormula, Goal]
        for model in models:
            assert issubclass(model, Base), f"{model.__name__} does not inherit from Base"
