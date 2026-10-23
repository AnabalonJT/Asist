"""Example-based integration tests for the Food_Barcode endpoints added to the
existing meals router (``app/routes/meals.py``, mounted under ``/api/meals``):

- ``GET /api/meals/barcode/{code}`` — barcode lookup (local catalog first, then
  Open Food Facts) (Req 2.1, 2.6, 2.7, 2.8, 6.1).
- ``GET /api/meals/food-search?q=...`` — name search (local catalog, plus Open
  Food Facts as a best-effort fallback) (Req 3.1, 3.2, 3.4, 3.5, 6.1).

These are EXAMPLE-BASED integration tests (not property tests) for task 6.2.
The real Open Food Facts network is NEVER contacted: the service functions the
router calls (``food_lookup_service.lookup_barcode`` / ``search_by_name``) are
monkeypatched. A local-hit test installs a stub that FAILS if the external
source is ever invoked, proving the local catalog short-circuits the network
(Req 2.1).

Setup mirrors the proven route-level pattern of
``tests/test_goal_plan_routes.py`` and
``tests/test_property_goal_wizard_privacy.py`` (there is NO conftest.py):
a throwaway FastAPI app mounting ONLY ``meals.router`` at ``/api/meals``, an
in-memory async SQLite engine, ``import app.models`` + ``create_all`` to build
the full schema, ``app.database.get_db`` overridden to yield the shared session,
and a real JWT minted by ``app.services.auth_service.auth_service.create_token``.

Coverage:
- barcode lookup success (local) → candidate JSON, source="local", no network.
- barcode lookup success (off)   → candidate JSON, source="off".
- invalid barcode                → 400 Spanish.
- not found                      → 404 Spanish.
- external source error/timeout  → 503 Spanish.
- name search                    → list of candidates (local + off), empty list.
- unauthenticated                → 401/403 on both endpoints.
- privilege separation           → lookup/search work for a non-admin (Req 6.1);
                                    POST /foods by a non-admin → 403 (Req 6.3).

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema.
import app.models  # noqa: F401
from app.models.food import Food
from app.models.user import User
from app.routes import meals
from app.services import food_lookup_service
from app.services.auth_service import auth_service


# ── A fully-mapped off candidate (what map_off_product returns) ──────────────
def _off_candidate(barcode: str = "7501234567890") -> dict:
    """A Food_Candidate dict shaped exactly like map_off_product's output."""
    return {
        "name": "Chocolate Amargo",
        "barcode": barcode,
        "kcal": 546.0,
        "protein": 7.8,
        "fat": 31.0,
        "carbs": 61.0,
        "fiber": 7.0,
        "brand": "MarcaX",
        "image_url": "https://images.off/choco.jpg",
        "source": "off",
    }


# ── Harness ──────────────────────────────────────────────────────────────────
class Harness:
    """A throwaway app + in-memory DB for one test. Builds the schema, seeds a
    single non-admin user, mints a real JWT, and exposes a TestClient wired to
    the meals router with ``get_db`` overridden to the shared session."""

    def __init__(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        asyncio.run(self._create_schema())
        self.user_id = asyncio.run(self._seed_user())
        self.token = auth_service.create_token(self.user_id, is_admin=False)

        app = FastAPI()
        app.include_router(meals.router, prefix="/api/meals")
        session_factory = self.session_factory

        async def _override_get_db():
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app)

    async def _create_schema(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _seed_user(self) -> int:
        async with self.session_factory() as db:
            user = User(email="barcode@example.com", password_hash="x",
                        is_admin=False)
            db.add(user)
            await db.flush()
            await db.commit()
            return user.id

    def seed_food(self, **kwargs) -> int:
        """Insert a Food row and return its id. Defaults fill required columns."""
        fields = {
            "name": "Alimento Local",
            "kcal_per_100g": 100.0,
            "protein_g_per_100g": 5.0,
            "fat_g_per_100g": 2.0,
            "carbs_g_per_100g": 10.0,
            "fiber_g_per_100g": 1.0,
            "is_meat": False,
            "is_animal": False,
            "has_gluten": False,
            "barcode": None,
            "brand": None,
        }
        fields.update(kwargs)
        return asyncio.run(self._insert_food(fields))

    async def _insert_food(self, fields: dict) -> int:
        async with self.session_factory() as db:
            food = Food(**fields)
            db.add(food)
            await db.flush()
            await db.commit()
            return food.id

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def close(self):
        self.client.close()
        asyncio.run(self.engine.dispose())


@pytest.fixture
def harness():
    h = Harness()
    try:
        yield h
    finally:
        h.close()


# ── Monkeypatch helpers (the external source is NEVER contacted) ─────────────
def _patch_lookup(monkeypatch, fn):
    """Replace food_lookup_service.lookup_barcode with ``fn`` (async)."""
    monkeypatch.setattr(food_lookup_service, "lookup_barcode", fn)


def _patch_search(monkeypatch, fn):
    """Replace food_lookup_service.search_by_name with ``fn`` (async)."""
    monkeypatch.setattr(food_lookup_service, "search_by_name", fn)


# ── Auth required on both new endpoints (Req 6.1 implies auth) ───────────────
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/meals/barcode/7501234567890"),
        ("GET", "/api/meals/food-search?q=choco"),
    ],
)
def test_endpoints_require_auth(harness, method, path):
    """Both Food_Barcode endpoints reject an unauthenticated request with
    401 (or 403) and never run their handler."""
    resp = harness.client.request(method, path)
    assert resp.status_code in (401, 403), (
        f"{method} {path} without a token returned {resp.status_code}: {resp.text}"
    )


# ── GET /barcode/{code} ──────────────────────────────────────────────────────
def test_barcode_local_hit_returns_local_candidate_without_network(
    harness, monkeypatch
):
    """A barcode present in the local catalog returns a candidate with
    source="local" WITHOUT contacting Open Food Facts (Req 2.1)."""
    harness.seed_food(
        name="Avena Local",
        barcode="7501234567890",
        kcal_per_100g=389.0,
        protein_g_per_100g=16.9,
        fat_g_per_100g=6.9,
        carbs_g_per_100g=66.3,
        fiber_g_per_100g=10.6,
    )

    async def _must_not_call(code):
        raise AssertionError(
            "Open Food Facts must not be contacted on a local-catalog hit."
        )

    _patch_lookup(monkeypatch, _must_not_call)

    resp = harness.client.get(
        "/api/meals/barcode/7501234567890", headers=harness.headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "local"
    assert body["name"] == "Avena Local"
    assert body["barcode"] == "7501234567890"
    assert body["kcal"] == 389.0
    assert body["protein"] == 16.9
    assert body["fat"] == 6.9
    assert body["carbs"] == 66.3
    assert body["fiber"] == 10.6


def test_barcode_normalizes_whitespace_before_local_lookup(harness, monkeypatch):
    """A code with surrounding whitespace is normalized, so it still matches the
    stored (trimmed) barcode locally (Req 1.5)."""
    harness.seed_food(name="Leche Local", barcode="12345678")

    async def _must_not_call(code):
        raise AssertionError("External source must not be contacted.")

    _patch_lookup(monkeypatch, _must_not_call)

    # The URL path carries the code with trailing spaces (url-encoded).
    resp = harness.client.get(
        "/api/meals/barcode/12345678%20%20", headers=harness.headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["source"] == "local"
    assert resp.json()["name"] == "Leche Local"


def test_barcode_miss_local_then_off_success(harness, monkeypatch):
    """A barcode not in the catalog falls back to Open Food Facts; a successful
    lookup returns a candidate with source="off" (Req 2.2, 2.3, 2.5)."""
    candidate = _off_candidate("7501234567890")

    async def _lookup(code):
        assert code == "7501234567890"
        return candidate

    _patch_lookup(monkeypatch, _lookup)

    resp = harness.client.get(
        "/api/meals/barcode/7501234567890", headers=harness.headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "off"
    assert body["name"] == "Chocolate Amargo"
    assert body["barcode"] == "7501234567890"
    assert body["kcal"] == 546.0
    assert body["brand"] == "MarcaX"
    assert body["image_url"] == "https://images.off/choco.jpg"


def test_barcode_invalid_format_returns_400_spanish(harness, monkeypatch):
    """A code that is not 8..14 digits is rejected with 400 and a Spanish detail,
    without touching the DB or the network (Req 2.6)."""
    async def _must_not_call(code):
        raise AssertionError("External source must not be contacted on bad input.")

    _patch_lookup(monkeypatch, _must_not_call)

    resp = harness.client.get(
        "/api/meals/barcode/123", headers=harness.headers
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and detail.strip()
    assert "código de barras" in detail.lower()


def test_barcode_not_found_returns_404_spanish(harness, monkeypatch):
    """When Open Food Facts has no product (NotFoundError), the endpoint returns
    404 with a Spanish detail (Req 2.7)."""
    async def _lookup(code):
        raise food_lookup_service.NotFoundError(
            "No encontramos un alimento con ese código de barras."
        )

    _patch_lookup(monkeypatch, _lookup)

    resp = harness.client.get(
        "/api/meals/barcode/7501234567890", headers=harness.headers
    )
    assert resp.status_code == 404, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and detail.strip()
    assert "no encontramos" in detail.lower()


def test_barcode_external_error_returns_503_spanish(harness, monkeypatch):
    """A timeout / transport failure (ExternalSourceError) surfaces as 503 with a
    Spanish detail, never a raw 500 (Req 2.8)."""
    async def _lookup(code):
        raise food_lookup_service.ExternalSourceError(
            "No pudimos consultar la base de alimentos en este momento. "
            "Inténtalo de nuevo más tarde."
        )

    _patch_lookup(monkeypatch, _lookup)

    resp = harness.client.get(
        "/api/meals/barcode/7501234567890", headers=harness.headers
    )
    assert resp.status_code == 503, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and detail.strip()
    assert "no pudimos consultar" in detail.lower()


# ── GET /food-search?q=... ───────────────────────────────────────────────────
def test_food_search_invalid_term_returns_400_spanish(harness, monkeypatch):
    """An empty search term is out of the 1..100 range → 400 Spanish detail,
    without contacting the external source (Req 3.4)."""
    async def _must_not_call(q):
        raise AssertionError("External source must not be contacted on bad input.")

    _patch_search(monkeypatch, _must_not_call)

    resp = harness.client.get(
        "/api/meals/food-search?q=%20%20", headers=harness.headers
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and detail.strip()
    assert "término de búsqueda" in detail.lower()


def test_food_search_local_results_do_not_query_off(harness, monkeypatch):
    """When the local catalog has at least one match, the external source is NOT
    queried and only local candidates are returned (Req 3.1)."""
    harness.seed_food(name="Chocolate Local", barcode=None)

    async def _must_not_call(q):
        raise AssertionError(
            "External source must not be contacted when local results exist."
        )

    _patch_search(monkeypatch, _must_not_call)

    resp = harness.client.get(
        "/api/meals/food-search?q=chocolate", headers=harness.headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list) and len(body) >= 1
    assert all(c["source"] == "local" for c in body)
    assert any(c["name"] == "Chocolate Local" for c in body)


def test_food_search_no_local_combines_off_results(harness, monkeypatch):
    """With no local match, the endpoint appends Open Food Facts results as
    additional candidates (Req 3.2)."""
    async def _search(q):
        assert q == "chocolate"
        return [_off_candidate("7501234567890")]

    _patch_search(monkeypatch, _search)

    resp = harness.client.get(
        "/api/meals/food-search?q=chocolate", headers=harness.headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list) and len(body) == 1
    assert body[0]["source"] == "off"
    assert body[0]["name"] == "Chocolate Amargo"


def test_food_search_off_failure_returns_only_locals(harness, monkeypatch):
    """When the external search degrades (returns []), the endpoint responds with
    only the local results (here, an empty list) and no error (Req 3.5)."""
    async def _search(q):
        # best-effort: the service swallows errors and returns [].
        return []

    _patch_search(monkeypatch, _search)

    resp = harness.client.get(
        "/api/meals/food-search?q=inexistente", headers=harness.headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == []


# ── Privilege separation (Req 6.1, 6.3) ──────────────────────────────────────
def test_lookup_and_search_work_for_non_admin(harness, monkeypatch):
    """A non-admin Authenticated_User can use both lookup and search (Req 6.1)."""
    async def _lookup(code):
        return _off_candidate("7501234567890")

    async def _search(q):
        return [_off_candidate("7501234567890")]

    _patch_lookup(monkeypatch, _lookup)
    _patch_search(monkeypatch, _search)

    r1 = harness.client.get(
        "/api/meals/barcode/7501234567890", headers=harness.headers
    )
    r2 = harness.client.get(
        "/api/meals/food-search?q=choco", headers=harness.headers
    )
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text


def test_catalog_write_still_requires_admin(harness):
    """Writing the global catalog (POST /foods) by a non-admin is forbidden,
    preserving the privilege separation (Req 6.3)."""
    resp = harness.client.post(
        "/api/meals/foods",
        json={
            "name": "Nuevo Alimento",
            "kcal": 100.0,
            "protein": 5.0,
            "fat": 2.0,
            "carbs": 10.0,
            "fiber": 1.0,
        },
        headers=harness.headers,
    )
    assert resp.status_code == 403, resp.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
