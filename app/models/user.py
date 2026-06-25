"""User model - to be implemented in task 1.3"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.reminder import Reminder
    from app.models.linking_token import LinkingToken


class User(Base):
    """User account model"""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Santiago")
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
    
    # Relationships
    activities: Mapped[list["Activity"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    linking_tokens: Mapped[list["LinkingToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
