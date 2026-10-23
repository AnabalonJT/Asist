"""DietaryProfile: 1:1 with User. Diet flags + allergens list (Req 3)."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class DietaryProfile(Base):
    __tablename__ = "dietary_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)  # 1:1
    vegetarian: Mapped[bool] = mapped_column(Boolean, default=False)
    vegan: Mapped[bool] = mapped_column(Boolean, default=False)
    gluten_free: Mapped[bool] = mapped_column(Boolean, default=False)
    allergens: Mapped[str] = mapped_column(String(500), default="[]")  # JSON list of strings (Req 3.1)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="dietary_profile")

    def allergen_list(self) -> list[str]:
        import json
        try:
            value = json.loads(self.allergens or "[]")
            return [str(a) for a in value] if isinstance(value, list) else []
        except (ValueError, TypeError):
            return []
