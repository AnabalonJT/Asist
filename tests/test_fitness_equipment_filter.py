"""Tests for equipment filtering in workout plan generation."""
import pytest
from app.services.fitness_service import filter_plan_equipment, EquipmentError


def _plan():
    return [
        {"day": "D1", "exercises": [
            {"name": "Press banca", "sets": 4, "reps": 10, "rest_seconds": 90, "equipment": "banco"},
            {"name": "Swing con kettlebell", "sets": 3, "reps": 15, "rest_seconds": 60, "equipment": "kettlebell"},
        ]},
        {"day": "D2", "exercises": [
            {"name": "Dominadas", "sets": 4, "reps": 8, "rest_seconds": 90, "equipment": "barra de dominadas"},
        ]},
    ]


def test_drops_unavailable_exercise_keeps_rest():
    out = filter_plan_equipment(_plan(), ["banco", "barra de dominadas", "peso corporal"])
    names = [e["name"] for d in out for e in d["exercises"]]
    assert "Swing con kettlebell" not in names
    assert "Press banca" in names and "Dominadas" in names


def test_removes_empty_days():
    # User only has a bench: D2 (dominadas) becomes empty and is removed.
    out = filter_plan_equipment(_plan(), ["banco"])
    assert len(out) == 1
    assert out[0]["day"] == "D1"


def test_full_gym_keeps_everything():
    out = filter_plan_equipment(_plan(), ["gimnasio completo"])
    total = sum(len(d["exercises"]) for d in out)
    assert total == 3


def test_bodyweight_always_allowed():
    plan = [{"day": "D1", "exercises": [
        {"name": "Flexiones", "sets": 3, "reps": 20, "rest_seconds": 60, "equipment": "peso corporal"},
    ]}]
    out = filter_plan_equipment(plan, [])
    assert len(out) == 1


def test_raises_when_nothing_survives():
    plan = [{"day": "D1", "exercises": [
        {"name": "Swing con kettlebell", "sets": 3, "reps": 15, "rest_seconds": 60, "equipment": "kettlebell"},
    ]}]
    with pytest.raises(EquipmentError):
        filter_plan_equipment(plan, ["banco"])
