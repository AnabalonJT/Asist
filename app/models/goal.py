"""Goal model for habit tracking targets."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Goal(Base):
    """
    User goal for tracking habit/activity frequency.
    
    Examples:
    - "Correr 3 veces por semana"  → activity_type="running", target_count=3, period="weekly"
    - "Meditar todos los días"     → activity_type="meditation", target_count=1, period="daily"
    - "Gym 4 veces por semana"     → activity_type="gym", target_count=4, period="weekly"
    """
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    activity_type: Mapped[str] = mapped_column(String(100))  # matches Activity.activity_type
    description: Mapped[str] = mapped_column(String(200))  # human-readable: "Correr 3 veces por semana"
    target_count: Mapped[int] = mapped_column(Integer, default=1)  # how many times per period
    period: Mapped[str] = mapped_column(String(20), default="weekly")  # "daily", "weekly", "monthly"
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="goals")
