"""User settings API routes."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.middleware import get_current_user
from app.models.user import User

router = APIRouter()


class UserSettings(BaseModel):
    show_calories: bool
    timezone: str


class SettingsUpdate(BaseModel):
    show_calories: bool | None = None
    timezone: str | None = None


@router.get("", response_model=UserSettings)
async def get_settings(current_user: User = Depends(get_current_user)):
    return UserSettings(
        show_calories=current_user.show_calories,
        timezone=current_user.timezone,
    )


@router.put("", response_model=UserSettings)
async def update_settings(
    body: SettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updates = {}
    if body.show_calories is not None:
        updates["show_calories"] = body.show_calories
    if body.timezone is not None:
        updates["timezone"] = body.timezone

    if updates:
        await db.execute(
            sql_update(User).where(User.id == current_user.id).values(**updates)
        )

    return UserSettings(
        show_calories=body.show_calories if body.show_calories is not None else current_user.show_calories,
        timezone=body.timezone if body.timezone is not None else current_user.timezone,
    )
