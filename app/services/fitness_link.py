"""Fitness link adapter: isolates the optional dependency on fitness-coach.

The Meal_Planner consumes ``FitnessProfile.meal_planner_view()`` and the pure
``fitness_service.compute_target_rate`` to derive nutrition targets. Because the
fitness-coach model/table may not be deployed/populated when the meal-planner runs,
this module imports those symbols lazily and degrades cleanly to ``None`` instead of
raising (Req 4.6, 5.5, 8.5). It never propagates exceptions to the caller.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_fitness_view(db: AsyncSession, user_id: int) -> Optional[dict]:
    """Return ``FitnessProfile.meal_planner_view()`` for the user, or ``None``.

    Returns ``None`` when the fitness-coach model/table does not exist yet
    (ImportError / SQL error) or when the user has no fitness profile. Lazy import
    so the meal-planner does not fail at import time if fitness-coach is absent.
    """
    try:
        from app.models.fitness_profile import FitnessProfile
    except ImportError:
        return None

    try:
        result = await db.execute(
            select(FitnessProfile).where(FitnessProfile.user_id == user_id)
        )
        row = result.scalar_one_or_none()
    except Exception:
        # Table missing / SQL error → treat as absent.
        return None

    if row is None:
        return None

    try:
        return row.meal_planner_view()
    except Exception:
        return None


def compute_target_rate_for_view(view: dict) -> Optional[dict]:
    """Compute ``{'daily_kcal_delta', 'direction'}`` from a fitness view.

    Applies only to weight-target goals: the view must carry ``target_weight_kg``
    and ``target_date`` (and a current weight). Uses the pure
    ``fitness_service.compute_target_rate`` and ``_parse_iso_date``. Returns ``None``
    when it does not apply, the dependency is unavailable, or any computation fails.
    Never raises.
    """
    if not isinstance(view, dict):
        return None

    goal_type = view.get("goal_type")
    target_weight = view.get("target_weight_kg")
    target_date = view.get("target_date")
    current_weight = view.get("current_weight_kg")

    if goal_type != "weight_target":
        return None
    if target_weight is None or target_date is None or current_weight is None:
        return None

    try:
        from app.services.fitness_service import (
            compute_target_rate,
            _parse_iso_date,
        )
    except ImportError:
        return None

    try:
        from datetime import date

        parsed = _parse_iso_date(target_date)
        days = (parsed - date.today()).days
        weeks = days / 7.0
        rate = compute_target_rate(current_weight, target_weight, weeks)
        return {
            "daily_kcal_delta": rate["daily_kcal_delta"],
            "direction": rate["direction"],
        }
    except Exception:
        return None
