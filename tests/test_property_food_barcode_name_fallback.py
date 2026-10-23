"""Property tests for the name fallback of ``map_off_product`` (food-barcode).

Targets the PURE function ``map_off_product`` in
``app.services.food_lookup_service``. No DB or I/O is involved, so this follows
the same style as the other ``test_property_*`` modules in this repo.
"""
from hypothesis import given, strategies as st, settings

from app.services.food_lookup_service import map_off_product


# A usable product_name: a non-empty string that stays non-empty after strip.
# min_size keeps at least one non-whitespace char so ``.strip()`` is truthy.
_usable_name = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc", "Zs", "Zl", "Zp")),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip() != "")

# product_name values that are NOT usable -> must fall back to the barcode:
#   whitespace-only, empty string, None, and non-string types.
_whitespace = st.text(alphabet=" \t\n\r", min_size=0, max_size=10)
_non_string = st.one_of(
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.lists(st.integers(), max_size=3),
    st.dictionaries(st.text(max_size=3), st.integers(), max_size=3),
)
# Barcode strings used as fallback (kept simple; not validated by the mapper).
_barcode = st.text(
    alphabet="0123456789", min_size=8, max_size=14
)


@st.composite
def _product_with_name(draw):
    """A product dict whose product_name is usable or unusable (or missing)."""
    choice = draw(
        st.sampled_from(["usable", "whitespace", "empty", "none", "nonstr", "missing"])
    )
    product = {"code": draw(st.one_of(st.none(), _barcode))}
    if choice == "usable":
        product["product_name"] = draw(_usable_name)
    elif choice == "whitespace":
        product["product_name"] = draw(_whitespace.filter(lambda s: s != "")) or " "
    elif choice == "empty":
        product["product_name"] = ""
    elif choice == "none":
        product["product_name"] = None
    elif choice == "nonstr":
        product["product_name"] = draw(_non_string)
    # "missing" -> leave the key out entirely
    return product


def _expected_name(product, fallback_barcode):
    """Model-based reference for Property 2's name rule."""
    raw = product.get("product_name")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return fallback_barcode


# Feature: food-barcode, Property 2: El nombre siempre está definido (fallback
# al código de barras). Para toda respuesta de producto y todo barcode
# consultado, map_off_product produce un name = product_name cuando es una
# cadena no vacía (tras strip), y el fallback_barcode en caso contrario.
# Validates: Requirements 4.3, 2.5
@settings(max_examples=100)
@given(product=_product_with_name(), fallback=_barcode)
def test_name_falls_back_to_barcode_when_product_name_unusable(product, fallback):
    candidate = map_off_product(product, fallback)

    expected = _expected_name(product, fallback)
    assert candidate["name"] == expected

    # When product_name is a non-empty string after strip, name is that trimmed
    # value; otherwise name is exactly the fallback barcode.
    raw = product.get("product_name")
    if isinstance(raw, str) and raw.strip():
        assert candidate["name"] == raw.strip()
    else:
        assert candidate["name"] == fallback
