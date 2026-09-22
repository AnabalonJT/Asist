# Implementation Plan: Fitness Coach

## Overview

Plan de implementación incremental para el Fitness_Coach de HabitTrack. Se construye de abajo hacia arriba: modelos SQLAlchemy → migración → capa de servicio (funciones puras primero, luego async con DB) → integración LLM → endpoints FastAPI → Telegram → frontend. Cada tarea se apoya en las anteriores y termina cableada al sistema (routers registrados, rutas y navegación conectadas). Los property tests (Hypothesis, mínimo 100 ejemplos) se colocan como subtareas opcionales cerca de la función que validan, siguiendo el "Mapa propiedad → función" del diseño (Propiedades 1–23).

Backend en Python 3.11 (FastAPI async + SQLAlchemy 2.0). Frontend en TypeScript/React. Ambos definidos explícitamente en el diseño; no se usa pseudocódigo.

## Tasks

- [ ] 1. Modelos de datos y relaciones
  - [ ] 1.1 Crear `app/models/fitness_profile.py`
    - Modelo `FitnessProfile` (tabla `fitness_profiles`) con relación 1:1 vía `user_id` FK `users.id` `unique=True, index=True`
    - Columnas: `weight_kg` Float, `height_cm` Float, `age` Integer, `sex` String(10) nullable, `level` String(20), `equipment` String(300) default `"[]"`, `days_per_week` Integer, `minutes_per_session` Integer, `goal_type` String(20) nullable, `target_weight_kg` Float nullable, `target_date` String(20) nullable, `performance_target` String(200) nullable, `created_at`/`updated_at`
    - Helpers: `equipment_list()` (parse JSON string → `list[str]`, tolerante a error) y `meal_planner_view()` (dict con `current_weight_kg`, `target_weight_kg`, `target_date`, `level`, `goal_type`)
    - Relationship `user` con `back_populates="fitness_profile"`
    - _Requirements: 1.1, 1.2, 1.4, 1.9_

  - [ ]* 1.2 Property test para `meal_planner_view`
    - **Property 3: Vista de perfil para Meal_Planner**
    - **Validates: Requirements 1.9**

  - [ ] 1.3 Crear `app/models/weight_entry.py`
    - Modelo `WeightEntry` (tabla `weight_entries`): `user_id` FK index, `weight_kg` Float, `entry_date` String(20) index (ISO "YYYY-MM-DD"), `created_at`
    - Relationship `user` con `back_populates="weight_entries"`
    - _Requirements: 7.1_

  - [ ] 1.4 Crear `app/models/workout_plan.py`
    - Modelo `WorkoutPlan` (tabla `workout_plans`): `user_id` FK index, `goal_type` String(20), `structure` Text (JSON días/ejercicios), `active` Boolean default True index, `created_at`
    - Helper `structure_list()` (parse JSON → `list[dict]`, tolerante a error)
    - Relationship `user` con `back_populates="workout_plans"`
    - _Requirements: 5.2, 5.3, 5.8_

  - [ ] 1.5 Añadir relationships al modelo `User` y registrar modelos nuevos
    - En `app/models/user.py`: añadir `fitness_profile` (uselist=False, cascade all/delete-orphan), `weight_entries` y `workout_plans` (cascade all/delete-orphan), con imports guardados por `TYPE_CHECKING`
    - En `app/models/__init__.py`: importar `FitnessProfile`, `WeightEntry`, `WorkoutPlan` y añadirlos a `__all__`
    - En `app/database.py` `init_db`: añadir `fitness_profile, weight_entry, workout_plan` al import de registro de modelos
    - _Requirements: 1.1, 7.1, 5.8_

- [ ] 2. Migración de base de datos
  - [ ] 2.1 Crear migración Alembic para las tres tablas nuevas
    - Añadir un archivo de migración en `alembic/versions/` (siguiendo el naming del proyecto) que haga `create_table` de `fitness_profiles`, `weight_entries`, `workout_plans`
    - Incluir índice único en `fitness_profiles.user_id` e índices en `weight_entries.user_id`, `weight_entries.entry_date`, `workout_plans.user_id`, `workout_plans.active`
    - Nota en el archivo: `create_all` en `init_db` actúa como red de seguridad idempotente; Alembic es la fuente de verdad versionada para despliegues limpios
    - _Requirements: 1.1, 5.8, 7.1_

- [ ] 3. Capa de servicio: constantes, excepciones y funciones puras
  - [ ] 3.1 Crear `app/services/fitness_service.py` con constantes y excepciones
    - Constantes: `EQUIPMENT_CATALOG`, `EXERCISE_EQUIPMENT`, `VALID_LEVELS`, `VALID_SEX`, `VALID_GOAL_TYPES`, `KCAL_PER_KG=7700.0`, `ACTIVITY_WINDOW_DAYS=28`, `MEDICAL_DISCLAIMER` (en español)
    - Excepciones internas: `ValidationError`, `EquipmentError`, `GoalRequiredError`, `LLMError` (con `kind`: "timeout"|"error"|"parse")
    - _Requirements: 3.5, 5.4, 11.5_

  - [ ] 3.2 Implementar `validate_profile_fields`
    - Valida peso 30–300, altura 100–250, edad 13–100, días 1–7, minutos 10–240, nivel ∈ VALID_LEVELS, sexo ∈ VALID_SEX o None, equipo ⊆ EQUIPMENT_CATALOG
    - Lanza `ValidationError` con mensaje en español que identifica el campo inválido y su rango
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ]* 3.3 Property test de perfil válido
    - **Property 1: Perfil válido es aceptado**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

  - [ ]* 3.4 Property test de perfil inválido
    - **Property 2: Perfil inválido es rechazado y el estado previo se preserva**
    - **Validates: Requirements 1.5, 1.6, 1.7**

  - [ ] 3.5 Implementar `validate_goal_fields`
    - Valida `goal_type` ∈ VALID_GOAL_TYPES; si `weight_target`: peso objetivo 30–300 y fecha objetivo > hoy; si `performance`: descripción longitud 1–200
    - Lanza `ValidationError` con mensaje en español que identifica el campo inválido o faltante
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 3.6 Property test de objetivo válido
    - **Property 4: Objetivo válido es aceptado**
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [ ]* 3.7 Property test de objetivo inválido
    - **Property 5: Objetivo inválido es rechazado y el objetivo previo se preserva**
    - **Validates: Requirements 2.4, 2.5, 2.6**

  - [ ] 3.8 Implementar `compute_target_rate` (pura, sin I/O)
    - Calcula `rate_kg_per_week = round((target-current)/weeks, 2)`, `daily_kcal_delta = round(abs(rate)*7700/7)`, `direction`, `warning` (|rate| > 1.0 kg/sem O > 1.0% del peso actual/sem), `warning_message` (es, sugiere ampliar plazo), `disclaimer=MEDICAL_DISCLAIMER`
    - Lanza `ValidationError` si `weeks < 1`, `weeks == 0`, o falta peso actual/objetivo
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 3.9 Property test del cálculo de ritmo y forma de salida
    - **Property 7: Cálculo correcto del Target_Rate y forma de salida**
    - **Validates: Requirements 3.1, 3.2, 3.5, 3.6**

  - [ ]* 3.10 Property test del umbral de advertencia
    - **Property 8: Umbral de advertencia de ritmo saludable**
    - **Validates: Requirements 3.3**

  - [ ]* 3.11 Property test de entradas inválidas del cálculo de ritmo
    - **Property 9: Entradas inválidas del cálculo de ritmo señalan error**
    - **Validates: Requirements 3.4**

  - [ ] 3.12 Implementar validación de plan pura: `validate_plan_structure`, `required_equipment`, `validate_plan_equipment`, `clamp_days_to_availability`
    - `validate_plan_structure`: 1–7 días, cada día 1–20 ejercicios, nombre 1–100, sets 1–20 con reps 1–100 XOR duration 1–7200 s, rest 0–3600 s → `ValidationError`
    - `required_equipment`: keyword de equipo por ejercicio (default "peso corporal")
    - `validate_plan_equipment`: `EquipmentError` (es, ofrece reintentar) si algún equipo requerido no está disponible
    - `clamp_days_to_availability`: recorta a `min(len(days), days_per_week)`
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 3.13 Property test de validación de estructura del plan
    - **Property 11: Validación de la estructura del plan**
    - **Validates: Requirements 5.2, 5.3**

  - [ ]* 3.14 Property test de validación del equipo del plan
    - **Property 12: Validación del equipo del plan**
    - **Validates: Requirements 5.4, 5.5**

  - [ ]* 3.15 Property test del ajuste de días a la disponibilidad
    - **Property 13: Ajuste de días a la disponibilidad**
    - **Validates: Requirements 5.6**

- [ ] 4. Capa de servicio: funciones async con DB
  - [ ] 4.1 Implementar `build_activity_summary`
    - Sobre la ventana de 28 días: `frequency` = nº de Activity, `total_minutes` = suma de duración (duración ausente = 0 min pero cuenta en frecuencia/tipos), `types` = tipos distintos; sin registros → ceros y lista vacía
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 4.2 Property test de agregación y ventana del Activity_Summary
    - **Property 10: Agregación y ventana del Activity_Summary**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

  - [ ] 4.3 Implementar `add_weight_entry` y `list_weight_entries`
    - `add_weight_entry`: valida 30–300 (`ValidationError` con rango en es), crea `WeightEntry`; si es la fecha más reciente del usuario, actualiza `FitnessProfile.weight_kg`
    - `list_weight_entries`: devuelve entradas ordenadas ascendente por `entry_date`; lista vacía si no hay
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 4.4 Property test del rango de peso registrado
    - **Property 16: Validación del rango de peso registrado**
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 4.5 Property test del peso más reciente actualiza el perfil
    - **Property 17: El peso más reciente actualiza el perfil**
    - **Validates: Requirements 7.3**

  - [ ] 4.6 Implementar `get_progress` y `compute_adherence`
    - `get_progress`: `{'series': [{'date','weight_kg'}...] asc, 'target_weight_kg': float|None}` (peso objetivo solo si `goal_type == weight_target`)
    - `compute_adherence`: sin plan activo o sesiones planificadas 0 → `{'available': False, 'message': <es>}` (sin ÷0); si no → `{'available': True, 'completed', 'planned', 'ratio': round(completed/planned, 2)}` con Activity dentro del periodo del plan
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 4.7 Property test de ordenamiento cronológico de historial y progreso
    - **Property 18: Ordenamiento cronológico ascendente del historial y del progreso**
    - **Validates: Requirements 7.4, 7.5, 8.1**

  - [ ]* 4.8 Property test de peso objetivo solo para weight_target
    - **Property 19: Peso objetivo incluido en el progreso solo para weight_target**
    - **Validates: Requirements 8.2**

  - [ ]* 4.9 Property test de relación de adherencia correcta
    - **Property 20: Relación de adherencia correcta**
    - **Validates: Requirements 8.3, 8.4**

  - [ ]* 4.10 Property test de adherencia sin división por cero
    - **Property 21: Adherencia sin división por cero**
    - **Validates: Requirements 8.5**

- [ ] 5. Integración LLM para rutinas
  - [ ] 5.1 Extender `app/services/llm_service.py` con generación de rutina
    - Añadir `WORKOUT_SYSTEM_PROMPT` (JSON de días/ejercicios, reglas de equipo/nivel/objetivo)
    - Añadir `async generate_workout_plan(profile, goal, activity_summary, timeout_seconds=60.0)`: construye prompt, llama OpenRouter con timeout 60s, hace strip de fences, `json.loads`; devuelve dict o `None` ante timeout/error HTTP/vacío/JSONDecodeError; `max_tokens` mayor (~1200)
    - No modificar `SYSTEM_PROMPT` salvo por el intent `fitness` (tarea 8)
    - _Requirements: 5.1, 6.1, 6.2, 6.3_

- [ ] 6. Capa de servicio: generación de rutina y consulta de plan activo
  - [ ] 6.1 Implementar `generate_workout_plan` y `get_active_plan` en `fitness_service.py`
    - `generate_workout_plan(db, user_id, overrides=None)`: carga perfil+objetivo (falta → `GoalRequiredError` es); aplica overrides (goal_type/equipment/days_per_week); construye Activity_Summary; llama `llm_service.generate_workout_plan` (timeout 60s); parse → `validate_plan_structure` → `clamp_days_to_availability` → `validate_plan_equipment`; ante cualquier fallo LLM/parse/equipo lanza el error en es correspondiente SIN tocar el plan previo; en éxito desactiva plan previo, persiste nuevo plan activo y lo devuelve
    - `get_active_plan(db, user_id)`: devuelve el `WorkoutPlan` activo o None
    - _Requirements: 5.1, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 6.1, 6.2, 6.3, 6.4, 6.5, 10.4, 10.5_

  - [ ]* 6.2 Property test de a lo más un plan activo por usuario
    - **Property 14: A lo más un Workout_Plan activo por usuario** (mock del LLM devolviendo rutina válida)
    - **Validates: Requirements 5.8**

  - [ ]* 6.3 Property test de preservación del estado ante fallo
    - **Property 15: Preservación del estado ante fallo de generación** (mock del LLM: timeout/error/None/JSON inválido/equipo no disponible)
    - **Validates: Requirements 5.5, 6.1, 6.2, 6.3, 6.4**

- [ ] 7. Endpoints REST `/api/fitness`
  - [ ] 7.1 Crear `app/routes/fitness.py` con schemas Pydantic y endpoints
    - Router con `current_user = Depends(get_current_user)` en todos; filtrado siempre por `current_user.id` salvo admin
    - Schemas: `ProfileIn/FitnessProfileOut`, `GoalIn/GoalOut` (con `target_rate?` + descargo), `WeightIn/WeightEntryOut`, `PlanGenerateIn`, `WorkoutPlanOut` (con descargo), `ProgressOut`, `AdherenceOut`
    - Endpoints: `GET/PUT /profile`, `PUT /goal`, `POST/GET /weight`, `POST /plan/generate`, `GET /plan`, `GET /progress`, `GET /adherence`
    - Traducción de excepciones internas a `HTTPException` con `detail` en español (ver tabla Error Handling del diseño): `ValidationError`→400/422, `GoalRequiredError`→400, `EquipmentError`→400, `LLMError`→502/503; adherencia no calculable → 200 con `available:false`
    - _Requirements: 1.1–1.9, 2.1–2.7, 3.1–3.6, 5.1–5.10, 6.1–6.5, 7.1–7.5, 8.1–8.5, 11.1–11.5_

  - [ ] 7.2 Registrar el router en `app/main.py`
    - `from app.routes import fitness` e `include_router(fitness.router, prefix="/api/fitness", tags=["Fitness"])` sin colisión de nombres (patrón `settings_routes`)
    - _Requirements: 11.1, 11.2_

  - [ ]* 7.3 Property test de privacidad (solo registros propios)
    - **Property 22: Privacidad — solo registros propios** (dos usuarios no admin; cada consulta devuelve solo lo propio, acceso ajeno rechazado)
    - **Validates: Requirements 11.3, 11.4**

  - [ ]* 7.4 Property test del descargo médico
    - **Property 23: Descargo médico en respuestas de rutina y objetivo de peso** (respuestas de `/plan` y `/goal` weight_target incluyen descargo no vacío)
    - **Validates: Requirements 11.5**

  - [ ]* 7.5 Property test del invariante de un solo objetivo activo (endpoint `PUT /goal`)
    - **Property 6: A lo más un objetivo activo por usuario**
    - **Validates: Requirements 2.7**

- [ ] 8. Checkpoint backend
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Tests de ejemplo e integración del backend
  - [ ]* 9.1 Tests de autenticación por endpoint
    - Cada endpoint `/api/fitness/*` sin token → 401; con token válido → 200
    - _Requirements: 11.1, 11.2_

  - [ ]* 9.2 Tests de lecturas CRUD y sexo
    - `GET /profile` devuelve todos los campos; `GET /plan` sin plan → mensaje es, con plan → estructura; sexo male/female/other/None aceptados, inválido rechazado
    - _Requirements: 1.4, 1.8, 5.9, 5.10_

  - [ ]* 9.3 Tests de generación con mock del LLM
    - Válido → plan persistido y activo; timeout/None/JSON inválido/error → error es + `FitnessProfile`, `FitnessGoal` y plan activo previo preservados
    - _Requirements: 5.1, 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 10. Interfaz de Telegram (intent `fitness`)
  - [ ] 10.1 Añadir intent `fitness` al `SYSTEM_PROMPT` y detección por keywords
    - En `llm_service.SYSTEM_PROMPT`: rama `intent="fitness"` con `data.action` ("generate"|"view"), `goal_type`, `equipment`, `days_per_week`
    - Añadir `_detect_fitness_keywords(text)` (patrón de `_detect_goal_keywords`) para "rutina", "entrenamiento", "plan de gym"
    - _Requirements: 10.2, 10.3, 10.4, 10.5_

  - [ ] 10.2 Añadir rama `_handle_fitness` en `app/services/telegram_bot.py`
    - Nueva rama `elif intent == "fitness"` en el handler; `action=="generate"` construye overrides desde el mensaje o usa el perfil y llama `fitness_service.generate_workout_plan`, responde en es con rutina + descargo; `action=="view"` usa `get_active_plan`; errores (perfil incompleto, fallo LLM, equipo inválido) → mensaje es con opción de reintentar; chat no vinculado ya se ignora/pide vincular
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ] 10.3 Añadir rama `_handle_fitness` en `app/routes/telegram.py`
    - Integrar fitness en `_handle_message` (webhook): rama `elif intent == "fitness"`, fallback `_detect_fitness_keywords`, `_handle_fitness` gemelo del de polling; chat no vinculado responde en es pidiendo vincular
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 11. Frontend: cliente API
  - [ ] 11.1 Añadir `fitnessApi` e interfaces TS a `src/lib/api.ts`
    - Interfaces: `FitnessProfile`, `TargetRate`, `WorkoutExercise`, `WorkoutDay`, `WorkoutPlan`, `WeightEntry`, `Progress`, `Adherence`
    - `fitnessApi`: `getProfile`, `putProfile`, `putGoal`, `postWeight`, `getWeight`, `generatePlan`, `getPlan`, `getProgress`, `getAdherence`
    - _Requirements: 9.2, 9.4, 9.7_

- [ ] 12. Frontend: gráfico de peso
  - [ ] 12.1 Crear `src/components/WeightChart.tsx` (SVG puro)
    - Recibe `series` y `targetWeight?`; calcula min/max; dibuja `<polyline>` + puntos + línea horizontal punteada de objetivo; sin librerías externas
    - _Requirements: 9.6_

- [ ] 13. Frontend: página Fitness
  - [ ] 13.1 Crear `src/pages/FitnessPage.tsx`
    - Secciones en español, Tailwind dark (tokens `card`, `text-primary/secondary/dim`, `accent`, `bg-surface/elevated/border`, `btn-ghost`): (1) Perfil con checkboxes de equipo del catálogo, (2) Objetivo con `target_rate` + `warning_message` + `disclaimer`, (3) Rutina (generar/ver, loading/error, descargo), (4) Peso + `WeightChart`, (5) Adherencia
    - Muestra el `detail` de error en español devuelto por la API y conserva los datos ingresados
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 3.3, 3.5_

  - [ ]* 13.2 Component tests de FitnessPage y WeightChart
    - Envío de perfil/objetivo/peso, visualización de errores en español, estados loading; render SVG de `WeightChart`
    - _Requirements: 9.1, 9.3, 9.6_

- [ ] 14. Frontend: enrutamiento y navegación
  - [ ] 14.1 Registrar ruta y tab de navegación
    - En `src/main.tsx`: ruta protegida `<Route path="/fitness" element={<FitnessPage />} />` dentro de `AppLayout`
    - En `src/components/Navbar.tsx`: enlace `{ to: '/fitness', icon: '🏋️', label: 'Fitness' }`
    - _Requirements: 9.1_

- [ ] 15. Checkpoint final
  - Ensure all tests pass, ask the user if questions arise. Ejecutar `pytest tests/` y `cd src && npm run build`.

## Notes

- Las tareas marcadas con `*` son opcionales (tests) y pueden omitirse para un MVP más rápido; el modelo no las implementa automáticamente.
- Cada tarea referencia requisitos concretos y, cuando aplica, la propiedad del diseño que valida.
- Los property tests usan Hypothesis con mínimo 100 ejemplos (`@settings(max_examples=100)`) y se etiquetan con el comentario `# Feature: fitness-coach, Property N: <texto>`.
- Cada una de las 23 propiedades del diseño se implementa con un único property test, según el "Mapa propiedad → función".
- Los tests de generación de rutina mockean el LLM_Service (no se hace PBT sobre la llamada externa; sí sobre la validación de la estructura devuelta).
- Los checkpoints aseguran validación incremental.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "1.4"] },
    { "id": 1, "tasks": ["1.2", "1.5"] },
    { "id": 2, "tasks": ["2.1", "3.1", "5.1"] },
    { "id": 3, "tasks": ["3.2"] },
    { "id": 4, "tasks": ["3.3", "3.4", "3.5"] },
    { "id": 5, "tasks": ["3.6", "3.7", "3.8"] },
    { "id": 6, "tasks": ["3.9", "3.10", "3.11", "3.12"] },
    { "id": 7, "tasks": ["3.13", "3.14", "3.15", "4.1"] },
    { "id": 8, "tasks": ["4.2", "4.3"] },
    { "id": 9, "tasks": ["4.4", "4.5", "4.6"] },
    { "id": 10, "tasks": ["4.7", "4.8", "4.9", "4.10", "6.1"] },
    { "id": 11, "tasks": ["6.2", "6.3", "7.1"] },
    { "id": 12, "tasks": ["7.2", "7.3", "7.4", "7.5"] },
    { "id": 13, "tasks": ["9.1", "9.2", "9.3", "10.1"] },
    { "id": 14, "tasks": ["10.2"] },
    { "id": 15, "tasks": ["10.3"] },
    { "id": 16, "tasks": ["11.1", "12.1"] },
    { "id": 17, "tasks": ["13.1"] },
    { "id": 18, "tasks": ["13.2", "14.1"] }
  ]
}
```
