"""Challenge model - groups multiple goals under one objective."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.goal import Goal


class Challenge(Base):
    """
    A challenge groups multiple goals under one shared deadline.
    
    Examples:
    - "75 días de disciplina" → deporte + cama + meditar, ends_at = hoy + 75 días
    - "Preparación maratón" → correr 3x/semana + meditar diario, ends_at = hoy + 3 meses
    """
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))  # "75 días de disciplina"
    ends_at: Mapped[str | None] = mapped_column(String(20))  # "2026-09-22" or null
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="challenges")
    goals: Mapped[list["Goal"]] = relationship(back_populates="challenge")
