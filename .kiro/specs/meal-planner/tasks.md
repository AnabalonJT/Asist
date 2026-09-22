# Implementation Plan: Meal Planner

## Overview

Plan de implementación incremental para el Meal_Planner (bot chef). El orden va de los modelos y la migración hacia la capa de servicio (funciones puras primero, luego I/O), el LLM, los endpoints, y por último Telegram y el frontend. Cada tarea construye sobre las anteriores y termina integrándose (routers registrados en `main.py`, seed invocado desde `init_db`, ruta y navbar cableados). Los property tests (Hypothesis, mínimo 100 iteraciones, etiquetados `# Feature: meal-planner, Property N: ...`) se ubican como subtareas opcionales (`*`) junto a la función que validan, según el mapa propiedad→función del diseño. Los tests de ejemplo/integración y la lista de compras (Req 13, nice-to-have) también son opcionales (`*`).

## Tasks

- [ ] 1. Modelos de datos y registro
  - [ ] 1.1 Crear los cinco modelos SQLAlchemy 2.0 en `app/models/`
    - `food.py`: `Food` con nutrición por 100 g (`name` unique/index 1..100, `kcal_per_100g`, `protein_g_per_100g`, `fat_g_per_100g`, `carbs_g_per_100g`, `fiber_g_per_100g` nullable) y flags `is_meat`/`is_animal`/`has_gluten` (default False)
    - `user_food_inventory.py`: `UserFoodInventory` con `user_id`/`food_id` FK, `quantity_grams` nullable y `UniqueConstraint("user_id", "food_id", name="uq_user_food")`; relationship a `User` (back_populates="food_inventory") y a `Food`
    - `dietary_profile.py`: `DietaryProfile` 1:1 (`user_id` unique), flags `vegetarian`/`vegan`/`gluten_free`, `allergens` String(500) JSON default `'[]'`, método `allergen_list()`
    - `nutrition_targets.py`: `NutritionTargets` 1:1 (`user_id` unique), `kcal`/`protein_g`/`fat_g`/`carbs_g`, `source` String(10)
    - `meal_plan.py`: `MealPlan` con `structure` Text (JSON), `active` Boolean index default True, método `structure_list()`
    - Usar `Mapped`/`mapped_column`, `func.now()` para timestamps, imports de relación bajo `TYPE_CHECKING`
    - _Requirements: 1.3, 1.4, 2.1, 2.2, 3.1, 5.4, 6.2, 6.11, 7.1, 7.2, 7.3, 13.5_

  - [ ] 1.2 Añadir relationships de Meal_Planner a `app/models/user.py`
    - `food_inventory` (list, cascade delete-orphan), `dietary_profile` (uselist=False), `nutrition_targets` (uselist=False), `meal_plans` (list, cascade delete-orphan); imports guardados por `TYPE_CHECKING`
    - _Requirements: 2.1, 3.1, 5.4, 6.2_

  - [ ] 1.3 Registrar los modelos en `app/models/__init__.py` y en `init_db`
    - Añadir imports y `__all__` para `Food`, `UserFoodInventory`, `DietaryProfile`, `NutritionTargets`, `MealPlan`
    - Añadir los cinco módulos al import de registro en `app/database.py::init_db` para que `create_all` cree las tablas (red de seguridad idempotente)
    - _Requirements: 1.1, 1.2_

- [ ] 2. Migración Alembic para las tablas del Meal_Planner
  - [ ] 2.1 Crear la migración autogenerada de las cinco tablas
    - Generar con `alembic revision --autogenerate -m "add meal planner tables"` y revisar: `create_table` de `foods`, `user_food_inventory`, `dietary_profiles`, `nutrition_targets`, `meal_plans`
    - Verificar el índice único de `foods.name`, los unique de `dietary_profiles.user_id` y `nutrition_targets.user_id`, la `UniqueConstraint (user_id, food_id)` de `user_food_inventory` y el índice de `meal_plans.active`
    - _Requirements: 1.3, 2.2, 3.1, 5.4, 6.11_

- [ ] 3. Seed del catálogo de alimentos
  - [ ] 3.1 Crear `scripts/seed_foods.py` idempotente y cablearlo a `init_db`
    - Seguir el patrón de `scripts/seed_calorie_formulas.py`: lista base de alimentos con valores por 100 g y flags (Pollo, Arroz, Huevo, Avena, Lenteja, Salmón, Leche, Pan, etc.); idempotente por `name`
    - Exponer `seed_if_empty(session)` que inserta el conjunto semilla solo si `SELECT count(*) FROM foods == 0` y no hace nada si hay ≥1 alimento
    - Invocar `seed_if_empty` desde `init_db` tras `create_all`/`_migrate_columns`; mantener `main()` ejecutable manualmente
    - Garantizar la invariante `is_meat ⇒ is_animal` en los datos semilla
    - _Requirements: 1.1, 1.2_

  - [ ]* 3.2 Property test del seed idempotente
    - **Property 1: Seed idempotente del catálogo**
    - **Validates: Requirements 1.1, 1.2**

- [ ] 4. Adaptador fitness_link (dependencia opcional con fitness-coach)
  - [ ] 4.1 Crear `app/services/fitness_link.py`
    - `get_fitness_view(db, user_id) -> dict | None`: import perezoso de `FitnessProfile` con `try/except ImportError`; consulta `fitness_profiles` con `try/except` para tabla inexistente/errores SQL → `None`; devuelve `meal_planner_view()` o `None`
    - `compute_target_rate_for_view(view) -> dict | None`: import perezoso de `fitness_service.compute_target_rate`; devuelve `{'daily_kcal_delta','direction'}` o `None` si no aplica/está ausente
    - Nunca lanzar excepciones hacia afuera (degradación limpia)
    - _Requirements: 4.6, 5.5, 8.5_

- [ ] 5. MealService — constantes, excepciones y funciones puras
  - [ ] 5.1 Crear `app/services/meal_service.py` con constantes y excepciones
    - Constantes: `CALORIE_TOLERANCE=0.10`, `KCAL_PER_G`, `MACRO_KCAL_TOLERANCE=10.0`, `PROTEIN_PER_KG`, `VALID_MEAL_TYPES`, `PLAN_DAYS=7`, rangos de validación (`FOOD_*`, `INVENTORY_GRAMS_RANGE`, `ALLERGEN_LEN`, `MANUAL_*`), `DIET_FLAGS`, `MEAL_DISCLAIMER`
    - Excepciones internas: `ValidationError`, `GoalRequiredError`, `LLMError` (con `kind`), `ToleranceError`, `DietaryError`, `ShoppingRequiresPlanError`, `ForbiddenError`
    - _Requirements: 4.5, 6.7, 12.6_

  - [ ] 5.2 Implementar `validate_food_fields` y `validate_manual_targets`
    - `validate_food_fields(name, kcal, protein, fat, carbs, fiber)`: rangos nombre 1..100, kcal 0..900, macros/fibra 0..100 (fibra puede ser None); mensaje en español identificando el campo inválido
    - `validate_manual_targets(kcal, protein_g, fat_g, carbs_g)`: rangos manuales, all-or-nothing, mensaje en español listando cada campo fuera de rango con su rango válido
    - _Requirements: 1.3, 1.4, 1.5, 2.3, 2.4, 5.1, 5.2_

  - [ ]* 5.3 Property tests de validación de campos de alimento
    - **Property 2: Alimento con campos válidos es aceptado**
    - **Property 3: Alimento con algún campo inválido es rechazado y el catálogo se preserva**
    - **Validates: Requirements 1.3, 1.4, 1.5, 2.4**

  - [ ] 5.4 Implementar `estimate_maintenance_kcal` y `derive_nutrition_targets` (puras)
    - `estimate_maintenance_kcal(view)`: Mifflin-St Jeor + factor de actividad ligera (1.375); `ValidationError` si faltan datos corporales
    - `derive_nutrition_targets(view, target_rate)`: kcal por objetivo (`gain_muscle`/`maintain`/`lose_weight`/`weight_target`/otros), proteína por `PROTEIN_PER_KG`, reparto restante 40% grasa / 60% carbo con 9/4 kcal/g; post-condición `|prot*4 + carb*4 + fat*9 - kcal| <= 10`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 8.1, 8.2_

  - [ ]* 5.5 Property test de derivación por objetivo
    - **Property 8: Derivación de metas por objetivo**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 8.1, 8.2**

  - [ ]* 5.6 Property test del reparto de macros 4/4/9
    - **Property 9: Reparto de macros consistente con 4/4/9**
    - **Validates: Requirements 4.5**

  - [ ] 5.7 Implementar `check_calorie_tolerance` y `validate_plan_structure` (puras)
    - `check_calorie_tolerance(day_totals, target_kcal)`: True sii `|day_kcal - target_kcal| <= CALORIE_TOLERANCE * target_kcal`
    - `validate_plan_structure(structure)`: exactamente 7 días, cada día ≥1 comida de `VALID_MEAL_TYPES`, cada comida ≥1 ítem con gramos 1..100000, totales presentes por día
    - _Requirements: 6.3, 6.4, 6.5, 6.7_

  - [ ]* 5.8 Property test del predicado de tolerancia
    - **Property 15: Predicado de tolerancia calórica**
    - **Validates: Requirements 6.7**

  - [ ]* 5.9 Property test de validación de estructura del plan
    - **Property 14: Validación de la estructura del plan**
    - **Validates: Requirements 6.3, 6.4, 6.5**

  - [ ] 5.10 Implementar `check_dietary_compliance` y `compute_shopping_list` (puras)
    - `check_dietary_compliance(structure, dietary, foods)`: devuelve string de error es en la primera violación (vegetariano→is_meat, vegano→is_animal, sin_gluten→has_gluten, alérgeno por subcadena normalizada) o None
    - `compute_shopping_list(plan_structure, inventory)`: suma requerida por alimento; `available = inventory.get(name, 0)`; incluir `{food_name, grams: max(ceil(missing), 1)}` si `missing > 0`, excluir en otro caso
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 13.1, 13.2, 13.3, 13.5_

  - [ ]* 5.11 Property test de cumplimiento dietético (pura)
    - **Property 18: Cumplimiento de restricciones dietéticas y preservación ante violación**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

  - [ ]* 5.12 Property test de la lista de compras
    - **Property 22: Corrección de la lista de compras**
    - **Validates: Requirements 13.1, 13.2, 13.3, 13.5**

- [ ] 6. MealService — funciones con I/O (catálogo, inventario, dieta)
  - [ ] 6.1 Implementar CRUD de catálogo `Food`
    - `list_foods(db)`, `create_food(db, fields, is_meat, is_animal, has_gluten)`, `update_food(db, food_id, ...)`, `delete_food(db, food_id)`; `validate_food_fields`; nombre único; forzar `is_meat ⇒ is_animal`; preservar el catálogo ante duplicado/inválido
    - _Requirements: 1.3, 1.5, 1.7_

  - [ ] 6.2 Implementar inventario del usuario
    - `add_inventory(db, user_id, food_name, quantity_grams, new_food_fields=None)`: upsert dedup por `(user, food)` actualizando cantidad; crear `Food` si el nombre no existe (con `new_food_fields` validados); validar gramos 1..100000 antes de mutar; preservar estado ante fallo
    - `remove_inventory(db, user_id, food_id)` (conserva el `Food`), `get_inventory(db, user_id)` (nombre + gramos)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 6.3 Property tests de inventario (dedup y rechazo)
    - **Property 4: Inventario deduplicado y con última cantidad**
    - **Property 5: Agregado inválido al inventario es rechazado y el estado se preserva**
    - **Validates: Requirements 2.1, 2.2, 2.4**

  - [ ] 6.4 Implementar perfil dietético
    - `get_dietary(db, user_id)` (ausente → sin flags/alérgenos), `set_dietary(db, user_id, vegetarian, vegan, gluten_free, allergens)`: validar alérgenos 1..50, dedup, reemplazo completo; preservar perfil previo ante inválido
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 6.5 Property tests del perfil dietético
    - **Property 6: Perfil dietético reemplazado por completo y con alérgenos deduplicados**
    - **Property 7: Perfil dietético inválido es rechazado y el perfil previo se preserva**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

- [ ] 7. MealService — metas nutricionales
  - [ ] 7.1 Implementar `get_targets`, `set_manual_targets` y `derive_targets`
    - `get_targets(db, user_id)` devuelve targets o None
    - `set_manual_targets(...)`: `validate_manual_targets`; upsert con `source='manual'` reemplazando cualquier previa
    - `derive_targets(db, user_id)`: `fitness_link.get_fitness_view`; None → `GoalRequiredError` (es); `compute_target_rate_for_view`; `derive_nutrition_targets` (pura); upsert `source='derived'` recalculando en cada llamada
    - _Requirements: 4.1, 4.6, 5.1, 5.3, 5.4, 8.3, 8.5_

  - [ ]* 7.2 Property test de metas manuales válidas
    - **Property 11: Metas manuales válidas se almacenan y reemplazan a las previas**
    - **Validates: Requirements 5.1, 5.3**

  - [ ]* 7.3 Property test de metas manuales inválidas
    - **Property 12: Metas manuales inválidas son rechazadas y las metas previas se preservan**
    - **Validates: Requirements 5.2**

  - [ ]* 7.4 Property test de derivación sin perfil fitness (mock `get_fitness_view` → None)
    - **Property 10: Derivación sin perfil fitness es rechazada y el estado se preserva**
    - **Validates: Requirements 4.6, 8.5**

  - [ ]* 7.5 Property test de recálculo con valores vigentes (mock view A→B)
    - **Property 19: Recálculo de metas derivadas con los valores vigentes**
    - **Validates: Requirements 8.3**

- [ ] 8. LLM_Service — generación del plan de comidas
  - [ ] 8.1 Extender `app/services/llm_service.py` con `MEAL_SYSTEM_PROMPT` y `generate_meal_plan`
    - Añadir `MEAL_SYSTEM_PROMPT` (JSON de 7 días, tipos de comida, gramos 1..100000, priorizar inventario, aproximar kcal/macros, respetar restricciones, totales por día, nombres en español)
    - `generate_meal_plan(prompt, timeout_seconds=60.0) -> dict | None`: patrón de `_call_llm` con `httpx.AsyncClient(timeout=...)`, stripping de fences, `json.loads`, `max_tokens ~2000`; devuelve dict o None ante timeout/error HTTP/vacío/JSONDecodeError
    - _Requirements: 6.1, 9.1, 9.2, 9.3_

- [ ] 9. MealService — generación, plan activo y lista de compras
  - [ ] 9.1 Implementar `build_meal_prompt` y `generate_meal_plan`
    - `build_meal_prompt(inventory, targets, dietary)`: compone el prompt con inventario (nombre+gramos), metas y restricciones, instruyendo priorizar inventario
    - `generate_meal_plan(db, user_id, overrides=None)`: 1) resolver targets (derivar si hay vista y no hay `manual`; overrides de objetivo por Telegram; sin metas → error es); 2) inventario vacío → error es; 3) `get_dietary`; 4) llamar LLM (None/timeout/error/no interpretable → `LLMError`); 5) `validate_plan_structure`; 6) `check_calorie_tolerance` por día → `ToleranceError`; 7) `check_dietary_compliance` → `DietaryError`; 8) ante cualquier fallo NO tocar plan/inventario/dieta/metas previos; en éxito desactivar plan previo e insertar nuevo activo
    - _Requirements: 5.5, 6.1, 6.2, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 7.1, 7.2, 7.3, 7.4, 8.4, 9.1, 9.2, 9.3, 9.4, 9.5, 11.5_

  - [ ] 9.2 Implementar `get_active_plan` y `get_shopping_list`
    - `get_active_plan(db, user_id)` devuelve el plan activo o None
    - `get_shopping_list(db, user_id)`: cargar plan activo (None → `ShoppingRequiresPlanError`); mapa de inventario (cantidad ausente → 0); `compute_shopping_list(...)`
    - _Requirements: 6.12, 6.13, 13.1, 13.4_

  - [ ]* 9.3 Property test de precondiciones ausentes al generar (mock)
    - **Property 13: Rechazo por precondiciones ausentes al generar el plan**
    - **Validates: Requirements 5.5, 6.9, 6.10**

  - [ ]* 9.4 Property test de aceptación por tolerancia y preservación (mock LLM + DB)
    - **Property 16: Aceptación del plan por tolerancia y preservación ante rechazo**
    - **Validates: Requirements 6.8**

  - [ ]* 9.5 Property test de a-lo-más-un-plan-activo (mock LLM + DB)
    - **Property 17: A lo más un Meal_Plan activo por usuario**
    - **Validates: Requirements 6.2, 6.11**

  - [ ]* 9.6 Property test de metas manuales no sobrescritas por la generación (mock LLM)
    - **Property 20: Las metas manuales no son sobrescritas por la generación**
    - **Validates: Requirements 8.4**

  - [ ]* 9.7 Property test de preservación de estado ante cualquier fallo (mock LLM + DB)
    - **Property 21: Preservación del estado ante cualquier fallo de generación**
    - **Validates: Requirements 6.4, 9.1, 9.2, 9.3, 9.4**

- [ ] 10. Endpoints `/api/meals` y registro en la app
  - [ ] 10.1 Crear `app/routes/meals.py` con schemas Pydantic y endpoints
    - Schemas: `FoodIn`/`FoodOut`, `InventoryIn`/`InventoryOut`, `DietaryIn`/`DietaryOut`, `TargetsIn`/`TargetsOut`, `MealPlanOut`, `ShoppingItemOut`
    - Endpoints (todos `Depends(get_current_user)`; `Food` CUD con `Depends(get_current_admin)`): `GET/POST/PUT/DELETE /foods`, `GET/POST /inventory`, `DELETE /inventory/{food_id}`, `GET/PUT /dietary`, `GET/PUT /targets`, `POST /targets/derive`, `POST /plan/generate`, `GET /plan`, `GET /shopping-list`
    - Filtrar datos por `current_user.id` (salvo admin); traducir excepciones del servicio a `HTTPException` con `detail` en español y descargos; adjuntar `MEAL_DISCLAIMER` en `/plan*` y `/targets*`
    - _Requirements: 1.3, 1.5, 1.7, 2.1, 2.5, 2.6, 3.1, 3.5, 3.6, 4.1, 4.7, 5.1, 5.4, 6.8, 6.9, 6.10, 6.12, 6.13, 7.1, 7.2, 7.3, 7.4, 9.1, 9.2, 9.3, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 13.4_

  - [ ] 10.2 Registrar el router en `app/main.py`
    - `from app.routes import meals` e `app.include_router(meals.router, prefix="/api/meals", tags=["Meals"])` sin colisión con `settings_routes`
    - _Requirements: 12.1_

  - [ ]* 10.3 Property test de privacidad de endpoints
    - **Property 23: Privacidad — solo registros propios**
    - **Validates: Requirements 12.3, 12.4**

  - [ ]* 10.4 Property test de descargo en respuestas de plan y metas
    - **Property 24: Descargo en respuestas de plan y metas**
    - **Validates: Requirements 4.7, 12.6**

- [ ] 11. Checkpoint backend
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Tests de ejemplo e integración del backend (opcionales)
  - [ ]* 12.1 Tests de auth y roles admin del catálogo
    - Cada endpoint sin token → 401; con token → 200; `POST/PUT/DELETE /foods` no-admin → 403, admin → 200; `GET /foods` e inventario con cualquier usuario → 200
    - _Requirements: 1.6, 12.1, 12.2, 12.5_

  - [ ]* 12.2 Tests de lecturas CRUD y alta desde inventario
    - `GET /foods` (nombre+nutrición), `GET /inventory` (nombre+gramos), `GET /dietary` sin perfil, `GET /targets` (source), `GET /plan` sin plan (mensaje es), `GET /shopping-list` sin plan (mensaje es); alta de alimento nuevo desde inventario (Food creado + entrada) y `remove_inventory` conserva el Food
    - _Requirements: 1.7, 2.3, 2.5, 2.6, 3.6, 5.4, 6.13, 13.4_

  - [ ]* 12.3 Tests de generación con mock del LLM y mock de fitness_link
    - Mock válido en tolerancia → plan persistido y activo, `build_meal_prompt` contiene inventario+metas+dieta; mocks de timeout/None/JSON inválido/fuera de tolerancia/viola dieta → error es + estado preservado; mock `get_fitness_view` devolviendo vista o None
    - _Requirements: 6.1, 6.6, 9.1, 9.2, 9.3, 9.5_

- [ ] 13. Telegram — intent `meal`
  - [ ] 13.1 Añadir el intent `meal` al `SYSTEM_PROMPT` y `_detect_meal_keywords`
    - En `llm_service.SYSTEM_PROMPT`: rama `intent="meal"` con `data{action:"generate"|"view", foods, goal_type}` y ejemplos
    - `_detect_meal_keywords(text)` en `routes/telegram.py` (patrón de `_detect_goal_keywords`): detecta "plan de comidas", "qué como", "menú", "dame el plan" y listas "tengo ..."
    - _Requirements: 11.2, 11.3, 11.4, 11.5_

  - [ ] 13.2 Implementar `_handle_meal` e integrarlo en el flujo de Telegram
    - En `app/services/telegram_bot.py` y `app/routes/telegram.py::_handle_message`: rama `elif intent == "meal": await _handle_meal(...)`
    - `action=="generate"`: añadir `data.foods` al inventario (creando `Food` si no existe, Req 11.4); si `goal_type` y no hay targets `manual`, `derive_targets` con ese objetivo (Req 11.5); `generate_meal_plan` y responder es con plan + `MEAL_DISCLAIMER`; errores → guía es y reintento
    - `action=="view"`: `get_active_plan`; formatear es o "no tienes un plan activo"; chat no vinculado → pedir vincular
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 9.4_

  - [ ]* 13.3 Tests de integración de Telegram (mock LLM)
    - Chat no vinculado → pedir vincular; vinculado + lista de alimentos → añade al inventario, deriva objetivo y responde es con plan; ver plan; falta metas/inventario → guía es
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [ ] 14. Frontend — API client
  - [ ] 14.1 Añadir `mealsApi` e interfaces TS a `src/lib/api.ts`
    - Interfaces `Food`, `InventoryItem`, `Dietary`, `Targets`, `MealItem`, `Meal`, `DayTotals`, `MealDay`, `MealPlan`, `ShoppingItem`
    - `mealsApi` con métodos para foods/inventory/dietary/targets/plan/shopping-list según el diseño
    - _Requirements: 10.2, 10.4_

- [ ] 15. Frontend — página de Comidas
  - [ ] 15.1 Crear `src/pages/MealsPage.tsx`
    - Secciones: Inventario (catálogo + alta con cantidad/valores/flags), Preferencias/restricciones (checkboxes + chips de alérgenos), Metas (derivar del fitness / manual, muestra `source` y `disclaimer`), Plan (generar/ver 7 días → comidas → ítems + totales), Lista de compras (opcional)
    - Español, Tailwind dark (tokens `card`, `text-primary`, `text-secondary`, `text-dim`, `accent`, `bg-surface`, `bg-elevated`, `bg-border`, `btn-ghost`), estados loading/error, mostrar `detail` es de la API conservando lo ingresado, descargos visibles
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 12.6_

  - [ ]* 15.2 Component tests de `MealsPage`
    - Render de secciones, envío de inventario/dieta/metas, visualización de errores es conservando el formulario, render del plan con descargo y del estado sin plan
    - _Requirements: 10.1, 10.2, 10.3, 10.5, 10.6_

- [ ] 16. Frontend — ruta y navegación
  - [ ] 16.1 Cablear la ruta protegida y el enlace de navbar
    - En `src/main.tsx`: `<Route path="/meals" element={<MealsPage />} />` dentro de `AppLayout`
    - En `src/components/Navbar.tsx`: enlace `{ to: '/meals', icon: '🍽️', label: 'Comidas' }`
    - _Requirements: 10.1_

- [ ] 17. Checkpoint final
  - Ensure all tests pass, ask the user if questions arise. Ejecutar `pytest tests/` y `cd src && npm run build`.

## Notes

- Las subtareas marcadas con `*` son opcionales (tests y la lista de compras Req 13, nice-to-have) y pueden omitirse para un MVP más rápido.
- Cada tarea referencia requisitos específicos; los property tests referencian su propiedad del diseño (etiqueta `# Feature: meal-planner, Property N: ...`, Hypothesis mínimo 100 iteraciones).
- Los property tests validan la corrección universal (validaciones, derivación, reparto 4/4/9, tolerancia, cumplimiento dietético, dedup, invariantes de estado, lista de compras, privacidad); los tests de ejemplo/integración cubren wiring, lecturas simples, roles admin y dependencias externas (LLM y fitness-link con mocks).
- Las funciones puras se implementan y prueban antes de las funciones con I/O para detectar errores temprano.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "4.1"] },
    { "id": 2, "tasks": ["2.1", "3.1", "5.1", "8.1"] },
    { "id": 3, "tasks": ["3.2", "5.2", "5.4", "5.7", "5.10"] },
    { "id": 4, "tasks": ["5.3", "5.5", "5.6", "5.8", "5.9", "5.11", "5.12", "6.1", "6.4"] },
    { "id": 5, "tasks": ["6.2", "7.1"] },
    { "id": 6, "tasks": ["6.3", "6.5", "7.2", "7.3", "7.4", "7.5", "9.1"] },
    { "id": 7, "tasks": ["9.2"] },
    { "id": 8, "tasks": ["9.3", "9.4", "9.5", "9.6", "9.7", "10.1"] },
    { "id": 9, "tasks": ["10.2", "10.3", "10.4"] },
    { "id": 10, "tasks": ["12.1", "12.2", "12.3", "13.1"] },
    { "id": 11, "tasks": ["13.2", "14.1"] },
    { "id": 12, "tasks": ["13.3", "15.1"] },
    { "id": 13, "tasks": ["15.2", "16.1"] }
  ]
}
```
