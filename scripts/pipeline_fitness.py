"""End-to-end pipeline test for the Fitness Coach.

Exercises the real HTTP API against a running deployment (Fly.io by default):
login -> profile -> goal -> weight entries -> generate plan -> read plan,
progress and adherence. Leaves real data on the account so you can see it on the
web (Fitness tab).

Usage (PowerShell):
    $env:FIT_EMAIL="jtanabalon@gmail.com"; $env:FIT_PASSWORD="tu_clave"; python scripts/pipeline_fitness.py

Optional:
    $env:FIT_BASE_URL="https://habittrack-bot.fly.dev"   # default
    $env:FIT_BASE_URL="http://localhost:8000"            # to test locally

Nothing is hardcoded: credentials come from env vars so no secret is stored.
"""
import os
import sys
import json
from datetime import date, timedelta

import httpx

BASE_URL = os.environ.get("FIT_BASE_URL", "https://habittrack-bot.fly.dev").rstrip("/")
EMAIL = os.environ.get("FIT_EMAIL")
PASSWORD = os.environ.get("FIT_PASSWORD")

# Plan generation calls the LLM (can take up to ~60s).
TIMEOUT = httpx.Timeout(90.0)


def _pretty(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _step(n: int, title: str) -> None:
    print(f"\n{'=' * 60}\n[{n}] {title}\n{'=' * 60}")


def main() -> int:
    if not EMAIL or not PASSWORD:
        print("ERROR: set FIT_EMAIL and FIT_PASSWORD environment variables.")
        print('  PowerShell: $env:FIT_EMAIL="tu@email"; $env:FIT_PASSWORD="clave"')
        return 2

    print(f"Base URL: {BASE_URL}")
    print(f"User: {EMAIL}")

    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        # ── 1. Login ─────────────────────────────────────────────────────────
        _step(1, "Login")
        r = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r.status_code != 200:
            print(f"  Login failed ({r.status_code}): {r.text}")
            return 1
        token = r.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        print("  OK, token obtained.")

        # ── 2. Create/update fitness profile ─────────────────────────────────
        _step(2, "PUT /api/fitness/profile")
        profile_payload = {
            "weight_kg": 80,
            "height_cm": 178,
            "age": 28,
            "sex": "male",
            "level": "intermedio",
            "equipment": ["mancuernas", "barra", "banco", "rack", "poleas", "barra de dominadas", "barras paralelas", "peso corporal"],
            "days_per_week": 4,
            "minutes_per_session": 60,
        }
        r = client.put("/api/fitness/profile", json=profile_payload)
        print(f"  status={r.status_code}")
        print("  " + _pretty(r.json()))
        if r.status_code != 200:
            return 1

        # ── 3. Define a weight_target goal (shows target_rate) ───────────────
        _step(3, "PUT /api/fitness/goal (weight_target 80 -> 74 kg)")
        target_date = (date.today() + timedelta(weeks=10)).isoformat()
        goal_payload = {
            "goal_type": "weight_target",
            "target_weight_kg": 74,
            "target_date": target_date,
        }
        r = client.put("/api/fitness/goal", json=goal_payload)
        print(f"  status={r.status_code}  (fecha objetivo: {target_date})")
        print("  " + _pretty(r.json()))
        if r.status_code != 200:
            return 1

        # ── 4. Log a few weight entries (curve for the chart) ────────────────
        _step(4, "POST /api/fitness/weight (varias fechas)")
        weigh_ins = [
            (date.today() - timedelta(days=21), 80.0),
            (date.today() - timedelta(days=14), 79.2),
            (date.today() - timedelta(days=7), 78.5),
            (date.today(), 78.0),
        ]
        for d, w in weigh_ins:
            r = client.post(
                "/api/fitness/weight",
                json={"weight_kg": w, "entry_date": d.isoformat()},
            )
            print(f"  {d.isoformat()} -> {w}kg : status={r.status_code}")
            if r.status_code != 200:
                print("    " + r.text)

        # ── 5. Generate a workout plan (LLM) ─────────────────────────────────
        _step(5, "POST /api/fitness/plan/generate  (llama al LLM, puede tardar)")
        r = client.post("/api/fitness/plan/generate")
        print(f"  status={r.status_code}")
        if r.status_code == 200:
            plan = r.json()
            print(f"  Plan id={plan['id']} goal_type={plan['goal_type']} "
                  f"días={len(plan['structure'])}")
            for day in plan["structure"]:
                exs = day.get("exercises", [])
                print(f"    - {day.get('day')}: {len(exs)} ejercicios")
        else:
            print(f"  Generación devolvió {r.status_code}: {r.text}")
            print("  (El LLM gratuito a veces falla/tarda; puedes reintentar.)")

        # ── 6. Read back plan / progress / adherence ─────────────────────────
        _step(6, "GET plan / progress / adherence")
        r = client.get("/api/fitness/plan")
        print(f"  GET /plan status={r.status_code}")
        r = client.get("/api/fitness/progress")
        print(f"  GET /progress status={r.status_code}: {_pretty(r.json())}")
        r = client.get("/api/fitness/adherence")
        print(f"  GET /adherence status={r.status_code}: {_pretty(r.json())}")

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETO. Abre la web -> pestaña Fitness para verlo:")
    print(f"  {BASE_URL}/fitness")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
