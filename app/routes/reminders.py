"""Reminder API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.middleware import get_current_user
from app.models.user import User
from app.models.reminder import Reminder

router = APIRouter()


class ReminderOut(BaseModel):
    id: int
    schedule: str
    frequency: str
    message: str
    active: bool

    @classmethod
    def from_model(cls, r: Reminder) -> "ReminderOut":
        return cls(id=r.id, schedule=r.schedule, frequency=r.frequency, message=r.message, active=r.active)


class ReminderCreate(BaseModel):
    schedule: str
    frequency: str = "daily"
    message: str


class ReminderUpdate(BaseModel):
    schedule: str | None = None
    frequency: str | None = None
    message: str | None = None
    active: bool | None = None


@router.get("", response_model=list[ReminderOut])
async def list_reminders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reminder).where(Reminder.user_id == current_user.id).order_by(Reminder.created_at.desc())
    )
    return [ReminderOut.from_model(r) for r in result.scalars().all()]


@router.post("", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    body: ReminderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Basic schedule validation (HH:MM)
    parts = body.schedule.split(":")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise HTTPException(status_code=400, detail="Schedule must be HH:MM format")
    h, m = int(parts[0]), int(parts[1])
    if h < 0 or h > 23 or m < 0 or m > 59:
        raise HTTPException(status_code=400, detail="Invalid time")

    reminder = Reminder(
        user_id=current_user.id,
        schedule=body.schedule,
        frequency=body.frequency,
        message=body.message,
        active=True,
    )
    db.add(reminder)
    await db.flush()
    return ReminderOut.from_model(reminder)


@router.put("/{reminder_id}", response_model=ReminderOut)
async def update_reminder(
    reminder_id: int,
    body: ReminderUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == current_user.id)
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    if body.schedule is not None:
        reminder.schedule = body.schedule
    if body.frequency is not None:
        reminder.frequency = body.frequency
    if body.message is not None:
        reminder.message = body.message
    if body.active is not None:
        reminder.active = body.active

    await db.flush()
    return ReminderOut.from_model(reminder)


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == current_user.id)
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    await db.delete(reminder)
