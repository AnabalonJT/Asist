"""Activity model - to be implemented in task 1.3"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Activity(Base):
    """Activity log model"""
    __tablename__ = "activities"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    activity_type: Mapped[str] = mapped_column(String(100), index=True)
    exercise_name: Mapped[str | None] = mapped_column(String(100))  # "Press Banca", "Sentadillas"
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[int] = mapped_column(Integer)
    sets_data: Mapped[str | None] = mapped_column(String(500))  # JSON: [{"reps":10,"weight_kg":50},...]
    timestamp: Mapped[datetime] = mapped_column(index=True, default=func.now())
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="activities")

    def sets_list(self) -> list[dict]:
        """Parse ``sets_data`` JSON into a list of set dicts.

        Each entry looks like ``{"reps": 10, "weight_kg": 50}``. Tolerant of
        ``None`` / empty / invalid JSON (returns ``[]``) so non-strength
        activities and legacy rows are handled gracefully. Mirrors the
        ``phases_list()`` pattern used by DietPhasePlan.
        """
        import json
        try:
            value = json.loads(self.sets_data or "[]")
            return value if isinstance(value, list) else []
        except (ValueError, TypeError):
            return []

    def total_volume(self) -> float:
        """Total training volume = sum of reps × weight_kg across all sets.

        Returns ``0`` when there is no strength data. Non-numeric or missing
        ``reps`` / ``weight_kg`` values are treated as 0.
        """
        total = 0.0
        for s in self.sets_list():
            if not isinstance(s, dict):
                continue
            try:
                reps = float(s.get("reps") or 0)
                weight = float(s.get("weight_kg") or 0)
            except (ValueError, TypeError):
                continue
            total += reps * weight
        return total
