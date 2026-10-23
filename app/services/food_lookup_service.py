"""Food_Lookup_Service: query Open Food Facts (barcode + name) and map results to a FoodIn-shaped candidate. External source is best-effort with a 10s timeout and graceful degradation. User-facing messages are Spanish; code is English."""

import httpx

# Open Food Facts endpoints (verified, no API key required).
OFF_PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"

# Field selectors sent to Open Food Facts to limit the payload.
OFF_PRODUCT_FIELDS = (
    "code,product_name,brands,quantity,serving_size,serving_quantity,"
    "nutriments,image_front_small_url"
)
OFF_SEARCH_FIELDS = "code,product_name,brands,nutriments,image_front_small_url"

# Lookup_Timeout in seconds (Req 2.8, 3.5).
LOOKUP_TIMEOUT = 10.0

# Descriptive User-Agent required by Open Food Facts (Req 4.5).
USER_AGENT = "HabitTrack/1.0 (https://habittrack.app; soporte@habittrack.app)"

# Inclusive barcode length bounds in digits (Req 1.2, 2.6).
BARCODE_LEN = (8, 14)


class LookupError(Exception):
    """Base class for Food_Lookup_Service errors.

    Note: this intentionally shadows the Python builtin ``LookupError`` within
    this module, matching the design. The router translates these into Spanish
    user-facing messages.
    """


class InvalidBarcodeError(LookupError):
    """The barcode is not an 8..14 digit string (Req 2.6)."""


class NotFoundError(LookupError):
    """Open Food Facts has no product for the barcode (status 0) (Req 2.7)."""


class ExternalSourceError(LookupError):
    """Open Food Facts timed out or failed (Req 2.8)."""


def normalize_barcode(code) -> str:
    """Trim surrounding whitespace from a barcode string (Req 1.5).

    Non-string input coerces to an empty string.
    """
    if not isinstance(code, str):
        return ""
    return code.strip()


def is_valid_barcode(code) -> bool:
    """True iff code is a string of 8..14 digits after normalization (Req 2.6)."""
    n = normalize_barcode(code)
    return n.isdigit() and BARCODE_LEN[0] <= len(n) <= BARCODE_LEN[1]


def _num(v):
    """Coerce an int/float (but not bool) to float; otherwise return None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def map_off_product(product: dict, fallback_barcode: str) -> dict:
    """PURE. Map an Open Food Facts product dict to a Food_Candidate dict
    (FoodIn-shaped). Missing/None nutriment fields become None; a missing
    product_name falls back to the barcode. Never raises on missing fields
    (Req 2.3, 2.5, 4.1-4.4). Returns:
        {name, barcode, kcal, protein, fat, carbs, fiber, brand, image_url,
         source: "off"}
    """
    if not isinstance(product, dict):
        product = {}

    # name: product_name when a non-empty string after strip, else fallback.
    raw_name = product.get("product_name")
    if isinstance(raw_name, str) and raw_name.strip():
        name = raw_name.strip()
    else:
        name = fallback_barcode

    # barcode: product code when present and truthy, else fallback.
    code = product.get("code")
    barcode = code if code else fallback_barcode

    # nutriments: guard against None / non-dict.
    nutriments = product.get("nutriments")
    if not isinstance(nutriments, dict):
        nutriments = {}

    return {
        "name": name,
        "barcode": barcode,
        "kcal": _num(nutriments.get("energy-kcal_100g")),
        "protein": _num(nutriments.get("proteins_100g")),
        "fat": _num(nutriments.get("fat_100g")),
        "carbs": _num(nutriments.get("carbohydrates_100g")),
        "fiber": _num(nutriments.get("fiber_100g")),
        "brand": product.get("brands") or None,
        "image_url": product.get("image_front_small_url") or None,
        "source": "off",
    }

import logging

logger = logging.getLogger(__name__)


async def lookup_barcode(code: str) -> dict:
    """Look up a single product by barcode on Open Food Facts (Req 2.2, 2.3,
    2.6, 2.7, 2.8, 4.5).

    Raises InvalidBarcodeError for malformed codes, NotFoundError when the
    product is absent (status 0), and ExternalSourceError on timeout/HTTP
    failure. User-facing messages are Spanish.
    """
    if not is_valid_barcode(code):
        raise InvalidBarcodeError(
            "El código de barras no es válido. Debe tener entre 8 y 14 dígitos."
        )

    norm = normalize_barcode(code)
    url = OFF_PRODUCT_URL.format(code=norm)
    params = {"fields": OFF_PRODUCT_FIELDS}

    # Guard only the network call + JSON parse so our own domain errors
    # (NotFoundError raised below) are not swallowed by the httpx except.
    try:
        async with httpx.AsyncClient(
            timeout=LOOKUP_TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(url, params=params)
        if response.status_code != 200:
            raise ExternalSourceError(
                "No pudimos consultar la base de alimentos en este momento. "
                "Inténtalo de nuevo más tarde."
            )
        data = response.json()
    except ExternalSourceError:
        raise
    except (httpx.TimeoutException, httpx.HTTPError) as exc:
        raise ExternalSourceError(
            "No pudimos consultar la base de alimentos en este momento. "
            "Inténtalo de nuevo más tarde."
        ) from exc
    except Exception as exc:  # transport / unexpected network errors
        raise ExternalSourceError(
            "No pudimos consultar la base de alimentos en este momento. "
            "Inténtalo de nuevo más tarde."
        ) from exc

    # Fetch succeeded: NotFoundError / mapping happen outside the httpx except.
    if data.get("status") != 1:
        raise NotFoundError(
            "No encontramos un alimento con ese código de barras."
        )

    return map_off_product(data.get("product") or {}, norm)


async def search_by_name(query: str) -> list[dict]:
    """Search products by name on Open Food Facts (Req 3.2, 3.5, 4.5).

    Best-effort: any failure (timeout, HTTP error, non-200, JSON error,
    missing products) returns an empty list and logs a warning. Never raises.
    """
    params = {
        "search_terms": query,
        "json": 1,
        "page_size": 20,
        "fields": OFF_SEARCH_FIELDS,
    }

    try:
        async with httpx.AsyncClient(
            timeout=LOOKUP_TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(OFF_SEARCH_URL, params=params)
        if response.status_code != 200:
            logger.warning(
                "Open Food Facts search returned status %s", response.status_code
            )
            return []
        data = response.json()
        products = data.get("products")
        if not isinstance(products, list):
            return []
        return [map_off_product(p, (p.get("code") if isinstance(p, dict) else "") or "") for p in products]
    except Exception as exc:
        logger.warning("Open Food Facts search failed: %s", exc)
        return []
