"""UserFoodInventory: a food the user has available, with optional grams."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Float, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.food import Food


class UserFoodInventory(Base):
    __tablename__ = "user_food_inventory"
    __table_args__ = (UniqueConstraint("user_id", "food_id", name="uq_user_food"),)  # dedup (Req 2.2)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"), index=True)
    quantity_grams: Mapped[float | None] = mapped_column(Float)  # 1..100000, nullable (Req 2.1, 13.5)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    user: Mapped["User"] = relationship(back_populates="food_inventory")
    food: Mapped["Food"] = relationship()
