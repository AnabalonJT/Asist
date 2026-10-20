"""RecipeIngredient: a Food plus grams within a Recipe (Req 4)."""
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.recipe import Recipe
    from app.models.food import Food


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"), index=True)
    grams: Mapped[float] = mapped_column(Float)   # 1..100000

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")
    food: Mapped["Food"] = relationship()
