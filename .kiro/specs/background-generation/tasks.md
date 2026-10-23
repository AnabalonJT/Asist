# Implementation Plan: Background Generation

## Overview

Implementación incremental de la generación en segundo plano para HabitTrack (FastAPI async + SQLAlchemy 2.0 + PostgreSQL; React 19 + Vite + Tailwind). Se construye de abajo hacia arriba: modelo y migración → lógica pura de estado/progreso → servicio (encolar, Worker, consulta, red de huérfanos) → endpoints → notificación Telegram → frontend (hook, indicador, botones) → integración y no-regresión. Cada paso reutiliza el `Chunk_Generator` y el `Phase_Plan_Generator` existentes sin modificar su firma. Los sub-tareas marcadas con `*` son opcionales (tests); las property tests usan Hypothesis con mínimo 100 iteraciones y mockean el LLM.

## Tasks

- [ ] 1. Crear el modelo GenerationJob y su migración
  - [ ] 1.1 Definir el modelo `GenerationJob`
    - Crear `app/models/generation_job.py` con columnas id, user_id, job_type, status, completed_chunks, total_chunks, error_message, result_workout_plan_id, result_diet_phase_plan_id, created_at, updated_at
    - Definir constantes `JOB_TYPES`, `JOB_STATUSES`, `ACTIVE_STATUSES`, el índice único parcial `uq_active_job_per_user_type` y el método `is_active()`
    - Registrar `GenerationJob` en `app/models/__init__.py` (import y `__all__`) e importarlo en `init_db`
    - Añadir la relación `generation_jobs` en `app/models/user.py` (guardada por `TYPE_CHECKING`)
    - _Requirements: 1.1, 1.3, 1.4, 2.4_

  - [ ] 1.2 Crear la migración Alembic de `generation_jobs`
    - Nueva revisión encadenada tras `20260614_100000` con `create_table("generation_jobs", ...)`
    - Crear índices en `user_id`, en `status` y el índice único parcial `uq_active_job_per_user_type` (`postgresql_where=status in ('pending','running')`)
    - _Requirements: 1.1, 2.3, 2.4_

- [ ] 2. Implementar la lógica pura de estado y progreso
  - [ ] 2.1 Crear `generation_job_service` con las funciones puras y constantes
    - Crear `app/services/generation_job_service.py` con las constantes (`DEFAULT_ROUTINE_CHUNKS`, `PHASE_PLAN_CHUNKS`, `POLL_INTERVAL_SECONDS`, `ORPHAN_TIMEOUT_MINUTES`, mensajes `ERR_*` en español)
    - Implementar `is_terminal`, `is_active`, `bump_progress`, `clamp_progress`, `total_chunks_for`, `terminal_status_for_success`, `can_enqueue`
    - _Requirements: 1.5, 1.6, 3.6, 3.7, 2.3, 4.5_

  - [ ]* 2.2 Property test: mapeo de bloques totales por tipo
    - **Property 2: Mapeo de bloques totales por tipo**
    - **Validates: Requirements 1.5, 1.6**

  - [ ]* 2.3 Property test: monotonía y cotas del progreso
    - **Property 3: Monotonía y cotas del progreso**
    - **Validates: Requirements 3.3, 3.6, 3.7, 4.4**

  - [ ]* 2.4 Property test: predicado de encolado (`can_enqueue`)
    - **Property 4: A lo más un trabajo activo por usuario y tipo** (parte pura)
    - **Validates: Requirements 4.5**

- [ ] 3. Implementar el encolado y la consulta de trabajos
  - [ ] 3.1 Implementar `enqueue_job` y la garantía de a lo más un Active_Job
    - Verificar con `get_active_job`/`can_enqueue` y lanzar `ActiveJobExistsError` (español) si ya hay Active_Job del tipo
    - Precondición de `routine`: objetivo de peso válido; si falta, lanzar `GoalRequiredError` (español)
    - Persistir el job `pending` con `total_chunks_for`; traducir la violación del índice único parcial a `ActiveJobExistsError`
    - Programar el Worker con `asyncio.create_task(run_job(job.id))` y devolver el job sin esperar
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 1.2_

  - [ ] 3.2 Implementar `get_job` y `get_active_job`
    - `get_job` filtra por `user_id`; un job inexistente o de otro usuario lanza `JobNotFoundError` (español) sin filtrar datos
    - `get_active_job` devuelve el Active_Job del tipo o `None`
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [ ]* 3.3 Property test: inicialización del trabajo
    - **Property 1: Inicialización del trabajo**
    - **Validates: Requirements 1.2**

  - [ ]* 3.4 Property test: a lo más un Active_Job por usuario y tipo
    - **Property 4: A lo más un trabajo activo por usuario y tipo** (invariante persistido)
    - **Validates: Requirements 2.3, 2.4**

  - [ ]* 3.5 Property test: aislamiento entre usuarios al consultar
    - **Property 8: Aislamiento entre usuarios al consultar**
    - **Validates: Requirements 5.3**

- [ ] 4. Implementar el Worker in-process
  - [ ] 4.1 Implementar `run_job` para `routine` y `phase_plan`
    - Abrir su propia `AsyncSessionLocal`; marcar `running` antes de generar
    - `routine`: iterar `chunk_index` 0..total-1 llamando `goal_wizard_service.generate_routine_chunk`, `bump_progress` y commit tras cada bloque
    - `phase_plan`: llamar `goal_wizard_service.derive_and_persist_plan` una vez y fijar `completed_chunks = 1`
    - Éxito: `succeeded` + Result_Reference (`result_workout_plan_id` / `result_diet_phase_plan_id`)
    - Fallo: capturar la excepción, marcar `failed`, fijar `error_message` en español, preservar el plan parcial y `completed_chunks`; registrar con `logging.exception`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4_

  - [ ]* 4.2 Property test: éxito fija estado terminal y referencia al resultado
    - **Property 5: Éxito fija estado terminal y referencia al resultado**
    - **Validates: Requirements 3.5**

  - [ ]* 4.3 Property test: el fallo marca estado fallido con mensaje en español
    - **Property 6: El fallo marca estado fallido con mensaje en español**
    - **Validates: Requirements 4.2**

  - [ ]* 4.4 Property test: el fallo preserva el plan en construcción
    - **Property 7: El fallo preserva el plan en construcción**
    - **Validates: Requirements 4.3**

  - [ ]* 4.5 Property test: equivalencia del Worker con la generación síncrona por bloques
    - **Property 9: Equivalencia del Worker con la generación síncrona por bloques**
    - **Validates: Requirements 3.2, 8.3**

  - [ ]* 4.6 Unit test: `pending→running` y ejecución de `phase_plan`
    - Verificar transición a `running` antes de generar (3.1) y que `phase_plan` invoca una vez y queda `completed=1` (3.4)
    - _Requirements: 3.1, 3.4_

- [ ] 5. Checkpoint - Asegurar que todas las pruebas pasan
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implementar la red de seguridad de trabajos huérfanos
  - [ ] 6.1 Implementar `reap_orphan_jobs` y registrarlo en el scheduler
    - Implementar `reap_orphan_jobs(db)` en `generation_job_service`: marcar `failed` (con `error_message` español) los Active_Job con `updated_at` más viejo que `ORPHAN_TIMEOUT_MINUTES`; idempotente
    - Registrar el job en `app/scheduler.py` (`start_scheduler`) con `IntervalTrigger(minutes=1)`
    - _Requirements: 4.2, 4.3_

  - [ ]* 6.2 Unit test: `reap_orphan_jobs` marca huérfanos e ignora recientes
    - Un job `running` rezagado pasa a `failed`; uno reciente no se toca
    - _Requirements: 4.2_

- [ ] 7. Implementar la notificación best-effort por Telegram
  - [ ] 7.1 Notificar al llegar a `succeeded`
    - En `run_job`, al pasar a `succeeded`, reutilizar los helpers de `app/scheduler.py` (`_get_chat_id`, `_send_telegram`) dentro de un `try/except` best-effort en español; un fallo se registra y se descarta sin alterar el estado
    - _Requirements: 6.3, 6.4_

  - [ ]* 7.2 Property test: la notificación best-effort no altera el éxito
    - **Property 10: La notificación best-effort no altera el éxito**
    - **Validates: Requirements 6.4**

- [ ] 8. Implementar los endpoints `/api/generation-jobs`
  - [ ] 8.1 Crear el router y los esquemas Pydantic
    - Crear `app/routes/generation_jobs.py` con `EnqueueIn{job_type, chunk_count?}` y `JobOut`
    - `POST /` (202, encolar), `GET /{job_id}` (consultar), `GET /active?job_type=` (trabajo activo o `{message}`)
    - Mapear `ActiveJobExistsError`→409, `GoalRequiredError`→400, `JobNotFoundError`→404 con `detail` en español; `except Exception`→500/502 genérico sin traza
    - Registrar en `app/main.py` con `prefix="/api/generation-jobs"`, `tags=["BackgroundGeneration"]`
    - _Requirements: 2.1, 2.5, 5.1, 5.2, 5.4, 5.5_

  - [ ]* 8.2 Unit test: contratos y mensajes de los endpoints
    - Códigos 202/400/404/409; forma de `JobOut`; rechazo de `job_type` inválido; mensajes en español; `error_message` en un job fallido
    - _Requirements: 1.3, 2.1, 2.5, 5.1, 5.2, 5.4_

- [ ] 9. Checkpoint - Asegurar que todas las pruebas pasan
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Integrar el frontend al flujo asíncrono
  - [ ] 10.1 Añadir `generationJobApi` y tipos en `src/lib/api.ts`
    - Tipos `JobType`, `JobStatus`, `GenerationJob`; métodos `enqueue`, `get`, `getActive`
    - _Requirements: 2.1, 5.1, 5.5_

  - [ ] 10.2 Crear el hook `useGenerationJob`
    - Crear `src/hooks/useGenerationJob.ts`: `enqueue`, *polling* cada 3 s hasta estado terminal, reanudación vía `getActive` al montar; expone `{ job, progress, isActive, isDone, error, enqueue }`
    - _Requirements: 7.4, 7.6_

  - [ ] 10.3 Crear el componente persistente `JobIndicator`
    - Crear `src/components/JobIndicator.tsx` y montarlo en el layout raíz para que sobreviva a la navegación
    - Estados `running` (progreso bloque X de N), `succeeded` ("Ver resultado"), `failed` (error + "Reintentar"); variante estática bajo `prefers-reduced-motion` vía `matchMedia`
    - _Requirements: 6.1, 6.2, 7.3, 7.5_

  - [ ] 10.4 Migrar los botones "Generar rutina" y "Realizar objetivo"
    - `src/pages/FitnessPage.tsx`: "Generar rutina" llama `enqueue('routine')` en vez del bucle síncrono; libera la navegación
    - `src/components/GoalWizard.tsx` (`RoutineStep` / "Realizar objetivo"): encolar `routine`/`phase_plan` sin bloquear con la barra
    - _Requirements: 7.1, 7.2_

  - [ ]* 10.5 Component test: `JobIndicator` y el hook
    - `succeeded`→"Ver resultado"; `failed`→error+"Reintentar"; variante estática con reduced-motion; *polling* con fake timers; reanudación con `getActive`
    - _Requirements: 6.1, 6.2, 7.4, 7.5, 7.6_

- [ ] 11. Verificar la compatibilidad con los flujos síncronos existentes
  - [ ] 11.1 Confirmar la no-regresión del endpoint y generadores existentes
    - Verificar que `POST /api/goal-plan/routine/generate-chunk` conserva su contrato y que el Worker invoca `generate_routine_chunk`/`derive_and_persist_plan` con firma intacta
    - _Requirements: 8.1, 8.2_

  - [ ]* 11.2 Integration test: suite completa sin regresiones
    - Ejecutar la suite y confirmar que los 147 tests existentes siguen verdes junto a los nuevos
    - _Requirements: 8.1, 8.2, 8.3_

- [ ] 12. Checkpoint final - Asegurar que todas las pruebas pasan
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido (tests).
- Cada tarea referencia requisitos específicos para trazabilidad.
- Los property tests usan Hypothesis con mínimo 100 iteraciones y mockean el LLM/Telegram para ser deterministas y baratos.
- Los checkpoints aseguran validación incremental.
- El Worker es in-process (asyncio + red de seguridad APScheduler); no se añade Celery/Redis.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "2.3", "2.4"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["3.3", "3.4", "3.5", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4", "4.5", "4.6", "6.1", "7.1"] },
    { "id": 5, "tasks": ["6.2", "7.2", "8.1"] },
    { "id": 6, "tasks": ["8.2", "10.1"] },
    { "id": 7, "tasks": ["10.2", "10.3"] },
    { "id": 8, "tasks": ["10.4", "11.1"] },
    { "id": 9, "tasks": ["10.5", "11.2"] }
  ]
}
```
