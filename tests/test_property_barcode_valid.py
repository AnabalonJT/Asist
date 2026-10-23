"""Property tests for the barcode validity predicate (food-barcode).

These target the PURE helpers ``normalize_barcode`` and ``is_valid_barcode`` in
``app.services.food_lookup_service``. No DB or I/O is involved, so they follow
the same style as the other ``test_property_*`` modules in this repo.
"""
from hypothesis import given, settings, strategies as st

from app.services.food_lookup_service import (
    BARCODE_LEN,
    is_valid_barcode,
    normalize_barcode,
)

_LO, _HI = BARCODE_LEN  # (8, 14) inclusive

# Arbitrary text: printable incl. digits, letters, whitespace and punctuation.
_arbitrary_text = st.text(
    alphabet=st.characters(min_codepoint=9, max_codepoint=0x2FFF),
    min_size=0,
    max_size=40,
)
# Digit-only strings across all lengths (too short, in range, too long).
_digit_strings = st.text(alphabet="0123456789", min_size=0, max_size=25)
# Surrounding whitespace to wrap a code with.
_ws = st.text(alphabet=" \t\n\r\f\v", min_size=0, max_size=5)
# Non-string inputs that normalize_barcode coerces to "".
_non_string = st.one_of(
    st.none(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.lists(st.integers(), max_size=3),
    st.binary(max_size=10),
)


@given(st.one_of(_arbitrary_text, _digit_strings, _non_string))
@settings(max_examples=100)
def test_barcode_validity_iff_eight_to_fourteen_digits(value):
    """# Feature: food-barcode, Property 4: La validación del código de barras
    acepta exactamente los códigos de 8 a 14 dígitos.

    For every input, ``is_valid_barcode`` on the normalized code SHALL be True
    iff the normalized string is all digits and its length is in [8, 14].

    **Validates: Requirements 1.2, 2.6**
    """
    normalized = normalize_barcode(value)
    expected = normalized.isdigit() and _LO <= len(normalized) <= _HI
    assert is_valid_barcode(value) is expected


@given(_digit_strings.filter(lambda s: _LO <= len(s) <= _HI), _ws, _ws)
@settings(max_examples=100)
def test_in_range_digits_with_surrounding_whitespace_are_valid(code, lead, trail):
    """# Feature: food-barcode, Property 4: La validación del código de barras
    acepta exactamente los códigos de 8 a 14 dígitos.

    An 8..14 digit string, with or without surrounding whitespace, is valid
    after normalization.

    **Validates: Requirements 1.2, 2.6**
    """
    assert is_valid_barcode(code) is True
    assert is_valid_barcode(lead + code + trail) is True


@given(_digit_strings.filter(lambda s: len(s) < _LO or len(s) > _HI))
@settings(max_examples=100)
def test_out_of_range_digit_strings_are_invalid(code):
    """# Feature: food-barcode, Property 4: La validación del código de barras
    acepta exactamente los códigos de 8 a 14 dígitos.

    Digit strings shorter than 8 or longer than 14 are invalid.

    **Validates: Requirements 1.2, 2.6**
    """
    assert is_valid_barcode(code) is False


@given(
    st.text(min_size=_LO, max_size=_HI).filter(lambda s: not s.strip().isdigit()),
)
@settings(max_examples=100)
def test_non_digit_content_is_invalid(code):
    """# Feature: food-barcode, Property 4: La validación del código de barras
    acepta exactamente los códigos de 8 a 14 dígitos.

    A string whose normalized form contains any non-digit character is invalid.

    **Validates: Requirements 1.2, 2.6**
    """
    assert is_valid_barcode(code) is False


@given(_non_string)
@settings(max_examples=100)
def test_non_string_input_is_invalid(value):
    """# Feature: food-barcode, Property 4: La validación del código de barras
    acepta exactamente los códigos de 8 a 14 dígitos.

    Non-string input normalizes to "" and is therefore never valid.

    **Validates: Requirements 1.2, 2.6**
    """
    assert normalize_barcode(value) == ""
    assert is_valid_barcode(value) is False
