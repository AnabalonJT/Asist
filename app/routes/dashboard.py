"""Dashboard API: user stats, recent activities, detailed metrics."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
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
    def from_orm(cls, a: Activity) -> "ActivityOut":
        return cls(
            id=a.id,
            activity_type=a.activity_type,
            duration_minutes=a.duration_minutes,
            distance_km=a.distance_km,
            calories=a.calories,
            timestamp=a.timestamp.isoformat() if a.timestamp else "",
        )


class ActivityBreakdown(BaseModel):
    activity_type: str
    count: int
    total_minutes: int
    total_calories: int


class WeekComparison(BaseModel):
    this_week: int
    last_week: int
    change_pct: float


class DashboardStats(BaseModel):
    total_activities: int
    total_calories: int
    total_minutes: int
    total_distance_km: float
    current_streak: int
    telegram_linked: bool
    timezone: str
    recent_activities: list[ActivityOut]
    breakdown: list[ActivityBreakdown]
    week_comparison: WeekComparison


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user.id

    # Total activities
    count_result = await db.execute(
        select(func.count()).select_from(Activity).where(Activity.user_id == user_id)
    )
    total_activities = count_result.scalar() or 0

    # Total calories
    cal_result = await db.execute(
        select(func.coalesce(func.sum(Activity.calories), 0)).where(Activity.user_id == user_id)
    )
    total_calories = cal_result.scalar() or 0

    # Total minutes
    min_result = await db.execute(
        select(func.coalesce(func.sum(Activity.duration_minutes), 0)).where(Activity.user_id == user_id)
    )
    total_minutes = min_result.scalar() or 0

    # Total distance
    dist_result = await db.execute(
        select(func.coalesce(func.sum(Activity.distance_km), 0.0)).where(Activity.user_id == user_id)
    )
    total_distance_km = float(dist_result.scalar() or 0.0)

    # Streak calculation
    streak_result = await db.execute(
        select(func.date(Activity.timestamp))
        .where(Activity.user_id == user_id)
        .distinct()
        .order_by(func.date(Activity.timestamp).desc())
    )
    dates = [row[0] for row in streak_result.all()]
    current_streak = _calc_streak(dates)

    # Recent activities (last 10)
    recent_result = await db.execute(
        select(Activity).where(Activity.user_id == user_id)
        .order_by(Activity.timestamp.desc()).limit(10)
    )
    recent = [ActivityOut.from_orm(a) for a in recent_result.scalars().all()]

    # Breakdown by activity type
    breakdown_result = await db.execute(
        select(
            Activity.activity_type,
            func.count().label("count"),
            func.coalesce(func.sum(Activity.duration_minutes), 0).label("total_min"),
            func.coalesce(func.sum(Activity.calories), 0).label("total_cal"),
        )
        .where(Activity.user_id == user_id)
        .group_by(Activity.activity_type)
        .order_by(func.count().desc())
    )
    breakdown = [
        ActivityBreakdown(
            activity_type=row.activity_type,
            count=row.count,
            total_minutes=row.total_min,
            total_calories=row.total_cal,
        )
        for row in breakdown_result.all()
    ]

    # Week-over-week comparison
    now = datetime.utcnow()
    this_week_start = now - timedelta(days=7)
    last_week_start = now - timedelta(days=14)

    tw_result = await db.execute(
        select(func.count()).select_from(Activity).where(
            Activity.user_id == user_id,
            Activity.timestamp >= this_week_start,
        )
    )
    this_week = tw_result.scalar() or 0

    lw_result = await db.execute(
        select(func.count()).select_from(Activity).where(
            Activity.user_id == user_id,
            Activity.timestamp >= last_week_start,
            Activity.timestamp < this_week_start,
        )
    )
    last_week = lw_result.scalar() or 0

    change_pct = 0.0
    if last_week > 0:
        change_pct = round(((this_week - last_week) / last_week) * 100, 1)

    return DashboardStats(
        total_activities=total_activities,
        total_calories=total_calories,
        total_minutes=total_minutes,
        total_distance_km=round(total_distance_km, 1),
        current_streak=current_streak,
        telegram_linked=current_user.telegram_chat_id is not None,
        timezone=current_user.timezone,
        recent_activities=recent,
        breakdown=breakdown,
        week_comparison=WeekComparison(
            this_week=this_week,
            last_week=last_week,
            change_pct=change_pct,
        ),
    )


def _calc_streak(dates: list) -> int:
    """Calculate streak from sorted dates (desc)."""
    if not dates:
        return 0

    today = datetime.utcnow().date()
    streak = 0
    expected = today

    for d in dates:
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif streak == 0 and d == today - timedelta(days=1):
            streak = 1
            expected = d - timedelta(days=1)
        else:
            break

    return streak
