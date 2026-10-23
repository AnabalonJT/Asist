"""Password reset token model for Telegram-delivered password recovery"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class PasswordResetToken(Base):
    """Single-use, short-lived token holding a bcrypt hash of a 6-digit recovery code"""
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(255), index=True)  # bcrypt hash of the 6-digit code
    used: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    expires_at: Mapped[datetime]

    # Relationships
    user: Mapped["User"] = relationship(back_populates="password_reset_tokens")
