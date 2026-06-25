"""Unit tests for SQLAlchemy models"""
import pytest
from datetime import datetime
from sqlalchemy import inspect

from app.models import User, Activity, Reminder, LinkingToken, CalorieFormula
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


class TestModelInheritance:
    """Tests for model inheritance from Base"""
    
    def test_all_models_inherit_from_base(self):
        """All models should inherit from Base"""
        models = [User, Activity, Reminder, LinkingToken, CalorieFormula]
        for model in models:
            assert issubclass(model, Base), f"{model.__name__} does not inherit from Base"
