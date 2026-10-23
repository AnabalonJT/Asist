# Implementation Plan: Food Barcode

## Overview

Plan de implementación incremental para el Food_Barcode (escáner y búsqueda de alimentos tipo MyFitnessPal) sobre la feature meal-planner. El orden va de la extensión mínima del modelo (`Food.barcode`) y su migración, a la capa de servicio (primero la función pura de mapeo, luego las funciones de I/O con httpx), al propagado del `barcode` por el flujo de alta existente, a los endpoints del router `/api/meals`, y por último al frontend (API client, componentes de escáner/búsqueda/confirmación, integración en `MealsPage`). Cada tarea construye sobre la anterior y termina integrándose (migración cableada en `_migrate_columns` + Alembic, endpoints en el router registrado, componentes montados en la página existente). Los property tests (Hypothesis, mínimo 100 iteraciones, etiquetados `# Feature: food-barcode, Property N: ...`) se ubican como subtareas opcionales (`*`) junto a la función pura que validan. Los tests de ejemplo/integración y los component tests del front también son opcionales (`*`). Las llamadas a Open Food Facts se mockean en los tests (no se accede a la red).

## Tasks

- [x] 1. Extender el modelo `Food` con la columna `barcode`
  - [x] 1.1 Añadir la columna `barcode` a `app/models/food.py`
    - Añadir `barcode: Mapped[str | None] = mapped_column(String(14), unique=True, index=True, nullable=True)` a la clase `Food`
    - Comentario en inglés indicando EAN/UPC opcional que permite reconocer un alimento escaneado la próxima vez
    - _Requirements: 1.1, 1.3_

- [x] 2. Migraciones de la columna `barcode`
  - [x] 2.1 Añadir la migración de columna en runtime (`_migrate_columns`)
    - En `app/database.py::_migrate_columns`, añadir a la lista `migrations` la tupla `("foods", "barcode", "VARCHAR(14)", None)` para que las bases ya creadas obtengan la columna (`create_all` no hace `ALTER TABLE`)
    - Crear el índice único de `foods.barcode` de forma idempotente (comprobando `information_schema`/`pg_indexes` antes de `CREATE UNIQUE INDEX`), consistente con el patrón defensivo del archivo
    - _Requirements: 1.1, 1.4, 1.5_

  - [x] 2.2 Crear la migración Alembic `add_food_barcode`
    - Nuevo archivo en `alembic/versions/` con `down_revision = '20260612_100000'`
    - `upgrade`: `op.add_column('foods', sa.Column('barcode', sa.String(length=14), nullable=True))` y `op.create_index(op.f('ix_foods_barcode'), 'foods', ['barcode'], unique=True)`
    - `downgrade`: `op.drop_index(...)` y `op.drop_column('foods', 'barcode')`
    - _Requirements: 1.1_

- [x] 3. Servicio de lookup externo — función pura de mapeo y helpers
  - [x] 3.1 Crear `app/services/food_lookup_service.py` con constantes, excepciones y helpers puros
    - Constantes: `OFF_PRODUCT_URL`, `OFF_SEARCH_URL`, `OFF_PRODUCT_FIELDS`, `OFF_SEARCH_FIELDS`, `LOOKUP_TIMEOUT=10.0`, `USER_AGENT` (descriptivo), `BARCODE_LEN=(8, 14)`
    - Excepciones: `LookupError` (base), `InvalidBarcodeError`, `NotFoundError`, `ExternalSourceError`
    - `normalize_barcode(code) -> str`: recorta espacios al inicio/fin; coacciona no-string a cadena vacía
    - `is_valid_barcode(code) -> bool`: verdadero sii el código normalizado es solo dígitos y su longitud está entre 8 y 14 inclusive
    - `map_off_product(product, fallback_barcode) -> dict` (PURA): mapea `nutriments` por 100 g (`energy-kcal_100g`→kcal, `proteins_100g`→protein, `fat_100g`→fat, `carbohydrates_100g`→carbs, `fiber_100g`→fiber) con `None` para campos ausentes/None; `name` = `product_name` o, si falta/está vacío, `fallback_barcode`; incluir `brand`/`image_url` cuando están presentes; `source="off"`; nunca lanzar excepción; devolver todas las claves de la forma del `Food_Candidate`
    - _Requirements: 1.2, 2.3, 2.5, 2.6, 4.1, 4.2, 4.3, 4.4_

  - [x]* 3.2 Property test del mapeo de nutrientes (presentes vs. ausentes)
    - **Property 1: El mapeo preserva los nutrientes presentes y nulifica los ausentes**
    - **Validates: Requirements 2.3, 2.5, 4.1, 4.2**

  - [x]* 3.3 Property test del fallback de nombre al código de barras
    - **Property 2: El nombre siempre está definido (fallback al código de barras)**
    - **Validates: Requirements 4.3**

  - [x]* 3.4 Property test de robustez y forma completa del candidato
    - **Property 3: El mapeo nunca falla y produce la forma completa del candidato**
    - **Validates: Requirements 2.5, 4.4**

  - [x]* 3.5 Property test del predicado de validez del código de barras
    - **Property 4: La validación del código de barras acepta exactamente los códigos de 8 a 14 dígitos**
    - **Validates: Requirements 1.2, 2.6**

- [x] 4. Servicio de lookup externo — funciones de I/O (httpx)
  - [x] 4.1 Implementar `lookup_barcode` y `search_by_name` con httpx asíncrono
    - `lookup_barcode(code) -> dict`: validar formato (inválido → `InvalidBarcodeError`); `httpx.AsyncClient(timeout=LOOKUP_TIMEOUT, headers={"User-Agent": USER_AGENT})`; GET a `OFF_PRODUCT_URL` con `fields=OFF_PRODUCT_FIELDS`; `status:0` → `NotFoundError`; `status:1` → `map_off_product(product, code)`; `httpx.TimeoutException`/`httpx.HTTPError`/estado HTTP no exitoso → `ExternalSourceError`
    - `search_by_name(query) -> list[dict]`: GET a `OFF_SEARCH_URL` con `search_terms`, `json=1`, `page_size=20`, `fields=OFF_SEARCH_FIELDS`; mapear cada producto con `map_off_product`; ante timeout/error devolver `[]` (best-effort)
    - Enviar siempre el `User-Agent` descriptivo
    - _Requirements: 2.2, 2.3, 2.6, 2.7, 2.8, 3.2, 3.5, 4.5_

  - [x]* 4.2 Tests de ejemplo del servicio con mock de httpx (sin red)
    - `lookup_barcode`: mock `status:1` → candidato mapeado; mock `status:0` → `NotFoundError`; mock timeout/error → `ExternalSourceError`; mock transport asegura el header `User-Agent`
    - `search_by_name`: mock con productos → lista mapeada; mock de fallo → `[]`
    - _Requirements: 2.3, 2.7, 2.8, 3.2, 3.5, 4.5_

- [x] 5. Propagar `barcode` por el flujo de alta existente
  - [x] 5.1 Añadir `barcode` a `FoodIn` y persistirlo en `create_food`/`add_inventory`
    - En `app/routes/meals.py`, añadir `barcode: str | None = None` al schema `FoodIn` (y exponerlo en `FoodOut`)
    - En `app/services/meal_service.py`, propagar `barcode` en `create_food` y en el camino de creación de `Food` dentro de `add_inventory` (vía `new_food_fields`), normalizándolo con `normalize_barcode`
    - Enforzar la unicidad del `barcode`: ante `IntegrityError` por `barcode` duplicado, hacer rollback y lanzar `ValidationError` en español ("Ese código de barras ya está asociado a otro alimento."), preservando el catálogo
    - _Requirements: 1.2, 1.4, 5.2, 5.3, 6.2_

  - [x]* 5.2 Tests de ejemplo de alta con `barcode` (reuso de `add_inventory`)
    - Alta de alimento nuevo con `barcode` → `Food` creado con `barcode` + entrada de inventario; nombre existente → sin duplicado en catálogo; `barcode` duplicado → `ValidationError` es y catálogo preservado; valores fuera de rango → `ValidationError` es
    - _Requirements: 1.4, 5.2, 5.3, 5.4_

- [x] 6. Endpoints de lookup y búsqueda en `/api/meals`
  - [x] 6.1 Añadir `FoodCandidateOut` y los endpoints al router existente
    - En `app/routes/meals.py`, añadir el schema `FoodCandidateOut` (name, barcode?, kcal?, protein?, fat?, carbs?, fiber?, brand?, image_url?, source)
    - `GET /barcode/{code}` (`Depends(get_current_user)`): validar formato (`is_valid_barcode`; inválido → 400 es); buscar `Food` por `barcode` normalizado → `FoodCandidateOut(source="local")` (Req 2.1); si no está, `food_lookup_service.lookup_barcode(code)` traduciendo `NotFoundError`→404 es, `ExternalSourceError`→503 es, éxito→`FoodCandidateOut(source="off")`
    - `GET /food-search` con `q` query param (`Depends(get_current_user)`): validar longitud 1..100 (inválido → 400 es); buscar en catálogo local por nombre → candidatos `source="local"`; si hay <1 resultado local, añadir `food_lookup_service.search_by_name(q)` (best-effort: si falla, devolver solo locales)
    - Todos los `detail` en español según la tabla de Error Handling del diseño
    - _Requirements: 2.1, 2.6, 2.7, 2.8, 3.1, 3.2, 3.4, 3.5, 6.1, 6.3_

  - [x]* 6.2 Tests de integración de los endpoints (mock de Open Food Facts)
    - `/barcode/{code}`: sin token → 401; código inválido → 400 es; hit local → `source="local"` (mock OFF falla si se llama); miss local + mock `status:1` → `source="off"`; mock `status:0` → 404 es; mock timeout/error → 503 es
    - `/food-search`: término inválido → 400 es; con resultados locales → no consulta OFF; sin locales + mock con productos → combina; mock de fallo → solo locales; usuario no admin → 200 (Req 6.1); `POST/PUT/DELETE /foods` no admin → 403 (Req 6.3)
    - _Requirements: 2.1, 2.6, 2.7, 2.8, 3.1, 3.2, 3.4, 3.5, 6.1, 6.3_

- [x] 7. Checkpoint backend
  - Ensure all tests pass, ask the user if questions arise. Ejecutar `pytest tests/`.

- [x] 8. Frontend — API client
  - [x] 8.1 Añadir `FoodCandidate` y métodos a `mealsApi` en `src/lib/api.ts`
    - Interfaz `FoodCandidate` (name, barcode?, kcal?, protein?, fat?, carbs?, fiber?, brand?, image_url?, source)
    - `lookupBarcode(code)` → `GET /meals/barcode/{code}` (con `encodeURIComponent`); `searchFood(q)` → `GET /meals/food-search?q=...` (con `encodeURIComponent`)
    - Extender la interfaz `FoodInput` con `barcode?: string | null` para el alta vía `addInventory({ ..., new_food })`
    - _Requirements: 2.1, 3.1, 5.2_

- [x] 9. Frontend — componentes de escáner, búsqueda y confirmación
  - [x] 9.1 Crear `src/components/BarcodeScanner.tsx`
    - Usar `@zxing/browser` (`BrowserMultiFormatReader`) sobre un `<video>` alimentado por `getUserMedia`; callback `onDetected(code)`
    - Campo de entrada manual (input + botón "Buscar código") que dispara el mismo `onDetected`
    - Manejar `NotAllowedError`/`NotFoundError`/`NotReadableError` de `getUserMedia` mostrando un mensaje en español y dejando visible la entrada manual; liberar el stream de la cámara al desmontar
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 9.2 Crear `src/components/FoodConfirm.tsx` y `FoodSearchBox`
    - `FoodConfirm`: muestra el Confirmation_Step con el texto exacto "¿Es este el alimento que quieres agregar?", nombre, marca e imagen (si hay) y valores nutricionales editables; "Agregar" llama a `mealsApi.addInventory({ food_name, quantity_grams, new_food })`; "Cancelar" descarta sin cambios; muestra el `detail` es de la API ante error de rango conservando el formulario
    - `FoodSearchBox`: input de nombre + botón que llama a `mealsApi.searchFood(q)` y renderiza la lista de `FoodCandidate` seleccionables
    - Español, Tailwind dark (tokens `card`, `text-primary`, `text-secondary`, `accent`, `btn-ghost`), estados loading/error
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 7.5_

  - [x]* 9.3 Component tests de los componentes del front
    - `BarcodeScanner`: `getUserMedia` mockeado concede → vídeo; rechaza → mensaje es + entrada manual; entrada manual envía → `onDetected`
    - `FoodConfirm`: renderiza el texto de confirmación y los valores; "Agregar" llama a `addInventory`; "Cancelar" descarta sin llamar nada; error de rango muestra el `detail` es
    - `FoodSearchBox`: enviar término → `searchFood` llamado, lista renderizada
    - _Requirements: 5.1, 5.5, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 10. Frontend — integración en `MealsPage`
  - [x] 10.1 Montar escáner, búsqueda y confirmación en `src/pages/MealsPage.tsx`
    - Añadir una sección "Agregar alimento (escáner / búsqueda)" junto al Inventario existente
    - Flujo: `BarcodeScanner`/`FoodSearchBox` → `lookupBarcode`/`searchFood` → mostrar `FoodConfirm` con el `Food_Candidate` → al confirmar, `addInventory` y refrescar el inventario; mostrar errores es (404/503/400) sin romper la página
    - _Requirements: 5.1, 5.2, 5.5, 7.1, 7.5_

- [x] 11. Checkpoint final
  - Ensure all tests pass, ask the user if questions arise. Ejecutar `pytest tests/` y `cd src && npm run build`.

## Notes

- Las subtareas marcadas con `*` son opcionales (property tests, tests de ejemplo/integración y component tests) y pueden omitirse para un MVP más rápido.
- Cada tarea referencia requisitos específicos; los property tests referencian su propiedad del diseño (etiqueta `# Feature: food-barcode, Property N: ...`, Hypothesis mínimo 100 iteraciones).
- Los property tests validan la corrección universal de la única pieza pura (mapeo `map_off_product` y el predicado `is_valid_barcode`); los tests de ejemplo/integración cubren el I/O con httpx (mockeado, sin red), los endpoints, la unicidad del código de barras, la separación de privilegios y los componentes del front.
- La función pura (`map_off_product`) se implementa y prueba antes de las funciones con I/O para detectar errores temprano.
- El alta tras confirmar reutiliza el endpoint existente `POST /api/meals/inventory`; no se crean endpoints de escritura nuevos (separación de privilegios: el usuario solo toca su inventario).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "3.1"] },
    { "id": 2, "tasks": ["3.2", "3.3", "3.4", "3.5", "4.1", "5.1"] },
    { "id": 3, "tasks": ["4.2", "5.2", "6.1"] },
    { "id": 4, "tasks": ["6.2", "8.1"] },
    { "id": 5, "tasks": ["9.1", "9.2"] },
    { "id": 6, "tasks": ["9.3", "10.1"] }
  ]
}
```
