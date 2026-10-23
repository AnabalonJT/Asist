"""End-to-end pipeline test for the Meal Planner (bot chef).

Exercises the real HTTP API against a running deployment (Fly.io by default):
login -> read catalog -> add inventory -> set dietary profile -> set targets
(derive from fitness, else manual) -> generate meal plan -> read plan and
shopping list. Leaves real data on the account so you can see it on the web
(Comidas tab).

Usage (PowerShell):
    $env:MEAL_EMAIL="jtanabalon@gmail.com"; $env:MEAL_PASSWORD="tu_clave"; python scripts/pipeline_meals.py

Optional:
    $env:MEAL_BASE_URL="https://habittrack-bot.fly.dev"   # default
    $env:MEAL_BASE_URL="http://localhost:8000"            # to test locally

Nothing is hardcoded: credentials come from env vars so no secret is stored.
"""
import os
import sys
import json

import httpx

BASE_URL = os.environ.get("MEAL_BASE_URL", "https://habittrack-bot.fly.dev").rstrip("/")
EMAIL = os.environ.get("MEAL_EMAIL")
PASSWORD = os.environ.get("MEAL_PASSWORD")

# Plan generation calls the LLM; backend may retry (2 x 120s) with the slow free model.
TIMEOUT = httpx.Timeout(240.0)

# Foods to ensure are in the user inventory. Names should match the seeded
# catalog (case/accent-insensitive). Grams are optional per item.
INVENTORY = [
    ("Pollo", 1000),
    ("Arroz", 1000),
    ("Huevo", 700),
    ("Avena", 500),
    ("Lenteja", 500),
    ("Brocoli", 400),
    ("Platano", 600),
    ("Aceite de oliva", 250),
]


def _pretty(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _step(n: int, title: str) -> None:
    print(f"\n{'=' * 60}\n[{n}] {title}\n{'=' * 60}")


def main() -> int:
    if not EMAIL or not PASSWORD:
        print("ERROR: set MEAL_EMAIL and MEAL_PASSWORD environment variables.")
        print('  PowerShell: $env:MEAL_EMAIL=\"tu@email\"; $env:MEAL_PASSWORD=\"clave\"')
        return 2

    print(f"Base URL: {BASE_URL}")
    print(f"User: {EMAIL}")

    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        # -- 1. Login --
        _step(1, "Login")
        r = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r.status_code != 200:
            print(f"  Login failed ({r.status_code}): {r.text}")
            return 1
        token = r.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        print("  OK, token obtained.")

        # -- 2. Read the food catalog --
        _step(2, "GET /api/meals/foods (catalogo)")
        r = client.get("/api/meals/foods")
        print(f"  status={r.status_code}")
        catalog = r.json() if r.status_code == 200 else []
        if r.status_code == 200:
            names = [f["name"] for f in catalog]
            print(f"  {len(names)} alimentos: {', '.join(names)}")
        else:
            print("  " + r.text)
        catalog_names = {f["name"].strip().lower() for f in catalog}

        # -- 3. Add foods to the user inventory --
        _step(3, "POST /api/meals/inventory (despensa)")
        for name, grams in INVENTORY:
            payload = {"food_name": name, "quantity_grams": grams}
            if name.strip().lower() not in catalog_names:
                # Provide nutrition data so the service can create the food.
                payload["new_food"] = {
                    "name": name, "kcal": 100, "protein": 5,
                    "fat": 2, "carbs": 15, "fiber": 1,
                }
            r = client.post("/api/meals/inventory", json=payload)
            print(f"  {name} ({grams}g) -> status={r.status_code}")
            if r.status_code != 200:
                print("    " + r.text)

        r = client.get("/api/meals/inventory")
        if r.status_code == 200:
            print(f"  Inventario actual: {len(r.json())} items")

        # -- 4. Set dietary profile --
        _step(4, "PUT /api/meals/dietary (restricciones)")
        dietary_payload = {
            "vegetarian": False,
            "vegan": False,
            "gluten_free": False,
            "allergens": ["mani"],
        }
        r = client.put("/api/meals/dietary", json=dietary_payload)
        print(f"  status={r.status_code}")
        print("  " + _pretty(r.json()) if r.status_code == 200 else "  " + r.text)

        # -- 5. Targets: try derive from fitness, else set manual --
        _step(5, "POST /api/meals/targets/derive (o manual si falla)")
        r = client.post("/api/meals/targets/derive")
        print(f"  derive status={r.status_code}")
        if r.status_code == 200:
            print("  " + _pretty(r.json()))
        else:
            print(f"  derive fallo: {r.text}")
            print("  -> Estableciendo metas manuales.")
            manual = {"kcal": 2200, "protein_g": 160, "fat_g": 70, "carbs_g": 220}
            r = client.put("/api/meals/targets", json=manual)
            print(f"  manual status={r.status_code}")
            print("  " + _pretty(r.json()) if r.status_code == 200 else "  " + r.text)

        # -- 6. Generate the meal plan (LLM) --
        _step(6, "POST /api/meals/plan/generate  (llama al LLM, puede tardar)")
        r = client.post("/api/meals/plan/generate")
        print(f"  status={r.status_code}")
        if r.status_code == 200:
            plan = r.json()
            days = plan.get("structure", [])
            print(f"  Plan id={plan['id']} dias={len(days)}")
            for day in days:
                meals = day.get("meals", [])
                totals = day.get("totals", {})
                print(f"    - {day.get('day')}: {len(meals)} comidas, "
                      f"{totals.get('kcal')} kcal")
        else:
            print(f"  Generacion devolvio {r.status_code}: {r.text}")
            print("  (El LLM gratuito a veces falla/tarda; puedes reintentar.)")

        # -- 7. Read back plan and shopping list --
        _step(7, "GET plan / shopping-list")
        r = client.get("/api/meals/plan")
        print(f"  GET /plan status={r.status_code}")
        r = client.get("/api/meals/shopping-list")
        print(f"  GET /shopping-list status={r.status_code}")
        if r.status_code == 200:
            items = r.json()
            print(f"  Faltan {len(items)} alimentos:")
            for it in items:
                print(f"    - {it['food_name']}: {it['grams']} g")
        else:
            print("  " + r.text)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETO. Abre la web -> pestana Comidas para verlo:")
    print(f"  {BASE_URL}/meals")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
