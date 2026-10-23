# Requirements Document

## Introduction

El **Goal Wizard** (asistente de objetivo progresivo) es una nueva capacidad de HabitTrack que guía al usuario, paso a paso desde la página Fitness de la web, para pasar de un peso actual A a un peso objetivo B con una **dieta progresiva** y luego una **rutina de entrenamiento**, generada por partes porque el LLM es lento.

La diferencia central respecto al Fitness_Coach existente es la **dieta progresiva**: en lugar de un único déficit (o superávit) agresivo para todo el trayecto A→B, el sistema parte el trayecto en **fases**. Cada fase tiene sus propias metas diarias de calorías y macros, derivadas del peso **vigente al inicio de esa fase** (no del peso original A). Cuando el usuario registra que alcanzó el peso de fin de una fase (reutilizando el registro de peso existente), la siguiente fase se **re-deriva** con los valores vigentes, de modo que el plan se adapta de forma gradual ("no tan cortante de una") y respeta la adaptación metabólica.

El asistente avanza por una máquina de estados de pasos: (1) completar el perfil si falta, (2) definir el objetivo A→B, (3) indicar el equipo disponible, (4) generar la dieta mientras se muestra una animación temática de progreso, (5) indicar los días de entrenamiento por semana, (6) generar la rutina informando progreso incremental, y (7) mostrar y permitir **editar** el resultado completo (metas de dieta por fase + rutina semanal).

**Realidad del LLM (explícita).** La generación de dieta y rutina depende del LLM de OpenRouter, hoy poco fiable en el modelo gratuito (el modelo `qwen` gratuito está limitado por tasa; `nemotron` razona pero no emite JSON usable y se trunca). Esta funcionalidad **requiere un modelo fiable** (clave propia del usuario en OpenRouter o un modelo de pago económico) para operar en producción. Por diseño, las **metas de dieta por fase son deterministas y puras** (matemática a partir de datos corporales + ritmo objetivo con Mifflin-St Jeor), de modo que el paso de dieta funciona aunque el LLM de plan de comidas esté caído; solo el plan de comidas día a día (opcional) y la rutina usan el LLM.

El asistente **reutiliza** el perfil fitness, la validación, el cálculo de ritmo, el registro de peso y la generación de rutina ya existentes en `app/services/fitness_service.py`, y las funciones puras de derivación nutricional de `app/services/meal_service.py`. Introduce un **nuevo estado de dominio** mínimo (plan de fases persistido) para que el progreso sobreviva entre sesiones.

Toda la interfaz web, las respuestas del bot y los detalles de error de la API son en español. Los identificadores de código, nombres de modelos y comentarios son en inglés. El sistema entrega estimaciones orientativas, no consejo médico, e incluye descargos apropiados.

Alcance: el asistente guiado multipaso en la web; el cálculo y la persistencia del plan de fases progresivo; la derivación determinista de metas por fase; el avance de fase al alcanzar el peso de fin; la re-adaptación de la fase cuando el progreso real difiere de lo esperado; la generación de rutina por partes con progreso incremental y preservación de estado ante fallos del LLM; el resumen final editable; privacidad por usuario autenticado y descargos.

Fuera de alcance (ver sección "Futuro / fuera de alcance" en el diseño): el asistente desde Telegram; la detección automática de estancamiento (plateau) a partir de los datos de actividad; el ciclado de macros (carb cycling); la planificación de comidas día a día como paso obligatorio del asistente (el plan de comidas por LLM queda opcional y degrada limpiamente).

## Glossary

- **Goal_Wizard**: El subsistema objeto de este documento, que orquesta el flujo guiado multipaso y el plan de fases progresivo sobre el Fitness_Coach existente.
- **Fitness_Profile**: Registro 1:1 con el usuario definido por la feature fitness-coach (`app/models/fitness_profile.py`): `weight_kg`, `height_cm`, `age`, `sex`, `level`, `equipment` (lista JSON), `days_per_week`, `minutes_per_session`, `goal_type`, `target_weight_kg`, `target_date` (ISO), `performance_target`. El Goal_Wizard lo lee y lo actualiza mediante las funciones existentes.
- **Profile_Complete**: Estado de un Fitness_Profile cuyos campos corporales y de disponibilidad obligatorios (`weight_kg`, `height_cm`, `age`, `level`, `days_per_week`, `minutes_per_session`) están presentes y dentro de rango.
- **Weight_Goal**: Objetivo cuantitativo de peso del usuario: peso actual A (`weight_kg`), peso objetivo B (`target_weight_kg`) y fecha objetivo (`target_date`), con `goal_type` igual a `weight_target`.
- **Diet_Phase_Plan**: Entidad nueva, 1:N con el usuario, que representa el trayecto A→B dividido en fases ordenadas. A lo más un Diet_Phase_Plan activo por usuario.
- **Diet_Phase**: Una fase ordenada dentro de un Diet_Phase_Plan, con índice, peso de inicio, peso objetivo de fin, metas diarias (`kcal`, `protein_g`, `fat_g`, `carbs_g`), estado (`active`, `completed`, `pending`) y fechas de inicio/fin estimadas.
- **Phase_Size_Rule**: La regla documentada que determina cuánto abarca cada fase: una fase abarca a lo más 2,5 kg de cambio de peso o 4 semanas de duración estimada, lo que ocurra primero.
- **Phase_Targets**: Las metas diarias (`kcal`, `protein_g`, `fat_g`, `carbs_g`) de una Diet_Phase, derivadas de forma determinista (sin LLM) del peso vigente al inicio de la fase, usando `estimate_maintenance_kcal` y `derive_nutrition_targets` con el ritmo objetivo de la fase.
- **Phase_Tolerance**: El margen por el cual se considera que el usuario "alcanzó" el peso objetivo de fin de una fase, definido como 0,5 kg respecto al peso objetivo de fin de la fase en la dirección del objetivo.
- **Phase_Time_Window**: La duración estimada de una fase en semanas, usada para detectar progreso insuficiente cuando ha transcurrido ese tiempo sin alcanzar el peso de fin.
- **Weight_Entry**: Registro de peso corporal en una fecha, gestionado por `fitness_service.add_weight_entry` (rango válido 30–300 kg). El Goal_Wizard reutiliza este flujo para detectar el avance de fase.
- **Target_Rate**: Resultado de `fitness_service.compute_target_rate(current_weight, target_weight, weeks)`: `rate_kg_per_week`, `daily_kcal_delta`, `direction`, `warning`, `warning_message`, `disclaimer`.
- **Nutrition_Derivation**: Las funciones puras de `app/services/meal_service.py`: `estimate_maintenance_kcal(view)` (Mifflin-St Jeor + factor de actividad) y `derive_nutrition_targets(view, target_rate)` (reparto de macros 4/4/9 con la poscondición de ±10 kcal).
- **Workout_Plan**: Rutina de entrenamiento generada y persistida por `fitness_service.generate_workout_plan` (vía LLM, timeout 120 s, reintento, filtrado por equipo). A lo más una activa por usuario.
- **LLM_Service**: La integración con OpenRouter (`app/services/llm_service.py`) usada por la generación de rutina y, opcionalmente, del plan de comidas.
- **Wizard_Step**: Uno de los pasos ordenados del asistente: `profile`, `goal`, `equipment`, `diet`, `training_days`, `routine`, `summary`.
- **Wizard_State**: El estado del asistente de un usuario, que determina el Wizard_Step actual y preserva los datos ya capturados entre pasos y entre sesiones.
- **Reduced_Motion**: La preferencia del sistema del usuario `prefers-reduced-motion` que, cuando está activa, suprime las animaciones temáticas y muestra una alternativa estática.
- **Web_Dashboard**: La interfaz web React de HabitTrack (`src/`).
- **Authenticated_User**: Usuario que ha iniciado sesión y cuya identidad se resuelve vía `get_current_user`.

## Requirements

### Requirement 1: Lanzamiento del asistente y máquina de estados

**User Story:** Como usuario, quiero iniciar un asistente guiado desde la página Fitness con un botón "Realizar objetivo", para avanzar paso a paso hasta tener un plan completo.

#### Acceptance Criteria

1. THE Web_Dashboard SHALL presentar en la página Fitness un botón en español con la etiqueta "Realizar objetivo" que inicia el Goal_Wizard.
2. WHEN un Authenticated_User inicia el Goal_Wizard, THE Goal_Wizard SHALL determinar el Wizard_Step inicial evaluando los pasos en el orden `profile`, `goal`, `equipment`, `diet`, `training_days`, `routine`, `summary` y posicionándose en el primer paso cuyos datos requeridos aún no estén completos.
3. WHILE el Goal_Wizard está activo, THE Goal_Wizard SHALL avanzar de un Wizard_Step al siguiente únicamente cuando los datos requeridos del paso actual sean válidos y hayan sido persistidos.
4. WHEN un Authenticated_User retrocede a un Wizard_Step anterior, THE Goal_Wizard SHALL conservar los datos ya capturados en los pasos posteriores sin descartarlos.
5. WHERE el Fitness_Profile del Authenticated_User ya es Profile_Complete al iniciar el asistente, THE Goal_Wizard SHALL omitir el Wizard_Step `profile` y posicionarse en el primer paso siguiente incompleto.
6. WHEN un Authenticated_User reanuda el Goal_Wizard en una sesión posterior, THE Goal_Wizard SHALL restaurar el Wizard_Step correspondiente al primer paso con datos requeridos incompletos a partir del estado persistido.

### Requirement 2: Completar el perfil (paso profile)

**User Story:** Como usuario, quiero completar mis datos corporales y mi nivel dentro del asistente solo si faltan, para no repetir información que ya registré.

#### Acceptance Criteria

1. WHILE el Goal_Wizard está en el Wizard_Step `profile`, THE Web_Dashboard SHALL presentar un formulario en español para `weight_kg`, `height_cm`, `age`, `sex` opcional, `level`, `days_per_week` y `minutes_per_session`.
2. WHEN un Authenticated_User envía datos de perfil en el Wizard_Step `profile`, THE Goal_Wizard SHALL validarlos con `fitness_service.validate_profile_fields` y, si son válidos, crear o actualizar el Fitness_Profile 1:1 del usuario.
3. IF los datos de perfil enviados en el Wizard_Step `profile` son inválidos, THEN THE Goal_Wizard SHALL rechazar la operación, conservar sin cambios el Fitness_Profile previo y devolver el mensaje de error en español que identifica el campo inválido y su rango válido.
4. WHERE el Fitness_Profile del usuario ya es Profile_Complete, THE Goal_Wizard SHALL permitir omitir el envío del Wizard_Step `profile` y continuar al siguiente paso.

### Requirement 3: Definir el objetivo A→B (paso goal)

**User Story:** Como usuario, quiero definir mi peso actual, mi peso objetivo y la fecha objetivo, para que el asistente arme un plan progresivo hacia esa meta.

#### Acceptance Criteria

1. WHILE el Goal_Wizard está en el Wizard_Step `goal`, THE Web_Dashboard SHALL presentar un formulario en español para el peso objetivo (`target_weight_kg`) y la fecha objetivo (`target_date`), tomando el peso actual del Fitness_Profile como peso A.
2. WHEN un Authenticated_User envía un objetivo en el Wizard_Step `goal`, THE Goal_Wizard SHALL validarlo con `fitness_service.validate_goal_fields` para `goal_type` igual a `weight_target` y, si es válido, almacenar `goal_type`, `target_weight_kg` y `target_date` en el Fitness_Profile.
3. IF el objetivo enviado en el Wizard_Step `goal` tiene una fecha objetivo anterior o igual a la fecha actual, o un peso objetivo fuera del rango de 30 a 300 kg, THEN THE Goal_Wizard SHALL rechazar la operación, conservar sin cambios el objetivo previo y devolver el mensaje de error en español correspondiente.
4. WHEN el Goal_Wizard almacena un Weight_Goal válido, THE Goal_Wizard SHALL incluir en la respuesta el Target_Rate calculado por `fitness_service.compute_target_rate` junto con su advertencia cuando aplique y el descargo médico en español.

### Requirement 4: Equipo disponible (paso equipment)

**User Story:** Como usuario, quiero indicar el equipo que tengo disponible, para que la rutina use solo lo que puedo utilizar.

#### Acceptance Criteria

1. WHILE el Goal_Wizard está en el Wizard_Step `equipment`, THE Web_Dashboard SHALL presentar en español la lista del catálogo de equipo definido en `fitness_service.EQUIPMENT_CATALOG` para selección múltiple.
2. WHEN un Authenticated_User confirma el equipo en el Wizard_Step `equipment`, THE Goal_Wizard SHALL validar que cada elemento pertenece al catálogo y almacenar la lista de equipo en el Fitness_Profile.
3. IF algún elemento de equipo enviado en el Wizard_Step `equipment` no pertenece al catálogo definido, THEN THE Goal_Wizard SHALL rechazar la operación, conservar sin cambios el equipo previo del Fitness_Profile y devolver un mensaje de error en español que identifique el equipo inválido.

### Requirement 5: Regla de fases del plan progresivo (Phase_Size_Rule)

**User Story:** Como usuario, quiero que mi trayecto A→B se divida en fases manejables, para avanzar con déficits o superávits sostenibles en lugar de uno solo agresivo.

#### Acceptance Criteria

1. WHEN el Goal_Wizard deriva un Diet_Phase_Plan a partir de un Weight_Goal, THE Goal_Wizard SHALL dividir el trayecto desde el peso actual A hasta el peso objetivo B en Diet_Phase ordenadas aplicando la Phase_Size_Rule, donde cada fase abarca a lo más 2,5 kg de cambio de peso o 4 semanas de duración estimada, lo que ocurra primero.
2. WHEN el Goal_Wizard construye las Diet_Phase, THE Goal_Wizard SHALL asignar a cada fase un peso de inicio igual al peso de fin de la fase anterior, siendo el peso de inicio de la primera fase igual al peso actual A, y un peso de fin que avanza hacia B sin sobrepasarlo.
3. THE Goal_Wizard SHALL asignar a la última Diet_Phase un peso de fin exactamente igual al peso objetivo B.
4. WHERE la diferencia entre el peso actual A y el peso objetivo B es menor o igual a 2,5 kg, THE Goal_Wizard SHALL construir un Diet_Phase_Plan con exactamente una Diet_Phase cuyo peso de fin es B.
5. WHEN el Goal_Wizard asigna la duración estimada de cada Diet_Phase, THE Goal_Wizard SHALL calcular la duración en semanas de cada fase a partir del cambio de peso de la fase dividido entre el valor absoluto del `rate_kg_per_week` del Target_Rate del Weight_Goal, con un mínimo de 1 semana por fase.
6. WHEN el Goal_Wizard persiste un Diet_Phase_Plan, THE Goal_Wizard SHALL marcar como `active` la primera Diet_Phase y como `pending` las fases restantes, dejando a lo más un Diet_Phase_Plan activo por usuario.

### Requirement 6: Metas por fase deterministas (paso diet)

**User Story:** Como usuario, quiero que las metas de calorías y macros de cada fase salgan de mis datos corporales y mi ritmo objetivo, para tener una dieta coherente sin depender de que el LLM funcione.

#### Acceptance Criteria

1. WHEN el Goal_Wizard calcula las Phase_Targets de una Diet_Phase, THE Goal_Wizard SHALL derivarlas de forma determinista con `meal_service.estimate_maintenance_kcal` y `meal_service.derive_nutrition_targets` usando el peso de inicio de esa fase como peso vigente, sin invocar al LLM_Service.
2. WHEN el Goal_Wizard deriva las Phase_Targets de una Diet_Phase, THE Goal_Wizard SHALL usar como ritmo objetivo de la fase el Target_Rate derivado del cambio de peso de la fase y de su duración estimada, de modo que el ajuste calórico diario corresponda a esa fase y no al trayecto completo A→B.
3. THE Goal_Wizard SHALL registrar en cada Diet_Phase sus Phase_Targets `kcal`, `protein_g`, `fat_g` y `carbs_g` resultantes de la derivación.
4. WHEN el Goal_Wizard calcula las Phase_Targets, THE Goal_Wizard SHALL garantizar que el valor absoluto de `protein_g*4 + carbs_g*4 + fat_g*9 - kcal` no exceda 10 kcal, consistente con la poscondición de `derive_nutrition_targets`.
5. WHILE el Goal_Wizard está en el Wizard_Step `diet`, THE Web_Dashboard SHALL mostrar el progreso de la generación de la dieta mediante una animación temática en lugar de un indicador estático congelado.
6. WHERE la preferencia Reduced_Motion del usuario está activa, THE Web_Dashboard SHALL suprimir la animación temática del Wizard_Step `diet` y mostrar una alternativa estática equivalente.
7. WHEN el Goal_Wizard completa la derivación de la dieta, THE Goal_Wizard SHALL devolver las Phase_Targets de todas las fases junto con el descargo médico en español.

### Requirement 7: Avance de fase y re-adaptación progresiva

**User Story:** Como usuario, quiero que al alcanzar el peso de fin de una fase la siguiente se recalcule con mi peso vigente, para que la dieta se re-adapte y no sea tan cortante de una.

#### Acceptance Criteria

1. WHEN un Authenticated_User registra un Weight_Entry cuyo peso alcanza el peso objetivo de fin de la Diet_Phase activa dentro de la Phase_Tolerance de 0,5 kg en la dirección del objetivo, THE Goal_Wizard SHALL marcar esa Diet_Phase como `completed` y activar la siguiente Diet_Phase `pending`.
2. WHEN el Goal_Wizard activa la siguiente Diet_Phase, THE Goal_Wizard SHALL re-derivar sus Phase_Targets usando el peso vigente del usuario en ese momento como peso de inicio de la fase.
3. IF ha transcurrido la Phase_Time_Window de la Diet_Phase activa y el peso vigente del usuario no ha alcanzado el peso objetivo de fin dentro de la Phase_Tolerance, THEN THE Goal_Wizard SHALL extender la Diet_Phase activa recalculando su duración estimada y sus Phase_Targets a partir del peso vigente, sin saltar a la siguiente fase.
4. IF un Authenticated_User registra un Weight_Entry cuyo peso sobrepasa el peso objetivo de fin de la Diet_Phase activa más allá de la Phase_Tolerance en la dirección del objetivo, THEN THE Goal_Wizard SHALL marcar como `completed` todas las Diet_Phase cuyo peso objetivo de fin ya fue alcanzado o sobrepasado y activar la primera Diet_Phase `pending` restante.
5. WHEN la última Diet_Phase alcanza el estado `completed`, THE Goal_Wizard SHALL establecer una Diet_Phase de mantenimiento cuyas Phase_Targets se derivan con dirección de mantenimiento sobre el peso objetivo B, y marcar el Weight_Goal como alcanzado.
6. THE Goal_Wizard SHALL persistir el Diet_Phase_Plan y el estado de cada Diet_Phase de modo que el progreso se restaure en sesiones posteriores.

### Requirement 8: Días de entrenamiento (paso training_days)

**User Story:** Como usuario, quiero indicar cuántos días por semana entrenaré, para que la rutina se ajuste a mi disponibilidad real.

#### Acceptance Criteria

1. WHILE el Goal_Wizard está en el Wizard_Step `training_days`, THE Web_Dashboard SHALL presentar en español un control para elegir los días de entrenamiento por semana entre 1 y 7.
2. WHEN un Authenticated_User confirma los días de entrenamiento en el Wizard_Step `training_days`, THE Goal_Wizard SHALL almacenar `days_per_week` en el Fitness_Profile tras validar que está entre 1 y 7.
3. IF el número de días enviado en el Wizard_Step `training_days` está fuera del rango de 1 a 7, THEN THE Goal_Wizard SHALL rechazar la operación, conservar sin cambios el valor previo y devolver un mensaje de error en español que indique el rango válido.

### Requirement 9: Generación de rutina por partes con progreso incremental (paso routine)

**User Story:** Como usuario, quiero generar la rutina viendo progreso ("generando rutina... Día 1... Día 2..."), para no quedarme ante un spinner congelado mientras el LLM es lento.

#### Acceptance Criteria

1. WHEN un Authenticated_User inicia la generación de rutina en el Wizard_Step `routine`, THE Goal_Wizard SHALL generar el Workout_Plan invocando `fitness_service.generate_workout_plan` con el Fitness_Profile y el objetivo del usuario como una llamada de API propia del paso.
2. WHILE la generación de rutina está en curso, THE Web_Dashboard SHALL mostrar progreso incremental en español que informe el avance de la generación en lugar de un indicador estático congelado.
3. IF la generación de rutina falla por tiempo de espera, error, respuesta vacía o contenido no interpretable del LLM_Service, THEN THE Goal_Wizard SHALL devolver un mensaje de error en español que ofrezca reintentar y SHALL preservar el Wizard_State y los datos de los pasos anteriores.
4. WHEN la generación de rutina falla, THE Goal_Wizard SHALL preservar sin cambios el Fitness_Profile, el Weight_Goal, el Diet_Phase_Plan y el Workout_Plan activo previo del usuario.
5. WHEN un Authenticated_User reintenta la generación de rutina tras un fallo, THE Goal_Wizard SHALL reutilizar el Fitness_Profile y el objetivo existentes sin requerir que el usuario los vuelva a introducir.
6. THE Goal_Wizard SHALL ajustar el número de días del Workout_Plan para que no exceda el valor `days_per_week` confirmado en el Wizard_Step `training_days`.

### Requirement 10: Resumen final editable (paso summary)

**User Story:** Como usuario, quiero ver al final todo mi plan (metas de dieta por fase y rutina semanal) y poder editarlo, para ajustarlo a mi gusto antes de empezar.

#### Acceptance Criteria

1. WHILE el Goal_Wizard está en el Wizard_Step `summary`, THE Web_Dashboard SHALL presentar en español las Phase_Targets de las Diet_Phase y el Workout_Plan activo con su estructura de días y ejercicios.
2. WHEN un Authenticated_User edita las Phase_Targets de la Diet_Phase activa en el Wizard_Step `summary` con valores válidos, THE Goal_Wizard SHALL persistir las Phase_Targets editadas en la Diet_Phase activa.
3. IF un Authenticated_User edita las Phase_Targets con valores fuera de los rangos manuales de `meal_service` (kcal 800–6000, proteínas 0–500 g, grasas 0–500 g, carbohidratos 0–1000 g), THEN THE Goal_Wizard SHALL rechazar la edición, conservar sin cambios las Phase_Targets previas y devolver un mensaje de error en español que identifique el campo inválido y su rango.
4. WHEN un Authenticated_User edita el Workout_Plan en el Wizard_Step `summary` con una estructura válida según `fitness_service.validate_plan_structure`, THE Goal_Wizard SHALL persistir el Workout_Plan editado como el plan activo del usuario.
5. IF un Authenticated_User edita el Workout_Plan con una estructura inválida, THEN THE Goal_Wizard SHALL rechazar la edición, conservar sin cambios el Workout_Plan activo previo y devolver un mensaje de error en español.

### Requirement 11: Persistencia y consulta del plan de fases

**User Story:** Como usuario, quiero que mi plan de fases quede guardado y pueda consultarlo, para retomar mi progreso cuando vuelva.

#### Acceptance Criteria

1. WHEN el Goal_Wizard persiste un Diet_Phase_Plan nuevo para un usuario, THE Goal_Wizard SHALL marcar como inactivo cualquier Diet_Phase_Plan activo previo del mismo usuario, dejando a lo más un Diet_Phase_Plan activo por usuario.
2. WHEN un Authenticated_User consulta su Diet_Phase_Plan activo, THE Goal_Wizard SHALL devolver el plan con sus Diet_Phase ordenadas por índice, el estado de cada fase y la Diet_Phase activa actual.
3. IF un Authenticated_User consulta su Diet_Phase_Plan y no existe ninguno activo, THEN THE Goal_Wizard SHALL devolver un mensaje en español que indique que no hay un plan de fases activo y que puede iniciar el asistente.
4. THE Goal_Wizard SHALL almacenar la estructura de las Diet_Phase de forma consistente con los modelos existentes del proyecto, usando JSON en una columna de texto cuando la estructura sea un árbol variable.

### Requirement 12: Privacidad y descargos

**User Story:** Como usuario, quiero que mis datos del asistente estén protegidos y que el plan incluya descargos, para usar la herramienta con confianza.

#### Acceptance Criteria

1. THE Goal_Wizard SHALL proteger todos sus endpoints requiriendo la identidad del Authenticated_User vía `get_current_user`.
2. IF una solicitud a un endpoint del Goal_Wizard no incluye una identidad autenticada válida, THEN THE Goal_Wizard SHALL rechazar la solicitud sin exponer datos.
3. WHEN un Authenticated_User solicita o modifica datos del asistente, THE Goal_Wizard SHALL operar únicamente sobre los registros que pertenecen a ese usuario, salvo que el solicitante sea administrador.
4. IF un Authenticated_User que no es administrador solicita el Diet_Phase_Plan, el Fitness_Profile o el Workout_Plan de otro usuario, THEN THE Goal_Wizard SHALL rechazar la solicitud sin exponer datos de ese otro usuario.
5. WHEN el Goal_Wizard devuelve una respuesta que contiene Phase_Targets o un Workout_Plan, THE Goal_Wizard SHALL incluir un descargo en español que indique que la información es orientativa, no constituye consejo ni diagnóstico médico, y que se recomienda consultar a un profesional.
