"""Canonical activity_type normalization shared across goal-progress matching.

Goals and activities may be labeled with different words for the same activity
(e.g. "caminar", "caminata", "walk", "Walking"). Normalizing both sides to a
canonical vocabulary makes goal progress matching robust so a goal like
"caminar todos los días" is correctly marked complete when a walk is logged.

Used by the Telegram bot (webhook + polling), the goals/challenges routes, and
the reminder/summary scheduler so matching is identical everywhere.
"""
from __future__ import annotations

# Canonical activity_type vocabulary (synonym -> canonical form).
_ACTIVITY_SYNONYMS: dict[str, str] = {
    # walking
    "walking": "walking", "walk": "walking", "caminar": "walking",
    "caminata": "walking", "caminando": "walking", "camine": "walking",
    "caminé": "walking", "caminar/trotar": "walking", "trotar": "walking",
    # running
    "running": "running", "run": "running", "correr": "running",
    "corri": "running", "corrí": "running", "trote": "running", "carrera": "running",
    # cycling
    "cycling": "cycling", "bici": "cycling", "bicicleta": "cycling",
    "ciclismo": "cycling", "pedalear": "cycling",
    # swimming
    "swimming": "swimming", "nadar": "swimming", "natacion": "swimming",
    "natación": "swimming", "nade": "swimming", "nadé": "swimming",
    # gym / strength
    "gym": "gym", "gimnasio": "gym", "deporte": "gym", "ejercicio": "gym",
    "pesas": "weights", "weights": "weights", "fuerza": "weights",
    "crossfit": "crossfit",
    # habits
    "yoga": "yoga",
    "meditar": "meditation", "meditacion": "meditation", "meditación": "meditation",
    "meditation": "meditation",
    "leer": "reading", "lectura": "reading", "reading": "reading",
    "estudiar": "study", "estudio": "study", "study": "study",
    "stretching": "stretching", "estiramiento": "stretching",
    # other common
    "hiking": "hiking", "senderismo": "hiking",
}


def normalize_activity_type(activity_type: str | None) -> str:
    """Map an activity_type to its canonical form so goals and activities match.

    Case-insensitive; trims whitespace. Unknown types are returned lowercased and
    stripped (so at least casing/whitespace never breaks a match). This keeps goal
    progress detection consistent regardless of whether the value came from the LLM,
    the keyword detectors, or free text.
    """
    if not activity_type:
        return ""
    key = activity_type.strip().lower()
    return _ACTIVITY_SYNONYMS.get(key, key)
