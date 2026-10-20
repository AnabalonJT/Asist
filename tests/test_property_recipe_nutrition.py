"""Property tests for recipe aggregate nutrition (food-add-redesign).

These target the PURE function ``compute_recipe_nutrition`` in
``app.services.recipe_service``. No DB or I/O is involved, so they follow the
same style as the other ``test_property_*`` modules in this repo.
"""
import math

from hypothesis import given, strategies as st

from app.services.recipe_service import compute_recipe_nutrition


# An ingredient: positive grams and per-100 g macros; fiber may be None.
_grams = st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
_macro = st.floats(min_value=0.0, max_value=900.0, allow_nan=False, allow_infinity=False)
_fiber = st.one_of(st.none(), st.floats(min_value=0.0, max_value=100.0,
                                        allow_nan=False, allow_infinity=False))


@st.composite
def _ingredient(draw):
    return {
        "grams": draw(_grams),
        "kcal_per_100g": draw(_macro),
        "protein_g_per_100g": draw(_macro),
        "fat_g_per_100g": draw(_macro),
        "carbs_g_per_100g": draw(_macro),
        "fiber_g_per_100g": draw(_fiber),
    }


_ingredients = st.lists(_ingredient(), min_size=1, max_size=20)


def _reference(ingredients):
    """Independent model-based reference: grams-weighted per-100 g average."""
    total = sum(i["grams"] for i in ingredients)
    out = {}
    for key, src in (("kcal", "kcal_per_100g"), ("protein", "protein_g_per_100g"),
                     ("fat", "fat_g_per_100g"), ("carbs", "carbs_g_per_100g")):
        abs_sum = sum(i[src] / 100.0 * i["grams"] for i in ingredients)
        out[key] = abs_sum / total * 100.0
    any_fiber = any(i["fiber_g_per_100g"] is not None for i in ingredients)
    if any_fiber:
        abs_fiber = sum((i["fiber_g_per_100g"] or 0.0) / 100.0 * i["grams"] for i in ingredients)
        out["fiber"] = abs_fiber / total * 100.0
    else:
        out["fiber"] = None
    return out


@given(ingredients=_ingredients)
def test_recipe_nutrition_matches_weighted_average(ingredients):
    """Feature: food-add-redesign, Property 5: Recipe_Nutrition es la suma
    ponderada por 100 g (dentro de +/-0.01 del modelo de referencia)."""
    result = compute_recipe_nutrition(ingredients)
    ref = _reference(ingredients)
    for key in ("kcal", "protein", "fat", "carbs"):
        assert math.isclose(result[key], ref[key], abs_tol=0.01, rel_tol=1e-9)
    if ref["fiber"] is None:
        assert result["fiber"] is None
    else:
        assert result["fiber"] is not None
        assert math.isclose(result["fiber"], ref["fiber"], abs_tol=0.01, rel_tol=1e-9)


@given(ingredients=_ingredients,
       scale=st.floats(min_value=0.01, max_value=1000.0,
                       allow_nan=False, allow_infinity=False))
def test_recipe_nutrition_invariant_to_uniform_scaling(ingredients, scale):
    """Feature: food-add-redesign, Property 5: la Recipe_Nutrition por 100 g es
    invariante al escalado uniforme de todos los gramos."""
    base = compute_recipe_nutrition(ingredients)
    scaled_ingredients = [dict(i, grams=i["grams"] * scale) for i in ingredients]
    scaled = compute_recipe_nutrition(scaled_ingredients)
    for key in ("kcal", "protein", "fat", "carbs"):
        assert math.isclose(base[key], scaled[key], abs_tol=0.01, rel_tol=1e-6)
    if base["fiber"] is None:
        assert scaled["fiber"] is None
    else:
        assert math.isclose(base["fiber"], scaled["fiber"], abs_tol=0.01, rel_tol=1e-6)


@given(fibers=st.lists(st.none(), min_size=1, max_size=10))
def test_fiber_none_only_when_all_ingredients_none(fibers):
    """Feature: food-add-redesign, Property 5 (fiber rule): fiber es None solo si
    todos los ingredientes tienen fiber None."""
    ingredients = [{
        "grams": 100.0, "kcal_per_100g": 10.0, "protein_g_per_100g": 1.0,
        "fat_g_per_100g": 1.0, "carbs_g_per_100g": 1.0, "fiber_g_per_100g": f,
    } for f in fibers]
    assert compute_recipe_nutrition(ingredients)["fiber"] is None
