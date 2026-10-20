# Implementation Plan: Food Add Redesign

## Overview

El plan implementa el rediseño de "Agregar alimento" en pasos incrementales, reutilizando el meal-planner y food-barcode. Se empieza por el modelo de datos y la migración, luego la lógica pura de nutrición de recetas, después los servicios y endpoints (recetas, inventario de recetas, búsqueda unificada), y finalmente el frontend (panel unificado, búsqueda incremental, formularios y escáner diferidos), cerrando con el cableado en la Meals_Page. Cada paso se integra con los anteriores; no queda código huérfano. El backend es Python (FastAPI async + SQLAlchemy 2.0) y el frontend TypeScript/React 19, conforme al diseño.

## Tasks

- [x] 1. Modelo de datos y migración
  - [x] 1.1 Añadir la columna `brand` a `Food` y crear los modelos `Recipe` y `RecipeIngredient`
    - Añadir `brand: Mapped[str | None]` (String(100), nullable) en `app/models/food.py` conservando las banderas `is_meat`/`is_animal`/`has_gluten`
    - Crear `app/models/recipe.py` (`Recipe`: user_id, name, created_at, relación a ingredientes con cascade) y `app/models/recipe_ingredient.py` (`RecipeIngredient`: recipe_id con ondelete CASCADE, food_id, grams)
    - Exportar `Recipe` y `RecipeIngredient` en `app/models/__init__.py`
    - _Requirements: 1.1, 4.1_

  - [x] 1.2 Extender `UserFoodInventory` para referenciar un Food o una Recipe
    - Hacer `food_id` anulable y añadir `recipe_id` anulable (FK a `recipes`)
    - Añadir `UniqueConstraint(user_id, recipe_id)` y un `CheckConstraint` de exclusividad entre `food_id` y `recipe_id`
    - _Requirements: 5.1_

  - [x] 1.3 Crear la migración Alembic `add_recipes_and_food_brand`
    - Nueva revisión encadenada tras `20260614_100000`: `add_column` foods.brand, `create_table` recipes y recipe_ingredients, columnas/constraints nuevos de user_food_inventory
    - Reflejar el cambio en el "safety net" de `_migrate_columns` en `init_db` siguiendo el estilo de `20260613_100000_add_food_barcode.py`
    - _Requirements: 1.1, 4.1, 5.1_

- [x] 2. Lógica pura de nutrición de recetas
  - [x] 2.1 Implementar `compute_recipe_nutrition` en `app/services/recipe_service.py`
    - Función pura: suma ponderada por 100 g de los aportes de cada ingrediente dividida entre la masa total y normalizada a 100 g; `fiber` es None solo si todos los ingredientes tienen fiber None
    - _Requirements: 4.2_

  - [x]* 2.2 Property test de la nutrición agregada
    - **Feature: food-add-redesign, Property 5: Recipe_Nutrition es la suma ponderada por 100 g e invariante al escalado de gramos**
    - **Validates: Requirements 4.2**

- [x] 3. Servicio y endpoints de recetas
  - [x] 3.1 Implementar el CRUD de recetas en `recipe_service.py`
    - `create_recipe` (valida nombre 1..100, ≥1 ingrediente, gramos 1..100000, Food existente vía `_normalize_name`; `ValidationError` en español), `list_recipes` (con `compute_recipe_nutrition`), `delete_recipe` (scope por user_id; `RecipeNotFoundError`/`ForbiddenRecipeError`)
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6, 8.4_

  - [ ]* 3.2 Property test del viaje de ida y vuelta de recetas
    - **Feature: food-add-redesign, Property 4: Alta y lectura de una Recipe son un viaje de ida y vuelta**
    - **Validates: Requirements 4.1, 4.5**

  - [ ]* 3.3 Property test de recetas inválidas
    - **Feature: food-add-redesign, Property 6: Toda Recipe inválida se rechaza y no se registra**
    - **Validates: Requirements 4.3, 4.4**

  - [ ]* 3.4 Property test de eliminación de receta
    - **Feature: food-add-redesign, Property 9: Eliminar una Recipe preserva los Food referenciados**
    - **Validates: Requirements 4.6**

  - [x] 3.5 Añadir los endpoints de recetas en `app/routes/meals.py`
    - `GET/POST /recipes`, `DELETE /recipes/{recipe_id}` con `get_current_user`; esquemas `RecipeIn`, `RecipeOut`, `RecipeNutritionOut`; traducir excepciones a `HTTPException` en español
    - _Requirements: 4.1, 4.5, 4.6, 8.1, 8.4, 8.5_

- [x] 4. Inventario de recetas
  - [x] 4.1 Implementar `add_recipe_to_inventory` en `recipe_service.py`
    - Valida gramos 1..100000 (reusa `INVENTORY_GRAMS_RANGE`), verifica propiedad de la Recipe, deduplica por (user_id, recipe_id) actualizando la cantidad
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 4.2 Añadir el endpoint `POST /inventory/recipe`
    - Esquema `InventoryRecipeIn`; `get_current_user`; excepciones a español (404 para receta ajena/inexistente)
    - _Requirements: 5.1, 5.4, 8.1, 8.5_

  - [ ]* 4.3 Property test de dedup y validación de gramos al agregar receta
    - **Feature: food-add-redesign, Property 7: Agregar una Recipe al inventario deduplica y valida los gramos**
    - **Validates: Requirements 5.2, 5.3**

- [x] 5. Checkpoint — Asegurar que todas las pruebas pasan
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Búsqueda incremental unificada
  - [x] 6.1 Implementar `unified_search` en `app/services/search_service.py`
    - Valida término 1..100 (`ValidationError` en español); busca catálogo (ilike), inventario del usuario y recetas del usuario; mapea cada uno a un dict Search_Result con `kind`, nombre, `brand`, macros y, para recetas, `compute_recipe_nutrition`; scope por user_id
    - _Requirements: 2.1, 2.3, 2.5, 2.7, 8.1_

  - [x] 6.2 Añadir el respaldo best-effort a Open Food Facts
    - Cuando no hay resultados locales, invocar `food_lookup_service.search_by_name` y añadir resultados con `kind="off"`; nunca propagar error externo
    - _Requirements: 2.2, 2.6_

  - [x] 6.3 Añadir el endpoint `GET /search?q=` con `SearchResultOut`
    - `get_current_user`; traducir `ValidationError` a 400 en español
    - _Requirements: 2.1, 2.3, 2.5, 8.1, 8.5_

  - [ ]* 6.4 Property test del subconjunto de búsqueda
    - **Feature: food-add-redesign, Property 3: La búsqueda incremental solo devuelve resultados locales que coinciden y de orígenes permitidos**
    - **Validates: Requirements 2.1**

  - [ ]* 6.5 Property test de serialización de Search_Result
    - **Feature: food-add-redesign, Property 2: La serialización de un Search_Result conserva los campos presentes**
    - **Validates: Requirements 1.5, 2.3**

  - [ ]* 6.6 Tests de integración del respaldo a Open Food Facts (mock)
    - Sin resultados locales invoca el fallback; con locales no lo invoca; un fallo del fallback devuelve solo locales sin excepción
    - _Requirements: 2.2, 2.6_

- [x] 7. Marca (brand) en el alta de alimentos
  - [x] 7.1 Aceptar y validar `brand` en el alta de Food
    - Añadir `brand` a `FoodIn`; validar longitud ≤100 en `create_food`/`add_inventory` (`ValidationError` en español); persistir en `Food.brand`; incluir `brand` en `FoodOut` y en los Search_Result
    - _Requirements: 1.2, 1.3, 1.4, 1.5_

  - [ ]* 7.2 Property test de rechazo de entradas inválidas
    - **Feature: food-add-redesign, Property 1: Toda entrada inválida se rechaza y preserva el estado**
    - **Validates: Requirements 1.4, 2.5, 3.4**

  - [ ]* 7.3 Property test de privacidad
    - **Feature: food-add-redesign, Property 8: El inventario y las recetas se limitan a su dueño**
    - **Validates: Requirements 2.7, 5.4, 8.4**

- [x] 8. Checkpoint — Asegurar que todas las pruebas pasan
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Cliente API del frontend
  - [x] 9.1 Extender `src/lib/api.ts`
    - Añadir las interfaces `SearchResult` y `Recipe`; `brand` en `Food`/`FoodInput`; métodos `search`, `listRecipes`, `createRecipe`, `deleteRecipe`, `addRecipeToInventory`
    - _Requirements: 1.5, 2.1, 4.1, 4.5, 4.6, 5.1_

- [x] 10. Componentes de búsqueda y recetas
  - [x] 10.1 Crear `IncrementalSearchBox.tsx` con debounce
    - Input con retardo de 300 ms (setTimeout + cleanup); llama a `mealsApi.search`; renderiza los Search_Result; estado vacío con mensaje en español que ofrece crear nuevo
    - _Requirements: 2.4, 7.6_

  - [ ]* 10.2 Tests de ejemplo del debounce y estado vacío
    - Temporizadores falsos: varias pulsaciones en <300 ms producen una sola solicitud; sin resultados muestra el aviso de crear nuevo
    - _Requirements: 2.4, 7.6_

  - [x] 10.3 Crear `CreateRecipeForm.tsx` (lazy)
    - Selección de ingredientes (Food) con gramos; muestra la nutrición agregada estimada; envía a `createRecipe`; muestra errores en español
    - _Requirements: 4.1, 4.3_

- [x] 11. Escáner de carga diferida y panel unificado
  - [x] 11.1 Crear `AddFoodPanel.tsx` con pestañas y carga diferida
    - Pestañas: escanear, buscar, inventario, recetas, crear nuevo; `React.lazy` + `Suspense` para `BarcodeScanner`, `CreateFoodForm` y `CreateRecipeForm` con fallback en español; respeta `prefers-reduced-motion`; muestra solo la pestaña activa (sin listas completas)
    - _Requirements: 3.1, 6.1, 6.2, 6.3, 7.1, 7.2, 7.5_

  - [x] 11.2 Conectar la selección de resultados al flujo de confirmación/alta
    - Resultado `catalog`/`inventory`/`off` → `FoodConfirm`; resultado `recipe` → agregar al inventario como unidad; barcode decodificado/manual → `lookupBarcode`
    - _Requirements: 6.4, 7.3, 7.4_

  - [ ]* 11.3 Tests de ejemplo de carga diferida y limpieza de cámara
    - Al montar la página no se monta el escáner ni se llama a `getUserMedia`; al activar escanear se monta tras el import; al cerrar se detiene la cámara (mock de `MediaStream`)
    - _Requirements: 6.1, 6.2, 6.5_

- [x] 12. Integrar el Add_Food_Panel en la Meals_Page
  - [x] 12.1 Reemplazar la sección "Agregar alimento" y las listas completas en `MealsPage.tsx`
    - Montar `AddFoodPanel`; eliminar la lista completa del catálogo/despensa y el formulario de inventario siempre visible del flujo de alta; conservar las secciones de preferencias, metas y plan
    - _Requirements: 7.1, 7.2_

  - [ ]* 12.2 Tests de ejemplo del panel unificado
    - Las cinco acciones se renderizan en español; seleccionar una acción oculta las demás y las listas completas; `prefers-reduced-motion` desactiva las animaciones de movimiento
    - _Requirements: 7.1, 7.2, 7.5_

- [x] 13. Checkpoint final — Asegurar que todas las pruebas pasan
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Las tareas marcadas con `*` son opcionales (tests) y pueden omitirse para un MVP más rápido.
- Cada tarea referencia requisitos específicos para trazabilidad.
- Los property tests validan las propiedades universales del diseño con Hypothesis (≥100 iteraciones); los tests de ejemplo validan casos concretos, ramas externas (mock de Open Food Facts) y la interacción de UI.
- Las banderas dietéticas `is_meat`/`is_animal`/`has_gluten` se conservan sin cambios en todas las tareas que tocan `Food`.
- Reutilización: `validate_food_fields`, `create_food`, `add_inventory`, `_normalize_name`, `food_lookup_service` y el componente `BarcodeScanner` no se reimplementan.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["1.3", "2.2", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "4.1"] },
    { "id": 4, "tasks": ["3.5", "4.2", "4.3"] },
    { "id": 5, "tasks": ["6.1", "7.1"] },
    { "id": 6, "tasks": ["6.2", "7.2", "7.3"] },
    { "id": 7, "tasks": ["6.3", "6.4", "6.5", "6.6"] },
    { "id": 8, "tasks": ["9.1"] },
    { "id": 9, "tasks": ["10.1", "10.3"] },
    { "id": 10, "tasks": ["10.2", "11.1"] },
    { "id": 11, "tasks": ["11.2", "11.3"] },
    { "id": 12, "tasks": ["12.1"] },
    { "id": 13, "tasks": ["12.2"] }
  ]
}
```


## Estado de cierre

El feature está **implementado, verificado y desplegado** en Fly.io (commit en `Develop`).
Todas las tareas obligatorias están completas; la suite pasa (150 tests) y el frontend
compila con la cámara en un chunk diferido aparte.

Tests opcionales (`*`): se completó **2.2** (nutrición de recetas, función pura).
Los demás quedaron **omitidos intencionalmente** porque requieren infraestructura de
pruebas que el repositorio no tiene todavía y cuyo montaje excede el alcance de estos
tests opcionales:

- **3.2, 3.3, 3.4, 4.3, 6.4, 7.2, 7.3** — necesitan una sesión async contra una base de
  datos de prueba (no existe `conftest.py` ni fixture de DB async en el repo).
- **6.6** — test de integración con `food_lookup_service` mockeado (depende del harness
  async anterior).
- **10.2, 11.3, 12.2** — tests de frontend que requieren Vitest + React Testing Library
  (no instalados ni configurados en el proyecto).

Si en el futuro se desea esta cobertura, montar primero los dos harnesses (DB async de
prueba y Vitest/RTL) como una tarea dedicada y luego implementar estos tests.
