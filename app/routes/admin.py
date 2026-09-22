"""Admin API: system-wide usage overview and per-user usage breakdown.

Administrator-only, read-only aggregation endpoints under the /api/admin prefix.
Every endpoint is protected by the shared get_current_admin dependency.

Privacy by construction: the response models below never declare password_hash,
authentication token, or raw telegram_chat_id fields. Telegram association is
surfaced only as the derived telegram_linked boolean.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.middleware import get_current_admin
from app.models.user import User
from app.models.activity import Activity
from app.models.goal import Goal
from app.models.reminder import Reminder
from app.models.challenge import Challenge

router = APIRouter()


class AdminOverview(BaseModel):
    total_users: int
    telegram_linked_users: int
    total_activities: int
    total_goals: int
    total_reminders: int
    total_challenges: int
    active_users_7d: int
    active_users_30d: int


class AdminUserSummary(BaseModel):
    id: int
    email: str
    telegram_linked: bool
    created_at: str
    activity_count: int
    goal_count: int
    reminder_count: int
    challenge_count: int


class AdminUserDetail(AdminUserSummary):
    activities_7d: int
    activities_30d: int
    last_activity_at: str | None


@router.get("/overview", response_model=AdminOverview)
async def admin_overview(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return system-wide aggregate usage statistics."""
    total_users = (
        await db.execute(select(func.count()).select_from(User))
    ).scalar() or 0

    telegram_linked_users = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.telegram_chat_id.is_not(None))
        )
    ).scalar() or 0

    total_activities = (
        await db.execute(select(func.count()).select_from(Activity))
    ).scalar() or 0

    total_goals = (
        await db.execute(select(func.count()).select_from(Goal))
    ).scalar() or 0

    total_reminders = (
        await db.execute(select(func.count()).select_from(Reminder))
    ).scalar() or 0

    total_challenges = (
        await db.execute(select(func.count()).select_from(Challenge))
    ).scalar() or 0

    now = datetime.utcnow()
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    active_users_7d = (
        await db.execute(
            select(func.count(func.distinct(Activity.user_id)))
            .where(Activity.timestamp >= cutoff_7d)
        )
    ).scalar() or 0

    active_users_30d = (
        await db.execute(
            select(func.count(func.distinct(Activity.user_id)))
            .where(Activity.timestamp >= cutoff_30d)
        )
    ).scalar() or 0

    return AdminOverview(
        total_users=total_users,
        telegram_linked_users=telegram_linked_users,
        total_activities=total_activities,
        total_goals=total_goals,
        total_reminders=total_reminders,
        total_challenges=total_challenges,
        active_users_7d=active_users_7d,
        active_users_30d=active_users_30d,
    )


@router.get("/users", response_model=list[AdminUserSummary])
async def admin_users(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return one AdminUserSummary per user.

    Uses a fixed number of queries regardless of user count: one query to load
    all users, plus one grouped-count query per entity, merged in Python.
    """
    users = (await db.execute(select(User))).scalars().all()

    async def count_map(model) -> dict[int, int]:
        rows = await db.execute(
            select(model.user_id, func.count()).group_by(model.user_id)
        )
        return {user_id: n for user_id, n in rows.all()}

    activity_counts = await count_map(Activity)
    goal_counts = await count_map(Goal)
    reminder_counts = await count_map(Reminder)
    challenge_counts = await count_map(Challenge)

    return [
        AdminUserSummary(
            id=u.id,
            email=u.email,
            telegram_linked=u.telegram_chat_id is not None,
            created_at=u.created_at.isoformat() if u.created_at else "",
            activity_count=activity_counts.get(u.id, 0),
            goal_count=goal_counts.get(u.id, 0),
            reminder_count=reminder_counts.get(u.id, 0),
            challenge_count=challenge_counts.get(u.id, 0),
        )
        for u in users
    ]


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def admin_user_detail(
    user_id: int,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return extended usage detail for a single user, or 404 if not found."""
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    async def scoped_count(model) -> int:
        return (
            await db.execute(
                select(func.count()).select_from(model).where(model.user_id == user_id)
            )
        ).scalar() or 0

    activity_count = await scoped_count(Activity)
    goal_count = await scoped_count(Goal)
    reminder_count = await scoped_count(Reminder)
    challenge_count = await scoped_count(Challenge)

    now = datetime.utcnow()
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    activities_7d = (
        await db.execute(
            select(func.count())
            .select_from(Activity)
            .where(Activity.user_id == user_id, Activity.timestamp >= cutoff_7d)
        )
    ).scalar() or 0

    activities_30d = (
        await db.execute(
            select(func.count())
            .select_from(Activity)
            .where(Activity.user_id == user_id, Activity.timestamp >= cutoff_30d)
        )
    ).scalar() or 0

    last_activity = (
        await db.execute(
            select(func.max(Activity.timestamp)).where(Activity.user_id == user_id)
        )
    ).scalar()
    last_activity_at = last_activity.isoformat() if last_activity is not None else None

    return AdminUserDetail(
        id=user.id,
        email=user.email,
        telegram_linked=user.telegram_chat_id is not None,
        created_at=user.created_at.isoformat() if user.created_at else "",
        activity_count=activity_count,
        goal_count=goal_count,
        reminder_count=reminder_count,
        challenge_count=challenge_count,
        activities_7d=activities_7d,
        activities_30d=activities_30d,
        last_activity_at=last_activity_at,
    )
