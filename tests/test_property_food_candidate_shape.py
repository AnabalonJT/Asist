"""Property test for Food_Barcode Property 3 (food-barcode spec).

Targets the PURE function ``map_off_product`` in
``app.services.food_lookup_service``. No DB or I/O is involved, so it follows
the same style as the other ``test_property_*`` modules in this repo.

Property 3 (design.md): for ANY Open Food Facts product response -- including a
missing/empty/partial ``nutriments`` and missing auxiliary fields, as well as
non-dict / garbage inputs -- ``map_off_product`` returns WITHOUT raising a dict
that contains all the Food_Candidate keys (name, barcode, kcal, protein, fat,
carbs, fiber, brand, image_url, source) with ``source == "off"``.
"""
from hypothesis import given, settings, strategies as st

from app.services.food_lookup_service import map_off_product


# The complete Food_Candidate shape (design.md "Data Models").
EXPECTED_KEYS = {
    "name", "barcode", "kcal", "protein", "fat", "carbs", "fiber",
    "brand", "image_url", "source",
}
_NUMERIC_KEYS = ("kcal", "protein", "fat", "carbs", "fiber")


# Arbitrary leaf values: numbers, bools, strings, None -- the kinds of garbage an
# external JSON source can hand us for any field.
_leaves = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=20),
)

# Arbitrary JSON-ish values (recursive: lists and dicts of leaves).
_json = st.recursive(
    _leaves,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=8), children, max_size=4),
    ),
    max_leaves=10,
)

# Known nutriment keys the mapper reads, mixed with garbage keys, each holding an
# arbitrary value (number / None / string / etc.).
_nutriment_keys = st.sampled_from([
    "energy-kcal_100g", "proteins_100g", "fat_100g",
    "carbohydrates_100g", "fiber_100g",
    "sugars_100g", "salt_100g", "random_key",
])
_nutriments = st.one_of(
    st.none(),
    _leaves,  # non-dict nutriments (None, number, string...) must be tolerated
    st.dictionaries(_nutriment_keys, _leaves, max_size=8),
)

# A product dict that may or may not carry the fields the mapper reads, each with
# arbitrary (possibly wrong-typed) values, plus arbitrary extra garbage keys.
@st.composite
def _product_dict(draw):
    product = {}
    for key in ("product_name", "code", "brands", "image_front_small_url"):
        if draw(st.booleans()):
            product[key] = draw(_leaves)
    if draw(st.booleans()):
        product["nutriments"] = draw(_nutriments)
    # Sprinkle arbitrary extra keys.
    product.update(draw(st.dictionaries(st.text(max_size=8), _json, max_size=4)))
    return product


# ANY input: a well-formed-ish product dict, OR raw garbage (non-dict / None /
# list / primitive) to prove robustness against entirely unexpected shapes.
_any_input = st.one_of(_product_dict(), _json)

# fallback_barcode may itself be arbitrary (the caller could pass anything).
_fallback = st.one_of(st.text(max_size=20), st.none(), st.integers(), st.booleans())


@settings(max_examples=100)
@given(product=_any_input, fallback=_fallback)
def test_map_off_product_never_raises_and_shape_is_complete(product, fallback):
    """Feature: food-barcode, Property 3: El mapeo nunca falla y produce la forma
    completa del candidato.
    Validates: Requirements 2.5, 4.4"""
    # Never raises for ANY input.
    result = map_off_product(product, fallback)

    # Always a dict with EXACTLY the Food_Candidate keys.
    assert isinstance(result, dict)
    assert set(result.keys()) == EXPECTED_KEYS

    # source is always "off".
    assert result["source"] == "off"

    # Numeric fields are float-or-None (never raw ints, strings, bools, etc.).
    for key in _NUMERIC_KEYS:
        value = result[key]
        assert value is None or (
            isinstance(value, float) and not isinstance(value, bool)
        ), f"{key} must be float or None, got {value!r}"
