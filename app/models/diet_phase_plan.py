"""DietPhasePlan: progressive A→B diet split into ordered phases.

At most one active plan per user. The ordered phases live as a JSON tree in a
Text column (same pattern as WorkoutPlan.structure / MealPlan.structure).
User-facing text is Spanish; identifiers and comments are English.
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Boolean, Float, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class DietPhasePlan(Base):
    __tablename__ = "diet_phase_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    start_weight_kg: Mapped[float] = mapped_column(Float)   # original A
    target_weight_kg: Mapped[float] = mapped_column(Float)  # final B
    goal_reached: Mapped[bool] = mapped_column(Boolean, default=False)

    # JSON list of phases. Each phase:
    # {"index": int, "start_weight": float, "end_weight": float,
    #  "kcal": float, "protein_g": float, "fat_g": float, "carbs_g": float,
    #  "status": "active"|"completed"|"pending",
    #  "weeks": float, "start_date": str|None, "end_date": str|None,
    #  "maintenance": bool}
    phases: Mapped[str] = mapped_column(Text, default="[]")

    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="diet_phase_plans")

    def phases_list(self) -> list[dict]:
        import json
        try:
            value = json.loads(self.phases or "[]")
            return value if isinstance(value, list) else []
        except (ValueError, TypeError):
            return []

    def active_phase(self) -> dict | None:
        for phase in self.phases_list():
            if phase.get("status") == "active":
                return phase
        return None
