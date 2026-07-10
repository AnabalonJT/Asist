"""Challenges API routes."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.middleware import get_current_user
from app.models.user import User
from app.models.goal import Goal
from app.models.challenge import Challenge
from app.models.activity import Activity

router = APIRouter()


class GoalProgress(BaseModel):
    id: int
    activity_type: str
    description: str
    target_count: int
    period: str
    current_progress: int
    completed: bool


class ChallengeOut(BaseModel):
    id: int
    name: str
    ends_at: str | None
    active: bool
    all_completed: bool  # True only if ALL goals are met for current period
    goals: list[GoalProgress]


@router.get("", response_model=list[ChallengeOut])
async def list_challenges(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Challenge).where(Challenge.user_id == current_user.id, Challenge.active == True)
    )
    challenges = result.scalars().all()

    out = []
    for ch in challenges:
        # Get goals for this challenge
        goals_result = await db.execute(
            select(Goal).where(Goal.challenge_id == ch.id, Goal.active == True)
        )
        goals = goals_result.scalars().all()

        goal_progresses = []
        all_met = True

        for g in goals:
            progress = await _calc_progress(g, current_user.id, db)
            completed = progress >= g.target_count
            if not completed:
                all_met = False

            goal_progresses.append(GoalProgress(
                id=g.id,
                activity_type=g.activity_type,
                description=g.description,
                target_count=g.target_count,
                period=g.period,
                current_progress=progress,
                completed=completed,
            ))

        out.append(ChallengeOut(
            id=ch.id,
            name=ch.name,
            ends_at=ch.ends_at,
            active=ch.active,
            all_completed=all_met and len(goal_progresses) > 0,
            goals=goal_progresses,
        ))

    return out


@router.delete("/{challenge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_challenge(
    challenge_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Challenge).where(Challenge.id == challenge_id, Challenge.user_id == current_user.id)
    )
    challenge = result.scalar_one_or_none()
    if not challenge:
        raise HTTPException(status_code=404)
    
    challenge.active = False
    # Also deactivate all goals in this challenge
    goals_result = await db.execute(select(Goal).where(Goal.challenge_id == challenge.id))
    for g in goals_result.scalars().all():
        g.active = False


async def _calc_progress(goal: Goal, user_id: int, db: AsyncSession) -> int:
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
            Activity.user_id == user_id,
            Activity.activity_type == goal.activity_type,
            Activity.timestamp >= start,
        )
    )
    return result.scalar() or 0
