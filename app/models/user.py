"""User model - to be implemented in task 1.3"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.reminder import Reminder
    from app.models.linking_token import LinkingToken
    from app.models.password_reset_token import PasswordResetToken
    from app.models.goal import Goal
    from app.models.challenge import Challenge
    from app.models.fitness_profile import FitnessProfile
    from app.models.weight_entry import WeightEntry
    from app.models.workout_plan import WorkoutPlan
    from app.models.user_food_inventory import UserFoodInventory
    from app.models.dietary_profile import DietaryProfile
    from app.models.nutrition_targets import NutritionTargets
    from app.models.meal_plan import MealPlan


class User(Base):
    """User account model"""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Santiago")
    show_calories: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
    
    # Relationships
    activities: Mapped[list["Activity"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    linking_tokens: Mapped[list["LinkingToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    goals: Mapped[list["Goal"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    challenges: Mapped[list["Challenge"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    fitness_profile: Mapped["FitnessProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    weight_entries: Mapped[list["WeightEntry"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    workout_plans: Mapped[list["WorkoutPlan"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    # Meal_Planner relationships
    food_inventory: Mapped[list["UserFoodInventory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    dietary_profile: Mapped["DietaryProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    nutrition_targets: Mapped["NutritionTargets | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    meal_plans: Mapped[list["MealPlan"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
