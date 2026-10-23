"""Example-based tests for the Food_Lookup_Service I/O functions (food-barcode).

Targets the async functions ``lookup_barcode`` and ``search_by_name`` in
``app.services.food_lookup_service``. The real Open Food Facts network is NEVER
contacted: every test injects an ``httpx.MockTransport`` into the client the
service builds, via a monkeypatched ``httpx.AsyncClient`` that preserves the
timeout/headers the service passes (so the descriptive ``User-Agent`` can be
asserted, Req 4.5).

Async tests run under pytest-asyncio auto mode (see pytest.ini).

Requirements covered: 2.2, 2.3, 2.6, 2.7, 2.8, 3.2, 3.5, 4.5.
"""
import httpx
import pytest

from app.services import food_lookup_service as fls
from app.services.food_lookup_service import (
    ExternalSourceError,
    InvalidBarcodeError,
    NotFoundError,
    lookup_barcode,
    search_by_name,
)


# ── httpx mocking helper ──────────────────────────────────────────────────────
#
# The service builds its own ``httpx.AsyncClient(timeout=..., headers=...)``.
# We replace ``httpx.AsyncClient`` with a factory that forwards those kwargs to a
# real AsyncClient but forces a MockTransport, so the handler sees the request
# (including the User-Agent header the service set) and returns a canned response
# WITHOUT any socket being opened.


def _install_mock(monkeypatch, handler, *, captured=None):
    """Patch ``httpx.AsyncClient`` so the service routes through ``handler``.

    ``handler`` is a callable ``httpx.Request -> httpx.Response`` (or one that
    raises an ``httpx`` exception to simulate a transport failure). When
    ``captured`` (a list) is provided, each inbound request is appended to it so
    tests can assert on headers / URL / params.
    """
    real_async_client = httpx.AsyncClient

    def _factory(*args, **kwargs):
        def _wrapped(request):
            if captured is not None:
                captured.append(request)
            return handler(request)

        kwargs["transport"] = httpx.MockTransport(_wrapped)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(fls.httpx, "AsyncClient", _factory)


def _json_response(payload, status_code=200):
    def handler(_request):
        return httpx.Response(status_code, json=payload)

    return handler


# ── lookup_barcode: invalid format (no network) ──────────────────────────────


async def test_lookup_barcode_invalid_format_raises_invalid_barcode_error(monkeypatch):
    """Req 2.6: a code that is not an 8..14 digit string is rejected before any
    network call, with a Spanish message."""
    calls = []

    def handler(_request):  # must never run
        calls.append(_request)
        return httpx.Response(200, json={"status": 1})

    _install_mock(monkeypatch, handler)

    with pytest.raises(InvalidBarcodeError) as exc:
        await lookup_barcode("abc123")

    assert calls == []  # no request was issued
    assert "código de barras" in str(exc.value).lower()


# ── lookup_barcode: product found (status 1) ─────────────────────────────────


async def test_lookup_barcode_status_1_returns_mapped_candidate(monkeypatch):
    """Req 2.2, 2.3, 4.5: status:1 → a mapped Food_Candidate with name/kcal and
    source 'off'; the request carries the descriptive User-Agent header."""
    captured = []
    payload = {
        "status": 1,
        "code": "7501234567890",
        "product": {
            "code": "7501234567890",
            "product_name": "Galletas de avena",
            "brands": "MarcaX",
            "image_front_small_url": "https://img.example/x.jpg",
            "nutriments": {
                "energy-kcal_100g": 450.0,
                "proteins_100g": 8.0,
                "fat_100g": 15.0,
                "carbohydrates_100g": 65.0,
                "fiber_100g": 5.0,
            },
        },
    }
    _install_mock(monkeypatch, _json_response(payload), captured=captured)

    candidate = await lookup_barcode("7501234567890")

    assert candidate["name"] == "Galletas de avena"
    assert candidate["kcal"] == 450.0
    assert candidate["protein"] == 8.0
    assert candidate["fiber"] == 5.0
    assert candidate["brand"] == "MarcaX"
    assert candidate["source"] == "off"

    # Req 4.5: a descriptive User-Agent was sent, and the request hit the OFF
    # product endpoint for the normalized code.
    assert len(captured) == 1
    req = captured[0]
    assert req.headers.get("user-agent") == fls.USER_AGENT
    assert "7501234567890" in str(req.url)


# ── lookup_barcode: product not found (status 0) ─────────────────────────────


async def test_lookup_barcode_status_0_raises_not_found(monkeypatch):
    """Req 2.7: status:0 → NotFoundError with a Spanish message."""
    _install_mock(monkeypatch, _json_response({"status": 0}))

    with pytest.raises(NotFoundError) as exc:
        await lookup_barcode("0000000000000")

    assert "no encontramos" in str(exc.value).lower()


# ── lookup_barcode: non-200 HTTP status ──────────────────────────────────────


async def test_lookup_barcode_non_200_raises_external_source_error(monkeypatch):
    """Req 2.8: a non-200 HTTP response → ExternalSourceError (Spanish),
    never a raw error."""
    _install_mock(monkeypatch, _json_response({"status": 1}, status_code=500))

    with pytest.raises(ExternalSourceError):
        await lookup_barcode("7501234567890")


# ── lookup_barcode: timeout ──────────────────────────────────────────────────


async def test_lookup_barcode_timeout_raises_external_source_error(monkeypatch):
    """Req 2.8: a timeout from the external source → ExternalSourceError."""

    def handler(request):
        raise httpx.TimeoutException("timed out", request=request)

    _install_mock(monkeypatch, handler)

    with pytest.raises(ExternalSourceError):
        await lookup_barcode("7501234567890")


# ── lookup_barcode: generic HTTP/transport error ─────────────────────────────


async def test_lookup_barcode_http_error_raises_external_source_error(monkeypatch):
    """Req 2.8: a transport/HTTP error → ExternalSourceError."""

    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    _install_mock(monkeypatch, handler)

    with pytest.raises(ExternalSourceError):
        await lookup_barcode("7501234567890")


# ── search_by_name: products list → mapped candidates ────────────────────────


async def test_search_by_name_returns_mapped_candidates(monkeypatch):
    """Req 3.2, 4.5: a 200 with a products list → a list of mapped candidates,
    and the request carries the descriptive User-Agent."""
    captured = []
    payload = {
        "products": [
            {
                "code": "111",
                "product_name": "Manzana",
                "nutriments": {"energy-kcal_100g": 52.0, "carbohydrates_100g": 14.0},
            },
            {
                "code": "222",
                "product_name": "Plátano",
                "nutriments": {"energy-kcal_100g": 89.0},
            },
        ]
    }
    _install_mock(monkeypatch, _json_response(payload), captured=captured)

    results = await search_by_name("fruta")

    assert len(results) == 2
    assert results[0]["name"] == "Manzana"
    assert results[0]["kcal"] == 52.0
    assert results[0]["carbs"] == 14.0
    assert results[1]["name"] == "Plátano"
    assert all(r["source"] == "off" for r in results)

    assert len(captured) == 1
    assert captured[0].headers.get("user-agent") == fls.USER_AGENT


# ── search_by_name: degradations all return [] (never raise) ─────────────────


async def test_search_by_name_non_200_returns_empty_list(monkeypatch):
    """Req 3.5: a non-200 response degrades to [] without raising."""
    _install_mock(monkeypatch, _json_response({"products": []}, status_code=503))
    assert await search_by_name("fruta") == []


async def test_search_by_name_timeout_returns_empty_list(monkeypatch):
    """Req 3.5: a timeout degrades to [] without raising."""

    def handler(request):
        raise httpx.TimeoutException("timed out", request=request)

    _install_mock(monkeypatch, handler)
    assert await search_by_name("fruta") == []


async def test_search_by_name_http_error_returns_empty_list(monkeypatch):
    """Req 3.5: a transport/HTTP error degrades to [] without raising."""

    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    _install_mock(monkeypatch, handler)
    assert await search_by_name("fruta") == []


async def test_search_by_name_malformed_json_returns_empty_list(monkeypatch):
    """Req 3.5: a 200 whose body is not valid JSON degrades to [] (no raise)."""

    def handler(_request):
        return httpx.Response(200, content=b"<html>not json</html>")

    _install_mock(monkeypatch, handler)
    assert await search_by_name("fruta") == []


async def test_search_by_name_missing_products_returns_empty_list(monkeypatch):
    """Req 3.5: a 200 JSON without a 'products' list degrades to [] (no raise)."""
    _install_mock(monkeypatch, _json_response({"count": 0}))
    assert await search_by_name("fruta") == []
