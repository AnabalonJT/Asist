"""Activity API routes."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.middleware import get_current_user
from app.models.user import User
from app.models.activity import Activity

router = APIRouter()


class ActivityOut(BaseModel):
    id: int
    activity_type: str
    duration_minutes: int | None
    distance_km: float | None
    calories: int
    timestamp: str

    @classmethod
    def from_model(cls, a: Activity) -> "ActivityOut":
        return cls(
            id=a.id,
            activity_type=a.activity_type,
            duration_minutes=a.duration_minutes,
            distance_km=a.distance_km,
            calories=a.calories,
            timestamp=a.timestamp.isoformat() if a.timestamp else "",
        )


class StreakResponse(BaseModel):
    current_streak: int


@router.get("", response_model=list[ActivityOut])
async def list_activities(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get activities for the current user, optionally filtered by date range."""
    query = select(Activity).where(Activity.user_id == current_user.id)

    if start_date:
        try:
            start = datetime.fromisoformat(start_date)
            query = query.where(Activity.timestamp >= start)
        except ValueError:
            pass

    if end_date:
        try:
            end = datetime.fromisoformat(end_date)
            query = query.where(Activity.timestamp <= end)
        except ValueError:
            pass

    query = query.order_by(Activity.timestamp.desc()).limit(limit)
    result = await db.execute(query)
    activities = result.scalars().all()
    return [ActivityOut.from_model(a) for a in activities]


@router.get("/streak", response_model=StreakResponse)
async def get_streak(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Calculate current activity streak (consecutive days with at least 1 activity)."""
    # Get all activity dates for user, ordered desc
    result = await db.execute(
        select(func.date(Activity.timestamp))
        .where(Activity.user_id == current_user.id)
        .distinct()
        .order_by(func.date(Activity.timestamp).desc())
    )
    dates = [row[0] for row in result.all()]

    if not dates:
        return StreakResponse(current_streak=0)

    today = datetime.utcnow().date()
    streak = 0
    expected = today

    for d in dates:
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif d == expected - timedelta(days=1):
            # Allow starting from yesterday if no activity today yet
            if streak == 0:
                streak = 1
                expected = d - timedelta(days=1)
            else:
                break
        else:
            break

    return StreakResponse(current_streak=streak)
