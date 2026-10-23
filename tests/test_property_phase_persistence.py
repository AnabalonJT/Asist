"""Property tests for the DietPhasePlan phases persistence round-trip (goal-wizard).

These target the serialization helpers ``phases_list`` and ``active_phase`` on
``app.models.diet_phase_plan.DietPhasePlan``. The round-trip is a pure JSON
serialize/deserialize over the ``phases`` Text column, so no DB or I/O is
involved; the model is instantiated directly and its ``phases`` attribute set to
the serialized string (same lightweight style as the other ``test_property_*``
modules in this repo).
"""
import json

from hypothesis import given, settings, strategies as st

from app.models.diet_phase_plan import DietPhasePlan


# A finite, JSON-safe float (no NaN/inf, which JSON cannot represent round-trip).
_finite = st.floats(min_value=-1e6, max_value=1e6,
                    allow_nan=False, allow_infinity=False)

_status = st.sampled_from(["active", "completed", "pending"])


@st.composite
def _phase(draw, index):
    """A single Diet_Phase dict matching the shape documented on the model."""
    return {
        "index": index,
        "start_weight": draw(_finite),
        "end_weight": draw(_finite),
        "kcal": draw(_finite),
        "protein_g": draw(_finite),
        "fat_g": draw(_finite),
        "carbs_g": draw(_finite),
        "status": draw(_status),
        "weeks": draw(_finite),
        "start_date": draw(st.one_of(st.none(), st.text(max_size=20))),
        "end_date": draw(st.one_of(st.none(), st.text(max_size=20))),
        "maintenance": draw(st.booleans()),
    }


@st.composite
def _phases(draw):
    """An ordered list of Diet_Phase dicts (0..n), indices assigned by position."""
    n = draw(st.integers(min_value=0, max_value=8))
    return [draw(_phase(index=i)) for i in range(n)]


@settings(max_examples=100)
@given(phases=_phases())
def test_phases_persistence_round_trip(phases):
    """Feature: goal-wizard, Property 11: Round-trip de persistencia del plan de fases.

    Serializing a list of phase dicts into the ``phases`` JSON Text column and
    reading them back via ``phases_list`` yields an equivalent list of phases
    (same indices, weights, targets and statuses, in the same order). And
    ``active_phase`` returns the first phase whose status is "active".

    Validates: Requirements 7.6, 11.4
    """
    plan = DietPhasePlan()
    plan.phases = json.dumps(phases)

    read_back = plan.phases_list()

    # The round-trip is lossless: same length, same ordering, same values.
    assert read_back == phases

    # active_phase returns the first phase with status "active", or None.
    expected_active = next((p for p in phases if p.get("status") == "active"), None)
    assert plan.active_phase() == expected_active
