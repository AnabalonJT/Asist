"""Goals API routes."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.middleware import get_current_user
from app.models.user import User
from app.models.goal import Goal
from app.models.activity import Activity

router = APIRouter()


class GoalOut(BaseModel):
    id: int
    activity_type: str
    description: str
    target_count: int
    period: str
    active: bool
    current_progress: int
    ends_at: str | None = None

    @classmethod
    async def from_model(cls, g: Goal, db: AsyncSession) -> "GoalOut":
        progress = await _calc_progress(g, db)
        return cls(
            id=g.id,
            activity_type=g.activity_type,
            description=g.description,
            target_count=g.target_count,
            period=g.period,
            active=g.active,
            current_progress=progress,
            ends_at=g.ends_at,
        )


class GoalCreate(BaseModel):
    activity_type: str
    description: str
    target_count: int = 1
    period: str = "weekly"


@router.get("", response_model=list[GoalOut])
async def list_goals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Goal).where(Goal.user_id == current_user.id, Goal.active == True, Goal.challenge_id == None)
    )
    goals = result.scalars().all()
    return [await GoalOut.from_model(g, db) for g in goals]


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
async def create_goal(
    body: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = Goal(
        user_id=current_user.id,
        activity_type=body.activity_type,
        description=body.description,
        target_count=body.target_count,
        period=body.period,
        active=True,
    )
    db.add(goal)
    await db.flush()
    return await GoalOut.from_model(goal, db)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == current_user.id)
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404)
    goal.active = False


async def _calc_progress(goal: Goal, db: AsyncSession) -> int:
    """Count matching activities in the current period."""
    now = datetime.utcnow()

    if goal.period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif goal.period == "weekly":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(func.count())
        .select_from(Activity)
        .where(
            Activity.user_id == goal.user_id,
            Activity.activity_type == goal.activity_type,
            Activity.timestamp >= start,
        )
    )
    return result.scalar() or 0
