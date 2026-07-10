"""Goal model for habit tracking targets."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.challenge import Challenge


class Goal(Base):
    """
    User goal for tracking habit/activity frequency.
    Can be standalone or part of a Challenge.
    """
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    challenge_id: Mapped[int | None] = mapped_column(ForeignKey("challenges.id"), index=True)
    activity_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(200))
    target_count: Mapped[int] = mapped_column(Integer, default=1)
    period: Mapped[str] = mapped_column(String(20), default="weekly")
    ends_at: Mapped[str | None] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="goals")
    challenge: Mapped["Challenge | None"] = relationship(back_populates="goals")
