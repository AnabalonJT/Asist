# Implementation Plan: Goal Wizard

## Overview

Plan de implementación incremental para el Goal_Wizard de HabitTrack. Se construye de abajo hacia arriba: modelo `DietPhasePlan` → migración → capa de servicio `goal_wizard_service` (funciones puras de fases primero, luego async con DB, reutilizando `fitness_service` y `meal_service`) → endpoints `/api/goal-plan` → cliente API y componente `GoalWizard` del frontend → cableado en `FitnessPage` y navegación. Cada tarea se apoya en las anteriores y termina cableada al sistema (router registrado, componente montado desde el botón "Realizar objetivo"). Los property tests (Hypothesis, mínimo 100 ejemplos) se colocan como subtareas opcionales cerca de la función que validan, siguiendo el "Mapa propiedad → función" del diseño (Propiedades 1–16).

Backend en Python 3.11 (FastAPI async + SQLAlchemy 2.0). Frontend en TypeScript/React 19 + Vite + Tailwind. Ambos definidos explícitamente en el diseño; no se usa pseudocódigo. La feature **reutiliza** símbolos verificados de `fitness_service` (`validate_profile_fields`, `validate_goal_fields`, `compute_target_rate`, `add_weight_entry`, `generate_workout_plan`, `validate_plan_structure`, `get_active_plan`, `EQUIPMENT_CATALOG`, `MEDICAL_DISCLAIMER`) y las funciones puras de `meal_service` (`estimate_maintenance_kcal`, `derive_nutrition_targets`, `validate_manual_targets`, rangos `MANUAL_*`); solo añade la lógica de fases y un `phase_view` enriquecido con datos corporales.

## Tasks

- [x] 1. Modelo de datos y relaciones
  - [x] 1.1 Crear `app/models/diet_phase_plan.py`
    - Modelo `DietPhasePlan` (tabla `diet_phase_plans`): `user_id` FK `users.id` index, `start_weight_kg` Float, `target_weight_kg` Float, `goal_reached` Boolean default False, `phases` Text default `"[]"` (JSON lista de fases), `active` Boolean default True index, `created_at`/`updated_at`
    - Helpers: `phases_list()` (parse JSON string → `list[dict]`, tolerante a error) y `active_phase()` (primera fase con `status == "active"` o None)
    - Relationship `user` con `back_populates="diet_phase_plans"`
    - _Requirements: 11.1, 11.2, 11.4_

  - [x] 1.2 Añadir relationship al modelo `User` y registrar el modelo
    - En `app/models/user.py`: añadir `diet_phase_plans` (cascade all/delete-orphan), con import guardado por `TYPE_CHECKING`
    - En `app/models/__init__.py`: importar `DietPhasePlan` y añadirlo a `__all__`
    - En `app/database.py` `init_db`: añadir `diet_phase_plan` al import de registro de modelos para `create_all`
    - _Requirements: 11.1, 11.4_

  - [x]* 1.3 Property test del round-trip de persistencia del plan de fases
    - **Property 11: Round-trip de persistencia del plan de fases**
    - **Validates: Requirements 7.6, 11.4**

- [x] 2. Migración de base de datos
  - [x] 2.1 Crear migración Alembic para `diet_phase_plans`
    - Añadir archivo en `alembic/versions/` encadenado tras `20260613_100000` (`down_revision = '20260613_100000'`) con `create_table("diet_phase_plans", ...)` e índices en `user_id` y `active`
    - Nota en el archivo: `create_all` en `init_db` actúa como red de seguridad idempotente; `_migrate_columns` solo cubre ALTER TABLE de tablas existentes y no aplica a esta tabla nueva; Alembic es la fuente de verdad versionada para despliegues limpios
    - _Requirements: 11.1, 11.4_

- [x] 3. Capa de servicio: constantes y lógica pura de fases
  - [x] 3.1 Crear `app/services/goal_wizard_service.py` con constantes y excepciones
    - Constantes: `PHASE_MAX_KG=2.5`, `PHASE_MAX_WEEKS=4.0`, `PHASE_TOLERANCE_KG=0.5`, `MIN_PHASE_WEEKS=1.0`, `WIZARD_STEPS`, `DISCLAIMER = fitness_service.MEDICAL_DISCLAIMER`
    - Reutilizar excepciones de `fitness_service` (`ValidationError`, `GoalRequiredError`, `EquipmentError`, `LLMError`) y `meal_service` (`ValidationError`) importándolas; definir `WizardValidationError` solo si hace falta un caso propio
    - _Requirements: 5, 6, 12.5_

  - [x] 3.2 Implementar `is_profile_complete` y `resolve_wizard_step` (puras)
    - `is_profile_complete(profile)`: True si `weight_kg/height_cm/age/level/days_per_week/minutes_per_session` presentes y en rango (apoyarse en `validate_profile_fields`)
    - `resolve_wizard_step(profile, plan, has_routine)`: devuelve el primer paso incompleto en el orden `WIZARD_STEPS`
    - _Requirements: 1.2, 1.5, 1.6_

  - [x]* 3.3 Property test de resolución del paso inicial
    - **Property 1: Resolución del paso inicial del asistente**
    - **Validates: Requirements 1.2, 1.5, 1.6**

  - [x] 3.4 Implementar `split_into_phases` (pura)
    - Divide A→B en fases ordenadas por Phase_Size_Rule (≤2.5 kg o ≤4 semanas, lo que ocurra primero); `start_0 == A`, `start_i == end_{i-1}`, última `end == B`; `weeks = max(|change|/|rate|, MIN_PHASE_WEEKS)` acotada; `|A-B| ≤ 2.5` ⇒ 1 fase a B; primera fase `status="active"`, resto `"pending"`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x]* 3.5 Property test de los invariantes del fraccionamiento en fases
    - **Property 2: Invariantes del fraccionamiento en fases**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

  - [x] 3.6 Implementar `derive_phase_targets` y `maintenance_phase` (puras)
    - `derive_phase_targets(profile, phase)`: construye el `phase_view` (datos corporales + `weight_kg`/`current_weight_kg` = `phase.start_weight`, `target_weight_kg` = `phase.end_weight`), calcula el `target_rate` por fase con `compute_target_rate(start, end, weeks)`, y llama `meal_service.derive_nutrition_targets(phase_view, target_rate)`; rellena `kcal/protein_g/fat_g/carbs_g` en la fase
    - `maintenance_phase(profile, target_weight)`: fase final de mantenimiento en B (dirección mantenimiento), `maintenance=True`, `status="active"`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x]* 3.7 Property test de derivación determinista y poscondición de macros
    - **Property 3: Derivación determinista de metas por fase y poscondición de macros**
    - **Validates: Requirements 6.1, 6.3, 6.4**

  - [x]* 3.8 Property test del ritmo por fase
    - **Property 4: El ritmo de cada fase corresponde a la fase, no al trayecto completo**
    - **Validates: Requirements 6.2**

  - [x] 3.9 Implementar `advance_phase_on_weight` (pura)
    - Alcanzó end±0.5 en dirección ⇒ fase `completed`, activar siguiente `pending`, re-derivar sus metas desde el peso vigente (Req 7.1, 7.2); sobrepaso múltiple ⇒ completar todas las alcanzadas, activar primera `pending` restante (Req 7.4); `elapsed ≥ weeks` sin alcanzar ⇒ extender fase (recalcular `weeks` y metas desde el peso vigente, sin saltar) (Req 7.3); última fase completada ⇒ `maintenance_phase` activa en B y `goal_reached=True` (Req 7.5)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x]* 3.10 Property test del avance de fase al alcanzar el peso de fin
    - **Property 7: Avance de fase al alcanzar el peso de fin**
    - **Validates: Requirements 7.1, 7.2**

  - [x]* 3.11 Property test de la extensión de la fase ante progreso insuficiente
    - **Property 8: Extensión de la fase ante progreso insuficiente**
    - **Validates: Requirements 7.3**

  - [x]* 3.12 Property test del salto múltiple al sobrepasar varias fases
    - **Property 9: Salto múltiple al sobrepasar varias fases**
    - **Validates: Requirements 7.4**

  - [x]* 3.13 Property test de la fase de mantenimiento al completar el trayecto
    - **Property 10: Fase de mantenimiento al completar el trayecto**
    - **Validates: Requirements 7.5**

- [x] 4. Capa de servicio: funciones async con DB
  - [x] 4.1 Implementar `derive_and_persist_plan` y `get_active_phase_plan`
    - `derive_and_persist_plan(db, user_id)`: carga perfil+objetivo (falta → `GoalRequiredError` es); calcula el `target_rate` global con `compute_target_rate`; `split_into_phases`; `derive_phase_targets` por fase; desactiva el plan activo previo; persiste un nuevo `DietPhasePlan` activo
    - `get_active_phase_plan(db, user_id)`: devuelve el `DietPhasePlan` activo o None
    - _Requirements: 5.1, 5.6, 6.1, 6.7, 11.1, 11.2, 11.3_

  - [x]* 4.2 Property test de a lo más un plan de fases activo por usuario
    - **Property 12: A lo más un plan de fases activo por usuario**
    - **Validates: Requirements 5.6, 11.1**

  - [x]* 4.3 Property test de consulta con fases ordenadas por índice
    - **Property 13: Consulta con fases ordenadas por índice**
    - **Validates: Requirements 11.2**

  - [x] 4.4 Implementar `register_weight_and_advance` y `edit_active_phase_targets`
    - `register_weight_and_advance(db, user_id, weight_kg, entry_date)`: reutiliza `fitness_service.add_weight_entry`; calcula las semanas transcurridas de la fase activa; llama `advance_phase_on_weight`; persiste las fases actualizadas; devuelve el plan + descargo
    - `edit_active_phase_targets(db, user_id, kcal, protein_g, fat_g, carbs_g)`: valida con `meal_service.validate_manual_targets`; si es válido persiste las metas en la fase activa
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 10.2, 10.3_

  - [x] 4.5 Implementar `generate_routine` (wrapper de reuso)
    - `generate_routine(db, user_id)`: wrapper delgado sobre `fitness_service.generate_workout_plan(db, user_id)`; ante fallo del LLM, la excepción (`LLMError`) propaga sin tocar el estado para que el router la traduzca a mensaje es con reintento
    - _Requirements: 9.1, 9.3, 9.4, 9.6_

  - [x]* 4.6 Property test de preservación del estado ante fallo de generación de rutina
    - **Property 14: Preservación del estado ante fallo de generación de rutina** (mock del LLM: timeout/error/None/JSON inválido)
    - **Validates: Requirements 9.3, 9.4**

- [x] 5. Endpoints REST `/api/goal-plan`
  - [x] 5.1 Crear `app/routes/goal_plan.py` con schemas Pydantic y endpoints
    - Router con `current_user = Depends(get_current_user)` en todos; filtrado siempre por `current_user.id` salvo admin
    - Schemas: `WizardStateOut`, `ProfileIn/FitnessProfileOut`, `GoalIn/GoalOut` (con `target_rate` + descargo), `EquipmentIn`, `PhasePlanOut` (con descargo), `TrainingDaysIn`, `WorkoutPlanIn/WorkoutPlanOut` (con descargo), `TargetsIn`, `WeightIn`
    - Endpoints: `GET /state`, `PUT /profile`, `PUT /goal`, `PUT /equipment`, `POST /phases/derive`, `GET /phases`, `PUT /training-days`, `POST /routine/generate`, `PUT /routine`, `PUT /phases/active/targets`, `POST /weight`
    - `PUT /goal` incluye el `target_rate` de `compute_target_rate` + descargo (Req 3.4); reutiliza `validate_profile_fields`/`validate_goal_fields`
    - Traducción de excepciones internas a `HTTPException` con `detail` en español (tabla Error Handling): `ValidationError`→400/422, `GoalRequiredError`→400, `EquipmentError`→400, `LLMError`→502/503; plan de fases ausente → 200 con `{message}`
    - _Requirements: 1.2, 1.6, 2.2, 2.3, 3.2, 3.3, 3.4, 4.2, 4.3, 5, 6, 7, 8.2, 8.3, 9.1, 9.3, 9.6, 10.2, 10.3, 10.4, 10.5, 11.1, 11.2, 11.3, 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x] 5.2 Registrar el router en `app/main.py`
    - `from app.routes import goal_plan` e `include_router(goal_plan.router, prefix="/api/goal-plan", tags=["GoalWizard"])`
    - _Requirements: 12.1, 12.2_

  - [x]* 5.3 Property test de la respuesta de dieta (todas las fases + descargo)
    - **Property 5: La respuesta de dieta incluye todas las fases con metas y descargo**
    - **Validates: Requirements 6.7**

  - [x]* 5.4 Property test de la respuesta de objetivo (ritmo + descargo)
    - **Property 6: La respuesta de objetivo incluye el ritmo y el descargo**
    - **Validates: Requirements 3.4**

  - [x]* 5.5 Property test de privacidad (solo registros propios)
    - **Property 15: Privacidad — solo registros propios** (dos usuarios no admin)
    - **Validates: Requirements 12.3, 12.4**

  - [x]* 5.6 Property test del descargo médico en respuestas con metas o rutina
    - **Property 16: Descargo médico en respuestas con metas o rutina**
    - **Validates: Requirements 12.5**

- [x] 6. Checkpoint backend
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Tests de ejemplo e integración del backend
  - [x]* 7.1 Tests de autenticación y wiring por paso
    - Cada endpoint `/api/goal-plan/*` sin token → 401; `PUT /profile|/goal|/equipment|/training-days` aceptan válidos (persisten) y rechazan inválidos (400 es, estado previo intacto); `GET /state` posiciona en el primer paso incompleto; `GET /phases` sin plan → mensaje es
    - _Requirements: 1.3, 1.6, 2.2, 2.3, 3.2, 3.3, 4.2, 4.3, 8.2, 8.3, 11.3, 12.1, 12.2_

  - [x]* 7.2 Tests de generación de rutina con mock del LLM
    - Válido → plan persistido y activo, no excede `days_per_week`; timeout/None/JSON inválido/error → 502 es + perfil/objetivo/plan de fases/rutina previa preservados; reintento sin reingresar datos
    - _Requirements: 9.1, 9.3, 9.5, 9.6_

  - [x]* 7.3 Tests de edición en el resumen
    - `PUT /phases/active/targets` y `PUT /routine` válidos persisten; inválidos → 400 es con estado previo intacto
    - _Requirements: 10.2, 10.3, 10.4, 10.5_

  - [x]* 7.4 Tests de avance de fase vía weigh-in (integración)
    - `POST /weight` que alcanza el end de la fase activa avanza a la siguiente; sobrepaso múltiple; progreso insuficiente extiende; completar la última produce mantenimiento
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 8. Frontend: cliente API
  - [x] 8.1 Añadir `goalPlanApi` e interfaces TS a `src/lib/api.ts`
    - Interfaces: `DietPhase`, `PhasePlan`, `WizardState` (reutilizar `FitnessProfile`, `TargetRate`, `WorkoutPlan`, `WorkoutDay` existentes)
    - `goalPlanApi`: `getState`, `putProfile`, `putGoal`, `putEquipment`, `derivePhases`, `getPhases`, `putTrainingDays`, `generateRoutine`, `putRoutine`, `putActiveTargets`, `postWeight`
    - _Requirements: 1.2, 3.2, 4.2, 6.7, 8.2, 9.1, 10.2, 10.4_

- [x] 9. Frontend: animación del paso de dieta
  - [x] 9.1 Crear `src/components/CookingAnimation.tsx`
    - Animación CSS/SVG de ollas/comida con progreso; detecta `window.matchMedia('(prefers-reduced-motion: reduce)')` y, si está activa, muestra una alternativa estática equivalente sin movimiento
    - _Requirements: 6.5, 6.6_

- [x] 10. Frontend: componente GoalWizard (máquina de estados)
  - [x] 10.1 Crear `src/components/GoalWizard.tsx` con el reducer y los pasos
    - `useReducer` que modela el `WizardState`; al montar llama `getState()` para posicionarse en el primer paso incompleto (reanudación); retroceder no descarta datos capturados
    - Sub-pasos: `ProfileStep`, `GoalStep`, `EquipmentStep` (checkboxes del `EQUIPMENT_CATALOG`), `TrainingDaysStep` (muestran `detail` de error en español y conservan lo ingresado); `DietStep` (dispara `derivePhases`, muestra `CookingAnimation` mientras carga); `RoutineStep` (dispara `generateRoutine`, progreso incremental "Generando rutina... Día 1... Día 2...", botón "Reintentar" en es ante fallo sin perder estado); `SummaryStep` (metas por fase + rutina, edición con `putActiveTargets` y `putRoutine`)
    - Estilo Tailwind dark con los tokens establecidos (`card`, `input`, `btn-primary`, `btn-ghost`, `text-text-primary/secondary/dim`, `accent`, `success`, `font-display`, helper `.display`)
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.3, 3.1, 4.1, 6.5, 6.6, 8.1, 9.2, 9.3, 10.1_

  - [x]* 10.2 Component tests de GoalWizard y sus pasos
    - Botón "Realizar objetivo" presente en FitnessPage; pasos muestran errores en español y conservan datos; `DietStep` anima mientras carga y respeta `prefers-reduced-motion`; `RoutineStep` muestra progreso incremental; `SummaryStep` permite editar
    - _Requirements: 1.1, 1.4, 2.1, 3.1, 4.1, 6.5, 6.6, 9.2, 10.1_

- [x] 11. Frontend: cableado en FitnessPage
  - [x] 11.1 Añadir el botón "Realizar objetivo" en `src/pages/FitnessPage.tsx`
    - Botón prominente en español que abre el `GoalWizard` (modal o vista a pantalla completa); al cerrarse, refresca el estado de la página
    - _Requirements: 1.1_

- [x] 12. Checkpoint final
  - Ensure all tests pass, ask the user if questions arise. Ejecutar `pytest tests/` y `cd src && npm run build`.

## Notes

- Las tareas marcadas con `*` son opcionales (tests) y pueden omitirse para un MVP más rápido; el modelo no las implementa automáticamente.
- Cada tarea referencia requisitos concretos y, cuando aplica, la propiedad del diseño que valida.
- Los property tests usan Hypothesis con mínimo 100 ejemplos (`@settings(max_examples=100)`) y se etiquetan con el comentario `# Feature: goal-wizard, Property N: <texto>`.
- Cada una de las 16 propiedades del diseño se implementa con un único property test, según el "Mapa propiedad → función".
- Los tests de generación de rutina mockean el LLM_Service (no se hace PBT sobre la llamada externa; sí sobre la preservación de estado ante fallo).
- La feature reutiliza `fitness_service` y `meal_service` sin reescribir su lógica; solo añade el plan de fases y el `phase_view` enriquecido.
- Los checkpoints aseguran validación incremental.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.4", "3.6", "3.9"] },
    { "id": 4, "tasks": ["3.3", "3.5", "3.7", "3.8", "3.10", "3.11", "3.12", "3.13"] },
    { "id": 5, "tasks": ["4.1", "4.4", "4.5"] },
    { "id": 6, "tasks": ["4.2", "4.3", "4.6", "5.1"] },
    { "id": 7, "tasks": ["5.2", "5.3", "5.4", "5.5", "5.6"] },
    { "id": 8, "tasks": ["7.1", "7.2", "7.3", "7.4", "8.1"] },
    { "id": 9, "tasks": ["9.1"] },
    { "id": 10, "tasks": ["10.1"] },
    { "id": 11, "tasks": ["10.2", "11.1"] }
  ]
}
```
