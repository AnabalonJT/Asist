"""UserFoodInventory: a food or recipe the user has available, with optional grams."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Float, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.food import Food
    from app.models.recipe import Recipe


class UserFoodInventory(Base):
    __tablename__ = "user_food_inventory"
    __table_args__ = (
        UniqueConstraint("user_id", "food_id", name="uq_user_food"),      # dedup Food (Req 2.2)
        UniqueConstraint("user_id", "recipe_id", name="uq_user_recipe"),  # dedup Recipe (Req 5.1)
        CheckConstraint(
            "(food_id IS NOT NULL) <> (recipe_id IS NOT NULL)",
            name="ck_food_xor_recipe",
        ),  # exactly one of food_id / recipe_id (Req 5.1)
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    food_id: Mapped[int | None] = mapped_column(ForeignKey("foods.id"), index=True, nullable=True)
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"), index=True, nullable=True)
    quantity_grams: Mapped[float | None] = mapped_column(Float)  # 1..100000, nullable (Req 2.1, 13.5)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    user: Mapped["User"] = relationship(back_populates="food_inventory")
    food: Mapped["Food | None"] = relationship()
    recipe: Mapped["Recipe | None"] = relationship()
