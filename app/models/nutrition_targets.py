"""NutritionTargets: 1:1 with User. Daily kcal + macros + source (Req 4, 5)."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class NutritionTargets(Base):
    __tablename__ = "nutrition_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)  # 1:1
    kcal: Mapped[float] = mapped_column(Float)         # 800..6000
    protein_g: Mapped[float] = mapped_column(Float)    # 0..500
    fat_g: Mapped[float] = mapped_column(Float)        # 0..500
    carbs_g: Mapped[float] = mapped_column(Float)      # 0..1000
    source: Mapped[str] = mapped_column(String(10))    # 'derived' | 'manual'
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="nutrition_targets")
