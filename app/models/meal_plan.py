"""MealPlan: weekly plan. At most one active per user (Req 6.2, 6.11)."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Boolean, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class MealPlan(Base):
    __tablename__ = "meal_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # JSON: [{"day":"Lunes","meals":[{"type":"desayuno","items":[{"food_name":"Avena","grams":80}]}],
    #         "totals":{"kcal":2100,"protein_g":160,"fat_g":60,"carbs_g":220}}, ... x7]
    structure: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    user: Mapped["User"] = relationship(back_populates="meal_plans")

    def structure_list(self) -> list[dict]:
        import json
        try:
            value = json.loads(self.structure or "[]")
            return value if isinstance(value, list) else []
        except (ValueError, TypeError):
            return []
