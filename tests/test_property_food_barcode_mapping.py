"""Property tests for the food-barcode nutriment mapping (food-barcode).

These target the PURE function ``map_off_product`` in
``app.services.food_lookup_service`` (and its helper ``_num``). No DB or I/O
is involved, so they follow the same style as the other ``test_property_*``
modules in this repo.
"""
from hypothesis import given, settings, strategies as st

from app.services.food_lookup_service import map_off_product, _num


# The five per-100 g nutriment fields mapped from Open Food Facts to the
# Food_Candidate, as declared in the design mapping table.
_NUTRIMENT_FIELDS = {
    "energy-kcal_100g": "kcal",
    "proteins_100g": "protein",
    "fat_100g": "fat",
    "carbohydrates_100g": "carbs",
    "fiber_100g": "fiber",
}

# A barcode fallback: 8..14 digit string.
_fallback_barcode = st.text(alphabet="0123456789", min_size=8, max_size=14)

# Values a nutriment slot may take in an OFF response:
#   - a usable number (int or float) -> should map to float
#   - None / absent -> should map to None
#   - a non-numeric value (str) or bool -> should map to None (per ``_num``)
_present_number = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
)
_non_numeric = st.one_of(
    st.text(max_size=10),
    st.booleans(),
)
# A sentinel meaning "this key is absent from the nutriments dict".
_ABSENT = object()
_slot_value = st.one_of(
    _present_number,
    st.none(),
    _non_numeric,
    st.just(_ABSENT),
)


@st.composite
def _nutriments(draw):
    """Build a nutriments dict where each of the five fields is independently
    present (number), absent, None, or non-numeric."""
    out = {}
    for off_key in _NUTRIMENT_FIELDS:
        value = draw(_slot_value)
        if value is not _ABSENT:
            out[off_key] = value
    return out


def _expected(off_value):
    """Reference: a usable int/float (not bool) maps to float; everything else
    (absent, None, str, bool) maps to None."""
    if off_value is _ABSENT or off_value is None:
        return None
    if isinstance(off_value, bool):
        return None
    if isinstance(off_value, (int, float)):
        return float(off_value)
    return None


@settings(max_examples=100)
@given(nutriments=_nutriments(), barcode=_fallback_barcode)
def test_mapping_preserves_present_nutriments_and_nullifies_absent(nutriments, barcode):
    """# Feature: food-barcode, Property 1: El mapeo preserva los nutrientes
    presentes y nulifica los ausentes.

    Validates: Requirements 2.3, 2.5, 4.1, 4.2
    """
    product = {"product_name": "Test", "code": barcode, "nutriments": nutriments}

    candidate = map_off_product(product, barcode)

    for off_key, cand_key in _NUTRIMENT_FIELDS.items():
        off_value = nutriments.get(off_key, _ABSENT)
        expected = _expected(off_value)
        actual = candidate[cand_key]
        if expected is None:
            assert actual is None, (
                f"{cand_key}: expected None for OFF value {off_value!r}, got {actual!r}"
            )
        else:
            assert isinstance(actual, float), (
                f"{cand_key}: expected float for OFF value {off_value!r}, got {actual!r}"
            )
            assert actual == expected


@settings(max_examples=100)
@given(value=_slot_value)
def test_num_helper_matches_reference(value):
    """# Feature: food-barcode, Property 1 (helper): _num coacciona int/float
    (no bool) a float y devuelve None en cualquier otro caso.

    Validates: Requirements 2.5, 4.2
    """
    arg = None if value is _ABSENT else value
    assert _num(arg) == _expected(value if value is not _ABSENT else None)
