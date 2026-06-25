"""Calorie estimation service using MET-based formulas."""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calorie_formula import CalorieFormula

logger = logging.getLogger(__name__)

# Default formulas (used when DB has no data)
DEFAULT_FORMULAS: dict[str, dict] = {
    "running": {"met": 9.8, "distance_factor": 60.0},
    "walking": {"met": 3.5, "distance_factor": 40.0},
    "cycling": {"met": 7.5, "distance_factor": 35.0},
    "gym": {"met": 5.0, "distance_factor": None},
    "swimming": {"met": 8.0, "distance_factor": None},
    "yoga": {"met": 3.0, "distance_factor": None},
    "hiking": {"met": 6.0, "distance_factor": 50.0},
    "basketball": {"met": 6.5, "distance_factor": None},
    "football": {"met": 7.0, "distance_factor": None},
    "tennis": {"met": 7.0, "distance_factor": None},
    "dance": {"met": 4.5, "distance_factor": None},
    "weights": {"met": 6.0, "distance_factor": None},
    "crossfit": {"met": 8.0, "distance_factor": None},
    "stretching": {"met": 2.5, "distance_factor": None},
    "meditation": {"met": 1.5, "distance_factor": None},
    "reading": {"met": 1.3, "distance_factor": None},
    "study": {"met": 1.5, "distance_factor": None},
}

DEFAULT_MET = 5.0
DEFAULT_WEIGHT_KG = 70.0


class CalorieService:

    def estimate(
        self,
        activity_type: str,
        duration_minutes: int | None = None,
        distance_km: float | None = None,
    ) -> int:
        """
        Estimate calories burned for an activity.
        
        Priority:
        1. If distance provided and activity has distance_factor → use distance formula
        2. Otherwise use MET × weight × duration formula
        3. If no duration → return 0
        """
        activity_key = activity_type.lower().strip()
        formula = DEFAULT_FORMULAS.get(activity_key, {})
        met = formula.get("met", DEFAULT_MET)
        distance_factor = formula.get("distance_factor")

        # Distance-based calculation takes priority
        if distance_km and distance_factor:
            return int(distance_km * distance_factor)

        # MET-based calculation
        if duration_minutes and duration_minutes > 0:
            duration_hours = duration_minutes / 60.0
            return int(met * DEFAULT_WEIGHT_KG * duration_hours)

        # If we have distance but no distance_factor, estimate duration from distance
        if distance_km and duration_minutes is None:
            # Rough: assume 6 min/km for running, 12 min/km for walking
            est_duration = distance_km * 6.0  # minutes
            duration_hours = est_duration / 60.0
            return int(met * DEFAULT_WEIGHT_KG * duration_hours)

        return 0


calorie_service = CalorieService()
