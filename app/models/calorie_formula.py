"""Calorie formula model - to be implemented in task 1.3"""
from datetime import datetime

from sqlalchemy import String, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CalorieFormula(Base):
    """Calorie calculation formula for activity types"""
    __tablename__ = "calorie_formulas"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    activity_type: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    met_value: Mapped[float] = mapped_column(Float)
    distance_factor: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
