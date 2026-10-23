"""Fitness profile model (1:1 with User). Reused by the future meal-planner."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Integer, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class FitnessProfile(Base):
    """Body data, equipment, level, availability and current goal for a user."""
    __tablename__ = "fitness_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)

    # Body data
    weight_kg: Mapped[float] = mapped_column(Float)          # 30..300
    height_cm: Mapped[float] = mapped_column(Float)          # 100..250
    age: Mapped[int] = mapped_column(Integer)                # 13..100
    sex: Mapped[str | None] = mapped_column(String(10))      # male|female|other (optional)

    # Level & availability
    level: Mapped[str] = mapped_column(String(20))           # principiante|intermedio|avanzado
    equipment: Mapped[str] = mapped_column(String(300), default="[]")  # JSON list of Equipment_Item
    days_per_week: Mapped[int] = mapped_column(Integer)      # 1..7
    minutes_per_session: Mapped[int] = mapped_column(Integer)  # 10..240

    # Goal (kept on the profile; at most one active goal - Req 2.7)
    goal_type: Mapped[str | None] = mapped_column(String(20))  # Goal_Type
    target_weight_kg: Mapped[float | None] = mapped_column(Float)     # only for weight_target
    target_date: Mapped[str | None] = mapped_column(String(20))       # ISO date, only weight_target
    performance_target: Mapped[str | None] = mapped_column(String(200))  # only performance

    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="fitness_profile")

    # -- Meal_Planner consumption helpers (Req 1.9, 3.6) --
    def equipment_list(self) -> list[str]:
        import json
        try:
            value = json.loads(self.equipment or "[]")
            return value if isinstance(value, list) else []
        except (ValueError, TypeError):
            return []

    def meal_planner_view(self) -> dict:
        """Expose weight/target/date/level for the Meal_Planner."""
        return {
            "current_weight_kg": self.weight_kg,
            "target_weight_kg": self.target_weight_kg,
            "target_date": self.target_date,
            "level": self.level,
            "goal_type": self.goal_type,
        }
