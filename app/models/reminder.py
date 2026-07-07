"""Reminder model - to be implemented in task 1.3"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Reminder(Base):
    """
    Reminder configuration model.
    
    Frequency types:
    - "daily": every day
    - "weekdays": Mon-Fri
    - "weekends": Sat-Sun
    - "specific_days": uses schedule_days JSON (e.g. "0,2,4" = Lun,Mie,Vie)
    - "once": one-time reminder, uses schedule_date
    - "biweekly": every 2 weeks
    """
    __tablename__ = "reminders"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    schedule: Mapped[str] = mapped_column(String(100))  # HH:MM
    frequency: Mapped[str] = mapped_column(String(50))  # daily, weekdays, weekends, specific_days, once, biweekly
    message: Mapped[str] = mapped_column(String(500))
    schedule_days: Mapped[str | None] = mapped_column(String(50))  # CSV of day numbers: "0,2,4" (Mon,Wed,Fri)
    schedule_date: Mapped[str | None] = mapped_column(String(20))  # "2026-07-06" for one-time
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_sent_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="reminders")
