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
    Reminder configuration model (flexible schedules — Phase 2, advanced reminders).

    Schema reconciliation note:
    The spec task lists separate ``schedule_type`` and ``schedule_interval``
    fields, but the design (see design.md "Reminder Model") and the entire
    implementation (scheduler.py, llm_service.py, routes/reminders.py) encode
    BOTH concepts in the single ``frequency`` column. ``frequency`` therefore
    carries the spec's ``schedule_type`` AND its ``schedule_interval``
    ("biweekly" is simply a frequency value). We deliberately keep one column
    instead of adding redundant ``schedule_type``/``schedule_interval`` columns,
    which would fragment the schema and break the scheduler/LLM that read
    ``frequency``.

    ``frequency`` values (schedule_type + interval combined):
    - "daily": every day
    - "weekdays": Mon-Fri
    - "weekends": Sat-Sun  (spec's [5,6] "fin de semana")
    - "specific_days": uses schedule_days CSV (e.g. "0,2" = Lun,Mie)
    - "once": one-time reminder, uses schedule_date
    - "biweekly": every 2 weeks (spec's "every_other_week"/"biweekly" interval,
      driven by last_sent_at)
    - "weekly": once a week (Monday)

    All flexible-schedule columns (schedule_days, schedule_date, challenge_id)
    are nullable so legacy reminders (daily/weekdays/weekends) stay valid.
    """
    __tablename__ = "reminders"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    schedule: Mapped[str] = mapped_column(String(100))  # HH:MM
    # Encodes the spec's schedule_type AND schedule_interval in one column:
    # daily, weekdays, weekends, specific_days, once, biweekly, weekly
    frequency: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(String(500))
    schedule_days: Mapped[str | None] = mapped_column(String(50))  # CSV of day numbers: "0,2,4" (Mon,Wed,Fri)
    schedule_date: Mapped[str | None] = mapped_column(String(20))  # "2026-07-06" for one-time
    challenge_id: Mapped[int | None] = mapped_column(ForeignKey("challenges.id"), index=True)  # link to a challenge, if any
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_sent_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="reminders")
