"""Weight_Entry: a body-weight measurement on a given date."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class WeightEntry(Base):
    __tablename__ = "weight_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    weight_kg: Mapped[float] = mapped_column(Float)      # 30..300
    entry_date: Mapped[str] = mapped_column(String(20), index=True)  # ISO date "YYYY-MM-DD"
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    user: Mapped["User"] = relationship(back_populates="weight_entries")
