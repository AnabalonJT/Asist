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
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(index=True, default=func.now())
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="activities")
