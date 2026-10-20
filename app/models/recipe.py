"""Recipe: a user-owned (private) recipe composed of Food ingredients (Req 4)."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.recipe_ingredient import RecipeIngredient


class Recipe(Base):
    """A private recipe owned by a user; nutrition is derived from its ingredients (Req 4)."""
    __tablename__ = "recipes"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_recipe_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # owner (private)
    name: Mapped[str] = mapped_column(String(100))                            # 1..100 chars
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
