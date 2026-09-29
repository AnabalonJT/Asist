"""Food: global catalog entry with nutrition per 100 g. Shared across users."""
from datetime import datetime

from sqlalchemy import String, Float, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Food(Base):
    """A catalog food with nutrition per 100 g and dietary flags (Req 1, 7)."""
    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # 1..100 chars
    kcal_per_100g: Mapped[float] = mapped_column(Float)          # 0..900
    protein_g_per_100g: Mapped[float] = mapped_column(Float)     # 0..100
    fat_g_per_100g: Mapped[float] = mapped_column(Float)         # 0..100
    carbs_g_per_100g: Mapped[float] = mapped_column(Float)       # 0..100
    fiber_g_per_100g: Mapped[float | None] = mapped_column(Float)  # 0..100, optional (Req 1.4)

    # Dietary restriction flags (Req 7). Explicit booleans -> deterministic validation.
    is_meat: Mapped[bool] = mapped_column(Boolean, default=False)    # carne o pescado
    is_animal: Mapped[bool] = mapped_column(Boolean, default=False)  # origen animal (incl. huevo/lacteo)
    has_gluten: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(default=func.now())
