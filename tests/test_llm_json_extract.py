"""Tests for the tolerant JSON extractor used in workout plan generation.

Regression coverage for the 502 where the free LLM returned JSON wrapped in prose
and with trailing commas, which json.loads rejected.
"""
from app.services.llm_service import _extract_json


def test_clean_json_object():
    r = _extract_json('{"days": [{"day": "D1", "exercises": []}]}')
    assert r is not None
    assert r["days"][0]["day"] == "D1"


def test_json_wrapped_in_code_fence():
    s = '```json\n{"days": [{"day": "D1", "exercises": []}]}\n```'
    assert _extract_json(s) is not None


def test_json_with_prose_around_it():
    s = 'Aquí tienes tu rutina:\n{"days": []}\n¡Espero que te sirva!'
    r = _extract_json(s)
    assert r is not None and r["days"] == []


def test_trailing_commas_are_repaired():
    s = '{"days": [{"day": "D1", "exercises": [{"name": "Dominadas"},],},]}'
    r = _extract_json(s)
    assert r is not None
    assert len(r["days"]) == 1
    assert r["days"][0]["exercises"][0]["name"] == "Dominadas"


def test_prose_plus_trailing_commas():
    # The exact real-world failure mode: prose + code fence + trailing commas.
    s = ('Rutina:\n```json\n{"days": [{"day": "D1", "exercises": '
         '[{"name": "Fondos", "duration_seconds": 60, "rest_seconds": 60, '
         '"equipment": "barras paralelas"},],},]}\n```')
    r = _extract_json(s)
    assert r is not None and len(r["days"]) == 1


def test_unrecoverable_returns_none():
    assert _extract_json("no hay json aquí") is None
    assert _extract_json("") is None


def test_empty_object():
    assert _extract_json("{}") == {}


def test_truncated_object_is_recovered():
    # JSON cut off mid-exercise (real free-model failure): the last complete
    # exercise is kept and the structure is closed.
    from app.services.llm_service import _extract_json
    s = ('{"days":[{"day":"Dia 1","exercises":['
         '{"name":"Press banca","sets":4,"reps":10,"duration_seconds":null,'
         '"rest_seconds":90,"equipment":"banco"},'
         '{"name":"Fondos en paral')
    r = _extract_json(s)
    assert r is not None
    assert len(r["days"]) == 1
    assert len(r["days"][0]["exercises"]) == 1
    assert r["days"][0]["exercises"][0]["name"] == "Press banca"


def test_truncated_multiple_days():
    from app.services.llm_service import _extract_json
    s = ('{"days":[{"day":"D1","exercises":[{"name":"Sentadilla","sets":5,"reps":5,'
         '"duration_seconds":null,"rest_seconds":120,"equipment":"rack"}]},'
         '{"day":"D2","exercises":[{"name":"Dominadas","sets":4,"reps":8,')
    r = _extract_json(s)
    assert r is not None
    # First day fully recovered; second day dropped (its exercise was incomplete).
    assert len(r["days"]) >= 1
    assert r["days"][0]["exercises"][0]["name"] == "Sentadilla"
