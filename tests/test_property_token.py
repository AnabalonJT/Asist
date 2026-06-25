"""Property tests for linking token uniqueness."""
import pytest
from hypothesis import given, strategies as st, settings
import uuid


@given(n=st.integers(min_value=10, max_value=500))
@settings(max_examples=20)
def test_uuid4_tokens_are_unique(n):
    """Property: generating n tokens produces n unique values."""
    tokens = [uuid.uuid4().hex for _ in range(n)]
    assert len(set(tokens)) == n


@given(st.data())
@settings(max_examples=50)
def test_token_format_is_hex(data):
    """Property: tokens are 32-char hex strings."""
    token = uuid.uuid4().hex
    assert len(token) == 32
    assert all(c in "0123456789abcdef" for c in token)
