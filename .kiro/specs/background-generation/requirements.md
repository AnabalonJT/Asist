# Requirements Document

## Introduction

La **Background Generation** (generación en segundo plano) es una nueva capacidad de HabitTrack que elimina la espera bloqueante que hoy sufre el usuario cuando genera una rutina de entrenamiento o deriva su plan de objetivo.

Hoy, al pulsar "Generar rutina" (en `FitnessPage`) o "Realizar objetivo" (en `GoalWizard`), la generación por LLM (OpenRouter, modelo gratuito `nvidia/nemotron-3-ultra-550b-a55b:free`) corre de forma **síncrona**: el frontend llama `goalPlanApi.generateRoutineChunk(i, 3)` tres veces seguidas y el usuario queda retenido tras una barra de progreso hasta que terminan los tres bloques. Cada bloque pequeño tarda del orden de 27 segundos con el modelo gratuito, de modo que el usuario no puede navegar a otras páginas (comidas, dashboard) ni hacer otra cosa mientras espera.

Este feature traslada ese trabajo a **segundo plano**. Cuando el usuario pide una generación, el sistema **encola un trabajo** (`Generation_Job`), devuelve su identificador de inmediato (sin bloquear) y ejecuta el trabajo **en proceso** (asyncio/APScheduler, sin infraestructura externa como Celery/Redis) reutilizando la lógica de bloques ya existente y verificada. Mientras el trabajo corre, el usuario puede seguir usando la aplicación con normalidad; el frontend consulta el estado del trabajo por *polling* y muestra un indicador de progreso **no bloqueante** y persistente. Al terminar, se notifica el resultado en la web y, de forma **best-effort**, por Telegram (el bot ya existe).

La feature **reutiliza** y **no reimplementa** la generación por bloques existente: endpoint `POST /api/goal-plan/routine/generate-chunk` (`RoutineChunkIn{chunk_index, chunk_count}`), servicio `goal_wizard_service.generate_routine_chunk` → `fitness_service.generate_workout_plan_chunk` → `llm_service.generate_workout_chunk`, que acumula los días en un `WorkoutPlan` activo. Para el plan de objetivo reutiliza `goal_wizard_service.derive_and_persist_plan` (derivación determinista de fases, sin LLM). El worker llama a esa lógica por bloque, con la misma tolerancia a reintentos por bloque que existe hoy, y actualiza el progreso del `Generation_Job` tras cada bloque.

La única extensión del modelo de datos es una tabla nueva `generation_jobs` (modelo `GenerationJob`) que registra el trabajo: usuario, tipo, estado, progreso por bloque, mensaje de error en español, timestamps y referencia al resultado. Se garantiza **a lo más un trabajo activo por usuario y por tipo**; el progreso es **monótono no decreciente**; y, ante un fallo, el estado previo (el `WorkoutPlan` o el `DietPhasePlan` en construcción) se **preserva** y no se corrompe, consistente con el comportamiento actual.

Toda la interfaz web y los mensajes de error son en español. Los identificadores de código, nombres de modelos y comentarios son en inglés. HabitTrack dirige su producto a usuarios hispanohablantes.

Alcance: modelo `GenerationJob` y su migración Alembic; servicio `generation_job_service` que encola, ejecuta en segundo plano (in-process), consulta y lista trabajos; endpoints bajo `/api/generation-jobs` para encolar, consultar por id y listar el trabajo activo del usuario, con mapeo de errores en español; ejecución del worker reutilizando la lógica de bloques existente con actualización de progreso por bloque y reintento por bloque; notificación best-effort por Telegram al completar; cambios de frontend para que los botones "Generar rutina" / "Realizar objetivo" encolen el trabajo, permitan seguir navegando y muestren estado/progreso no bloqueante con *polling* respetando `prefers-reduced-motion`.

Fuera de alcance (ver sección "Futuro / fuera de alcance" en el diseño): escalado a múltiples instancias de Fly.io con coordinación distribuida (Celery/Redis/colas externas); notificaciones *push* del navegador o *websockets* en tiempo real (se usa *polling*); cancelación de un trabajo en curso por el usuario; historial de trabajos más allá del trabajo activo y el último terminado por tipo; generación de plan de comidas día a día (meal plan); encolado de generación desde el bot de Telegram.

## Glossary

- **Background_Generation**: El subsistema de HabitTrack objeto de este documento, responsable de encolar, ejecutar en segundo plano, consultar y notificar trabajos de generación (rutina y plan de objetivo) de modo que el usuario no quede bloqueado durante la generación por LLM.
- **Generation_Job**: Registro persistente de un trabajo de generación en segundo plano, con usuario, tipo, estado, progreso por bloque, mensaje de error en español, timestamps y referencia al resultado. Modelo `GenerationJob`, tabla `generation_jobs`.
- **Job_Type**: El tipo de trabajo. Uno de `routine` (generación de rutina de entrenamiento vía LLM por bloques) o `phase_plan` (derivación del plan de objetivo en fases, determinista sin LLM).
- **Job_Status**: El estado del Generation_Job. Uno de `pending` (encolado, aún no empezó), `running` (en ejecución), `succeeded` (terminó con éxito) o `failed` (terminó con error).
- **Active_Job**: Un Generation_Job cuyo Job_Status es `pending` o `running`.
- **Chunk**: Uno de los bloques en que se divide la generación de rutina. La rutina se genera en `chunk_count` bloques (hoy 3), con `chunk_index` de 0 a `chunk_count - 1`, acumulando días en un WorkoutPlan activo.
- **Chunk_Count**: El número total de bloques de un trabajo de rutina (hoy 3).
- **Progress**: El avance del Generation_Job, expresado como el número de bloques completados (`completed_chunks`) sobre el total (`total_chunks`). Para `phase_plan`, el total es 1.
- **Chunk_Generator**: La lógica existente y verificada que genera un bloque de rutina: `goal_wizard_service.generate_routine_chunk(db, user_id, chunk_index, chunk_count)` → `fitness_service.generate_workout_plan_chunk` → `llm_service.generate_workout_chunk`.
- **Phase_Plan_Generator**: La lógica existente `goal_wizard_service.derive_and_persist_plan(db, user_id)` que deriva y persiste el DietPhasePlan activo de forma determinista (sin LLM).
- **Worker**: El ejecutor asíncrono in-process (tarea asyncio y/o job de APScheduler) que toma un Generation_Job `pending`, lo marca `running` e invoca al Chunk_Generator o al Phase_Plan_Generator, actualizando el Progress tras cada bloque.
- **WorkoutPlan**: Modelo existente que representa la rutina de entrenamiento activa del usuario; los bloques de rutina acumulan sus días en el WorkoutPlan activo.
- **DietPhasePlan**: Modelo existente que representa el plan de objetivo del usuario dividido en fases; el resultado de un trabajo `phase_plan`.
- **Result_Reference**: La referencia al resultado producido por un Generation_Job: el `workout_plan_id` del WorkoutPlan para `routine`, o el `diet_phase_plan_id` del DietPhasePlan para `phase_plan`.
- **LLM_Service**: La integración existente con OpenRouter (`app/services/llm_service.py`, modelo gratuito `nvidia/nemotron-3-ultra-550b-a55b:free`) usada por el Chunk_Generator.
- **Scheduler**: El APScheduler asíncrono existente (`app/scheduler.py`) que ya corre jobs periódicos y sobre el que se apoya el Worker.
- **Telegram_Bot**: El bot de Telegram existente (python-telegram-bot) capaz de enviar notificaciones al `telegram_chat_id` del usuario.
- **Web_Dashboard**: La interfaz web React de HabitTrack.
- **Job_Indicator**: El indicador de progreso no bloqueante y persistente del Web_Dashboard que muestra el estado del Active_Job del usuario mientras este navega.
- **Polling_Interval**: El intervalo con que el Web_Dashboard consulta el estado de un Generation_Job, igual a 3 segundos.
- **Authenticated_User**: Usuario que ha iniciado sesión y cuya identidad se resuelve vía `get_current_user`.

## Requirements

### Requirement 1: Modelo y persistencia del trabajo en segundo plano

**User Story:** Como usuario, quiero que cada generación quede registrada como un trabajo con su estado y progreso, para poder consultarla y recibir su resultado cuando esté lista.

#### Acceptance Criteria

1. THE Background_Generation SHALL persistir cada Generation_Job con los campos: identificador, `user_id`, Job_Type, Job_Status, bloques completados (`completed_chunks`), bloques totales (`total_chunks`), mensaje de error en español anulable, referencia al resultado anulable, fecha de creación y fecha de última actualización.
2. WHEN se crea un Generation_Job, THE Background_Generation SHALL inicializar su Job_Status en `pending`, sus bloques completados en cero y su referencia al resultado como nula.
3. THE Background_Generation SHALL restringir el Job_Type a los valores `routine` y `phase_plan`.
4. THE Background_Generation SHALL restringir el Job_Status a los valores `pending`, `running`, `succeeded` y `failed`.
5. WHEN un Generation_Job de Job_Type `routine` se crea, THE Background_Generation SHALL fijar sus bloques totales en el Chunk_Count solicitado.
6. WHEN un Generation_Job de Job_Type `phase_plan` se crea, THE Background_Generation SHALL fijar sus bloques totales en uno.

### Requirement 2: Encolar un trabajo sin bloquear al usuario

**User Story:** Como usuario, quiero que al pedir una generación el sistema me responda de inmediato con el identificador del trabajo, para poder seguir usando la aplicación mientras se genera.

#### Acceptance Criteria

1. WHEN un Authenticated_User encola un Generation_Job de un Job_Type dado, THE Background_Generation SHALL crear el Generation_Job con Job_Status `pending` y devolver su identificador y estado sin esperar a que la generación termine.
2. WHEN un Authenticated_User encola un Generation_Job, THE Background_Generation SHALL programar la ejecución del Worker para ese Generation_Job de forma asíncrona e in-process, sin depender de infraestructura externa de colas.
3. IF un Authenticated_User encola un Generation_Job de un Job_Type para el que ya tiene un Active_Job, THEN THE Background_Generation SHALL rechazar la solicitud, conservar el Active_Job existente y devolver un mensaje en español que indique que ya hay una generación de ese tipo en curso.
4. THE Background_Generation SHALL permitir que un mismo Authenticated_User tenga simultáneamente a lo más un Active_Job de Job_Type `routine` y a lo más un Active_Job de Job_Type `phase_plan`.
5. IF un Authenticated_User encola un Generation_Job de Job_Type `routine` sin tener un objetivo de peso válido registrado, THEN THE Background_Generation SHALL rechazar la solicitud y devolver un mensaje en español que indique que falta completar el objetivo antes de generar la rutina.

### Requirement 3: Ejecución del trabajo en segundo plano con progreso por bloque

**User Story:** Como usuario, quiero que la generación corra en segundo plano reutilizando la lógica existente y me muestre cuántos bloques lleva, para saber cuánto falta mientras hago otras cosas.

#### Acceptance Criteria

1. WHEN el Worker toma un Generation_Job `pending`, THE Background_Generation SHALL cambiar su Job_Status a `running` antes de ejecutar la generación.
2. WHILE un Generation_Job de Job_Type `routine` está en ejecución, THE Background_Generation SHALL invocar al Chunk_Generator una vez por cada bloque desde `chunk_index` cero hasta `total_chunks` menos uno, acumulando los días en el WorkoutPlan activo.
3. WHEN el Chunk_Generator completa un bloque de un Generation_Job de Job_Type `routine`, THE Background_Generation SHALL incrementar los bloques completados del Generation_Job en uno.
4. WHEN el Worker ejecuta un Generation_Job de Job_Type `phase_plan`, THE Background_Generation SHALL invocar al Phase_Plan_Generator una sola vez y fijar los bloques completados en uno al terminar.
5. WHEN todos los bloques de un Generation_Job se completan con éxito, THE Background_Generation SHALL cambiar su Job_Status a `succeeded` y registrar la Result_Reference del WorkoutPlan o del DietPhasePlan producido.
6. THE Background_Generation SHALL mantener los bloques completados de un Generation_Job como un valor monótono no decreciente durante toda la vida del Generation_Job.
7. THE Background_Generation SHALL mantener los bloques completados de un Generation_Job siempre entre cero y sus bloques totales, ambos inclusive.

### Requirement 4: Reintento por bloque y manejo de fallos

**User Story:** Como usuario, quiero que un fallo del LLM en un bloque se reintente y, si aun así falla, no corrompa mi plan en construcción, para no perder el progreso previo.

#### Acceptance Criteria

1. WHILE el Chunk_Generator genera un bloque, THE Background_Generation SHALL conservar el comportamiento de reintento por bloque ya existente en la lógica de generación de bloques.
2. IF la generación de un bloque de rutina falla tras agotar sus reintentos, THEN THE Background_Generation SHALL cambiar el Job_Status del Generation_Job a `failed` y registrar un mensaje de error en español.
3. IF un Generation_Job termina en Job_Status `failed`, THEN THE Background_Generation SHALL conservar el estado previo del WorkoutPlan o del DietPhasePlan sin corromper el plan en construcción.
4. IF un Generation_Job termina en Job_Status `failed`, THEN THE Background_Generation SHALL conservar los bloques completados alcanzados antes del fallo sin reducirlos.
5. WHEN un Authenticated_User encola un nuevo Generation_Job de un Job_Type para el que su último trabajo terminó en Job_Status `failed`, THE Background_Generation SHALL permitir el nuevo encolado.

### Requirement 5: Consulta del estado de un trabajo (polling)

**User Story:** Como usuario, quiero consultar el estado de mi trabajo repetidamente, para ver el progreso y saber cuándo terminó sin bloquearme.

#### Acceptance Criteria

1. WHEN un Authenticated_User consulta un Generation_Job propio por su identificador, THE Background_Generation SHALL devolver su Job_Type, su Job_Status, sus bloques completados, sus bloques totales y su Result_Reference cuando exista.
2. IF un Authenticated_User consulta un Generation_Job que no existe, THEN THE Background_Generation SHALL devolver un mensaje en español que indique que el trabajo no fue encontrado.
3. IF un Authenticated_User consulta un Generation_Job que pertenece a otro usuario, THEN THE Background_Generation SHALL rechazar la consulta y devolver un mensaje en español que indique que el trabajo no fue encontrado, sin revelar datos de otro usuario.
4. WHEN un Generation_Job consultado está en Job_Status `failed`, THE Background_Generation SHALL incluir en la respuesta el mensaje de error en español registrado.
5. WHEN un Authenticated_User solicita el Active_Job de un Job_Type dado, THE Background_Generation SHALL devolver el Active_Job de ese Job_Type del usuario o indicar que no hay ninguno activo.

### Requirement 6: Notificación al completar

**User Story:** Como usuario, quiero enterarme cuando la generación termina aunque esté en otra página, para revisar el resultado sin estar pendiente de la pantalla.

#### Acceptance Criteria

1. WHEN un Generation_Job cambia a Job_Status `succeeded`, THE Web_Dashboard SHALL mostrar en el Job_Indicator un aviso en español de que la generación terminó y un enlace o acción para ver el resultado.
2. WHEN un Generation_Job cambia a Job_Status `failed`, THE Web_Dashboard SHALL mostrar en el Job_Indicator un aviso en español con el mensaje de error y una acción para reintentar.
3. WHERE el Authenticated_User tiene un `telegram_chat_id` vinculado y un Generation_Job cambia a Job_Status `succeeded`, THE Background_Generation SHALL enviar por el Telegram_Bot una notificación en español de forma best-effort.
4. IF el envío de la notificación por el Telegram_Bot falla, THEN THE Background_Generation SHALL conservar el Job_Status `succeeded` del Generation_Job sin alterarlo.

### Requirement 7: Encolar y seguir navegando desde la web

**User Story:** Como usuario, quiero que al pulsar "Generar rutina" o "Realizar objetivo" el trabajo se encole y yo pueda navegar a otras páginas, para no quedar atrapado tras una barra de progreso.

#### Acceptance Criteria

1. WHEN un Authenticated_User pulsa "Generar rutina" en la página de Fitness, THE Web_Dashboard SHALL encolar un Generation_Job de Job_Type `routine` y permitir al usuario navegar a otras páginas sin esperar a que la generación termine.
2. WHEN un Authenticated_User pulsa "Realizar objetivo" en el GoalWizard, THE Web_Dashboard SHALL encolar un Generation_Job de Job_Type `phase_plan` y permitir al usuario navegar a otras páginas sin esperar a que la generación termine.
3. WHILE un Authenticated_User tiene un Active_Job, THE Web_Dashboard SHALL mostrar el Job_Indicator de forma persistente mientras el usuario navega entre páginas.
4. WHILE un Active_Job está en ejecución, THE Web_Dashboard SHALL consultar el estado del Generation_Job cada Polling_Interval y actualizar el Progress mostrado en el Job_Indicator.
5. WHERE el usuario ha activado `prefers-reduced-motion`, THE Web_Dashboard SHALL mostrar el Progress del Job_Indicator mediante una representación estática equivalente sin animación.
6. WHEN un Authenticated_User recarga la página teniendo un Active_Job, THE Web_Dashboard SHALL recuperar el Active_Job mediante la consulta del trabajo activo y volver a mostrar el Job_Indicator.

### Requirement 8: Compatibilidad con los flujos síncronos existentes

**User Story:** Como responsable del producto, quiero que la migración al flujo asíncrono no rompa los endpoints existentes de los que dependen otros flujos y tests, para no desestabilizar lo que ya funciona.

#### Acceptance Criteria

1. THE Background_Generation SHALL conservar el endpoint existente `POST /api/goal-plan/routine/generate-chunk` y su contrato de entrada y salida actuales.
2. THE Background_Generation SHALL conservar la firma y el comportamiento del Chunk_Generator y del Phase_Plan_Generator existentes al invocarlos desde el Worker.
3. WHEN el Worker ejecuta un Generation_Job de Job_Type `routine`, THE Background_Generation SHALL producir el mismo WorkoutPlan activo acumulado que produce la secuencia de llamadas síncronas a `generate-chunk` con el mismo Chunk_Count.
