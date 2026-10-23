# Requirements Document

## Introduction

El **Fitness Coach** es una nueva capacidad de HabitTrack que ayuda al usuario a estructurar su entrenamiento físico. El usuario registra un **perfil fitness** (equipo disponible, datos corporales, nivel y disponibilidad) y define un **objetivo** (bajar de un peso A a un peso B en un plazo, o un objetivo cualitativo/de rendimiento como adelgazar, ganar músculo, mantener, mejorar resistencia o lograr una marca). Con ese perfil y ese objetivo, el sistema genera una **rutina de entrenamiento** estructurada mediante el LLM de OpenRouter, adaptada al equipo disponible, al objetivo y a cuánto se mueve el usuario según su historial de actividades. Para objetivos de peso con plazo, el sistema calcula un **ritmo objetivo** realista y advierte cuando el plazo es poco saludable o irreal. El usuario puede registrar su peso a lo largo del tiempo (weigh-ins) para visualizar progreso, y ver su adherencia a la rutina a partir de las actividades ya registradas.

El perfil fitness (peso actual, peso objetivo, plazo, nivel de actividad y calorías/macros objetivo derivados) está modelado deliberadamente para ser **reutilizado por la feature meal-planner**, de modo que un solo perfil alimente tanto el entrenamiento como la planificación de comidas.

Toda la interfaz web, las respuestas del bot de Telegram y los mensajes de error son en español. Los identificadores de código, nombres de modelos y comentarios son en inglés. El sistema entrega estimaciones informativas, no consejo médico, e incluye descargos apropiados.

Alcance: gestión del perfil fitness, definición de objetivos (peso A→B con plazo y objetivos cualitativos/rendimiento), generación de rutina adaptada, cálculo del ritmo objetivo con advertencias, registro y visualización de peso, adherencia/progreso usando actividades, interfaces web y Telegram, manejo de fallos del LLM y privacidad/descargos.

Fuera de alcance: la planificación de comidas y el cálculo detallado de macros (feature meal-planner, que consumirá este perfil); consejo o diagnóstico médico; integraciones con wearables o dispositivos externos.

## Glossary

- **Fitness_Coach**: El subsistema de HabitTrack objeto de este documento, responsable del perfil fitness, objetivos, rutinas, ritmo objetivo, weigh-ins y progreso.
- **Fitness_Profile**: Registro 1:1 con el usuario que almacena datos corporales (peso actual, altura, edad, sexo opcional), nivel (principiante, intermedio, avanzado), equipo disponible, disponibilidad (días por semana, minutos por sesión) y el objetivo actual. Reutilizado por el meal-planner.
- **Equipment_Item**: Elemento de equipo/herramienta que el usuario tiene disponible, elegido de un catálogo definido (mancuernas, barra, banco, kettlebell, bandas, peso corporal / sin equipo, acceso a gimnasio, máquinas).
- **Fitness_Goal**: Objetivo del usuario. Puede ser cuantitativo de peso (peso actual A → peso objetivo B en un plazo) o cualitativo/de rendimiento (adelgazar, ganar músculo, mantener, mejorar resistencia, o una marca específica como "correr 10 km" o "salto de X metros").
- **Goal_Type**: Clasificación del objetivo. Valores: `weight_target`, `lose_weight`, `gain_muscle`, `maintain`, `improve_endurance`, `performance`.
- **Target_Rate**: Ritmo de cambio de peso calculado para un objetivo `weight_target`, expresado como cambio de peso por semana y como déficit/superávit calórico diario aproximado (usando 7700 kcal por kilogramo de peso corporal).
- **Weight_Entry**: Registro de peso corporal del usuario en una fecha determinada, usado para graficar progreso. Rango válido: 30 a 300 kg.
- **Workout_Plan**: Rutina de entrenamiento generada y persistida, con estructura de días, cada día con ejercicios (nombre, series/reps o duración, descanso). Un usuario tiene a lo más un Workout_Plan activo a la vez.
- **Activity**: Registro de actividad existente en HabitTrack (tipo, duración, distancia, calorías, series). El Fitness_Coach lo usa como fuente para calibrar volumen y medir adherencia.
- **Activity_Summary**: Resumen agregado del historial de Activity de un usuario en la ventana reciente de 28 días (frecuencia, minutos totales, tipos), usado como entrada del LLM y para calibrar la rutina.
- **Activity_Window**: La ventana reciente usada para construir el Activity_Summary, definida como los últimos 28 días contados hacia atrás desde la fecha actual.
- **Healthy_Rate_Threshold**: Umbral de cambio de peso semanal considerado saludable, definido como 1,00 kg por semana o el 1,0 % del peso corporal actual por semana, el que resulte aplicable.
- **LLM_Service**: La integración con OpenRouter (`app/services/llm_service.py`) que recibe perfil, objetivo y Activity_Summary y devuelve una rutina en JSON.
- **Meal_Planner**: Feature separada (fuera de alcance de este documento) que consume el Fitness_Profile y el Target_Rate para planificar comidas.
- **Web_Dashboard**: La interfaz web React de HabitTrack.
- **Telegram_Bot**: El bot de Telegram de HabitTrack.
- **Authenticated_User**: Usuario que ha iniciado sesión y cuya identidad se resuelve vía `get_current_user`.

## Requirements

### Requirement 1: Gestión del perfil fitness

**User Story:** Como usuario, quiero registrar y editar mi perfil fitness (datos corporales, equipo, nivel y disponibilidad), para que el coach genere rutinas adaptadas a mí y el meal-planner pueda reutilizar mis datos.

#### Acceptance Criteria

1. WHEN un Authenticated_User envía datos de perfil que incluyen peso actual entre 30 y 300 kg, altura entre 100 y 250 cm, edad entre 13 y 100 años y nivel igual a `principiante`, `intermedio` o `avanzado`, THE Fitness_Coach SHALL crear o actualizar el Fitness_Profile asociado a ese usuario con una relación 1:1.
2. WHERE el usuario indica equipo disponible, THE Fitness_Coach SHALL almacenar en el Fitness_Profile cada Equipment_Item seleccionado del catálogo definido (mancuernas, barra, banco, kettlebell, bandas, peso corporal, acceso a gimnasio, máquinas).
3. WHEN un Authenticated_User registra disponibilidad con días por semana entre 1 y 7 y minutos por sesión entre 10 y 240, THE Fitness_Coach SHALL almacenar los días por semana y los minutos por sesión en el Fitness_Profile.
4. WHERE el usuario proporciona sexo con valor `male`, `female` u `other`, THE Fitness_Coach SHALL almacenar el valor de sexo en el Fitness_Profile como dato opcional.
5. IF el peso actual está fuera del rango de 30 a 300 kg, la altura está fuera del rango de 100 a 250 cm, la edad está fuera del rango de 13 a 100 años, los días por semana están fuera del rango de 1 a 7, o los minutos por sesión están fuera del rango de 10 a 240, THEN THE Fitness_Coach SHALL rechazar la operación, conservar sin cambios el Fitness_Profile previo y devolver un mensaje de error en español que identifique el campo inválido y su rango válido.
6. IF el nivel enviado no es igual a `principiante`, `intermedio` ni `avanzado`, THEN THE Fitness_Coach SHALL rechazar la operación, conservar sin cambios el Fitness_Profile previo y devolver un mensaje de error en español que identifique el campo nivel como inválido.
7. IF algún Equipment_Item enviado no pertenece al catálogo definido (mancuernas, barra, banco, kettlebell, bandas, peso corporal, acceso a gimnasio, máquinas), THEN THE Fitness_Coach SHALL rechazar la operación, conservar sin cambios el Fitness_Profile previo y devolver un mensaje de error en español que identifique el equipo inválido.
8. WHEN un Authenticated_User consulta su perfil fitness, THE Fitness_Coach SHALL devolver el Fitness_Profile de ese usuario incluyendo peso actual, altura, edad, sexo cuando esté presente, nivel, la lista de Equipment_Item, los días por semana, los minutos por sesión y el objetivo actual.
9. THE Fitness_Coach SHALL exponer el peso actual, el peso objetivo, la fecha objetivo y el nivel del Fitness_Profile de forma que el Meal_Planner pueda consumirlos.

### Requirement 2: Definición de objetivos fitness

**User Story:** Como usuario, quiero definir un objetivo fitness cuantitativo o cualitativo, para que el coach oriente la rutina y el progreso hacia ese objetivo.

#### Acceptance Criteria

1. WHEN un Authenticated_User define un objetivo de tipo `weight_target` con peso objetivo entre 30 y 300 kg y fecha objetivo posterior a la fecha actual, THE Fitness_Coach SHALL almacenar el Fitness_Goal con Goal_Type `weight_target`, el peso objetivo y la fecha objetivo en el Fitness_Profile.
2. WHEN un Authenticated_User define un objetivo cualitativo o de rendimiento, THE Fitness_Coach SHALL almacenar el Fitness_Goal con su Goal_Type igual a `lose_weight`, `gain_muscle`, `maintain`, `improve_endurance` o `performance`.
3. WHERE el Goal_Type es `performance`, THE Fitness_Coach SHALL almacenar la descripción de la marca objetivo definida por el usuario con una longitud de 1 a 200 caracteres.
4. IF el Goal_Type enviado no es igual a `weight_target`, `lose_weight`, `gain_muscle`, `maintain`, `improve_endurance` ni `performance`, o si el Goal_Type es `performance` y no se proporciona descripción de marca objetivo, THEN THE Fitness_Coach SHALL rechazar la operación, conservar sin cambios el Fitness_Goal previo y devolver un mensaje de error en español que identifique el campo inválido o faltante.
5. IF un objetivo `weight_target` tiene una fecha objetivo anterior o igual a la fecha actual, THEN THE Fitness_Coach SHALL rechazar la operación, conservar sin cambios el Fitness_Goal previo y devolver un mensaje de error en español que indique que la fecha objetivo debe ser posterior a la fecha actual.
6. IF el peso objetivo de un objetivo `weight_target` está fuera del rango de 30 a 300 kg, THEN THE Fitness_Coach SHALL rechazar la operación, conservar sin cambios el Fitness_Goal previo y devolver un mensaje de error en español que identifique el peso objetivo como inválido e indique el rango válido de 30 a 300 kg.
7. WHEN un Authenticated_User actualiza su objetivo con datos válidos, THE Fitness_Coach SHALL reemplazar el objetivo activo anterior por el nuevo objetivo en el Fitness_Profile, dejando a lo más un objetivo activo por usuario.

### Requirement 3: Cálculo del ritmo objetivo y advertencias de plazo

**User Story:** Como usuario, quiero saber si mi objetivo de peso es realista en el plazo indicado, para poder ajustar mis expectativas y que el meal-planner reciba una meta calórica sensata.

#### Acceptance Criteria

1. WHEN un Authenticated_User define un objetivo `weight_target` con peso actual, peso objetivo y plazo en semanas, THE Fitness_Coach SHALL calcular el Target_Rate como (peso objetivo menos peso actual) dividido entre el plazo en semanas, expresado en kilogramos por semana con dos decimales.
2. WHEN el Fitness_Coach calcula el Target_Rate, THE Fitness_Coach SHALL derivar el ajuste calórico diario multiplicando el valor absoluto del Target_Rate por 7700 kcal por kilogramo y dividiendo entre 7 días, expresado en kcal por día como déficit si el Target_Rate es negativo o superávit si el Target_Rate es positivo.
3. IF el valor absoluto del Target_Rate excede 1,00 kg por semana o excede el 1,0 % del peso actual del usuario por semana (Healthy_Rate_Threshold), THEN THE Fitness_Coach SHALL devolver una advertencia en español que indique que el ritmo es agresivo o irreal y sugiera ampliar el plazo, conservando el Target_Rate calculado sin modificarlo.
4. IF el plazo proporcionado es cero o menor que 1 semana, o si falta el peso actual o el peso objetivo, THEN THE Fitness_Coach SHALL rechazar el cálculo y devolver un mensaje de error en español que indique qué dato es inválido o falta, sin producir un Target_Rate.
5. WHEN el Fitness_Coach devuelve cualquier respuesta que contiene el Target_Rate o el ajuste calórico diario, THE Fitness_Coach SHALL incluir un descargo en español que indique que la información es una estimación orientativa, que no constituye consejo médico y que se recomienda consultar a un profesional de la salud.
6. THE Fitness_Coach SHALL exponer el Target_Rate y el ajuste calórico diario derivado de forma que el Meal_Planner pueda consumirlos.

### Requirement 4: Resumen de actividad para calibración

**User Story:** Como usuario, quiero que el coach considere cuánto me muevo, para que la rutina no sea ni demasiado suave ni demasiado exigente para mi nivel real.

#### Acceptance Criteria

1. WHEN el Fitness_Coach construye el Activity_Summary, THE Fitness_Coach SHALL considerar únicamente los registros de Activity con fecha dentro del Activity_Window (los últimos 28 días contados hacia atrás desde la fecha actual).
2. WHEN el Fitness_Coach construye el Activity_Summary dentro del Activity_Window, THE Fitness_Coach SHALL incluir la frecuencia como el número entero de registros de Activity en la ventana, los minutos totales como la suma de la duración en minutos de esos registros, y los tipos como la lista de tipos de actividad distintos presentes en la ventana.
3. IF no existe ningún registro de Activity dentro del Activity_Window, THEN THE Fitness_Coach SHALL construir un Activity_Summary con frecuencia igual a 0, minutos totales igual a 0 y lista de tipos vacía, representando actividad nula.
4. IF uno o más registros de Activity dentro del Activity_Window carecen de duración en minutos, THEN THE Fitness_Coach SHALL contarlos en la frecuencia y en los tipos, tratando su duración como 0 minutos para el cálculo de minutos totales.

### Requirement 5: Generación de rutina de entrenamiento

**User Story:** Como usuario, quiero que el coach genere una rutina estructurada a partir de mi perfil y objetivo, para tener un plan claro de qué entrenar cada día.

#### Acceptance Criteria

1. WHEN un Authenticated_User solicita una rutina y tiene un Fitness_Profile con objetivo definido, THE Fitness_Coach SHALL invocar al LLM_Service con el Fitness_Profile, el Fitness_Goal y el Activity_Summary y persistir la rutina resultante como un Workout_Plan.
2. THE Workout_Plan SHALL contener entre 1 y 7 días, y cada día SHALL contener entre 1 y 20 ejercicios.
3. THE Workout_Plan SHALL registrar en cada ejercicio un nombre de 1 a 100 caracteres, y para cada ejercicio SHALL registrar un esquema de series de 1 a 20 con repeticiones de 1 a 100, o bien una duración de 1 a 7200 segundos, junto con un descanso de 0 a 3600 segundos.
4. THE Workout_Plan SHALL contener únicamente ejercicios cuyo equipo requerido esté incluido en los Equipment_Item del Fitness_Profile.
5. IF la rutina devuelta por el LLM_Service incluye algún ejercicio que requiere equipo no presente en los Equipment_Item del Fitness_Profile, THEN THE Fitness_Coach SHALL rechazar esa rutina, no persistirla como Workout_Plan válido, preservar sin cambios el Workout_Plan activo previo del usuario y devolver un mensaje de error en español que ofrezca reintentar.
6. WHEN el Fitness_Coach genera un Workout_Plan, THE Fitness_Coach SHALL ajustar el número de días de entrenamiento para que no exceda los días por semana declarados en la disponibilidad del Fitness_Profile.
7. IF un Authenticated_User solicita una rutina sin haber definido un Fitness_Profile con objetivo, THEN THE Fitness_Coach SHALL rechazar la operación y devolver un mensaje en español que indique que primero debe completar su perfil y objetivo.
8. WHEN un Authenticated_User genera un nuevo Workout_Plan, THE Fitness_Coach SHALL marcar el Workout_Plan anterior como inactivo y el nuevo como activo, dejando a lo más un Workout_Plan activo por usuario.
9. WHEN un Authenticated_User consulta su rutina y tiene un Workout_Plan activo, THE Fitness_Coach SHALL devolver el Workout_Plan activo de ese usuario con su estructura de días y ejercicios.
10. IF un Authenticated_User consulta su rutina y no tiene ningún Workout_Plan activo, THEN THE Fitness_Coach SHALL devolver un mensaje en español que indique que no existe una rutina activa y que puede generar una.

### Requirement 6: Manejo de fallos del LLM

**User Story:** Como usuario, quiero que el coach responda con claridad cuando la generación de rutina falla, para saber que puedo reintentar sin perder mis datos.

#### Acceptance Criteria

1. IF el LLM_Service no produce una respuesta completa dentro de los 60 segundos posteriores a la invocación durante la generación de una rutina, THEN THE Fitness_Coach SHALL abortar la generación y devolver un mensaje de error en español que ofrezca reintentar.
2. IF el LLM_Service responde con un error o no devuelve ninguna respuesta durante la generación de una rutina, THEN THE Fitness_Coach SHALL devolver un mensaje de error en español que ofrezca reintentar.
3. IF el LLM_Service devuelve contenido que no puede interpretarse como una rutina estructurada válida, THEN THE Fitness_Coach SHALL devolver un mensaje de error en español que ofrezca reintentar.
4. WHEN la generación de una rutina falla, THE Fitness_Coach SHALL preservar sin cambios el Fitness_Profile, el Fitness_Goal y el Workout_Plan activo previo del usuario.
5. WHEN un Authenticated_User reintenta la generación tras un fallo, THE Fitness_Coach SHALL reutilizar el Fitness_Profile y el Fitness_Goal existentes del usuario sin requerir que los vuelva a introducir.

### Requirement 7: Registro y visualización de peso

**User Story:** Como usuario, quiero registrar mi peso a lo largo del tiempo, para visualizar mi progreso hacia el objetivo.

#### Acceptance Criteria

1. WHEN un Authenticated_User registra un peso entre 30 y 300 kg con una fecha, THE Fitness_Coach SHALL crear un Weight_Entry asociado a ese usuario con el peso y la fecha indicados.
2. IF el peso de un Weight_Entry está fuera del rango de 30 a 300 kg, THEN THE Fitness_Coach SHALL rechazar la operación, no crear el Weight_Entry y devolver un mensaje de error en español que indique el rango válido de 30 a 300 kg.
3. WHEN un Authenticated_User registra un Weight_Entry cuya fecha es la más reciente entre sus Weight_Entry, THE Fitness_Coach SHALL actualizar el peso actual del Fitness_Profile con el peso de ese Weight_Entry.
4. WHEN un Authenticated_User consulta su historial de peso, THE Fitness_Coach SHALL devolver los Weight_Entry de ese usuario ordenados cronológicamente de forma ascendente por fecha para su visualización.
5. WHERE el Authenticated_User no tiene ningún Weight_Entry, THE Fitness_Coach SHALL devolver un historial de peso vacío.

### Requirement 8: Adherencia y progreso

**User Story:** Como usuario, quiero ver mi progreso hacia el objetivo y mi adherencia a la rutina, para saber si voy por buen camino.

#### Acceptance Criteria

1. WHEN un Authenticated_User consulta su progreso, THE Fitness_Coach SHALL devolver la serie de Weight_Entry del usuario ordenada cronológicamente.
2. WHERE el Goal_Type del Fitness_Goal es `weight_target`, THE Fitness_Coach SHALL incluir en la respuesta de progreso el peso objetivo del Fitness_Goal junto con la serie de Weight_Entry.
3. WHEN un Authenticated_User consulta su adherencia y tiene un Workout_Plan activo, THE Fitness_Coach SHALL calcular las sesiones de entrenamiento realizadas a partir de las Activity registradas dentro del periodo del Workout_Plan activo.
4. WHEN el Fitness_Coach calcula la adherencia con sesiones planificadas mayores que cero, THE Fitness_Coach SHALL expresar la adherencia como la relación entre las sesiones realizadas y las sesiones planificadas del Workout_Plan activo dentro del mismo periodo.
5. IF un Authenticated_User consulta su adherencia sin tener un Workout_Plan activo, o el Workout_Plan activo no tiene sesiones planificadas dentro del periodo, THEN THE Fitness_Coach SHALL devolver un mensaje en español que indique que no hay adherencia calculable, sin realizar una división por cero.

### Requirement 9: Interfaz web

**User Story:** Como usuario, quiero gestionar mi perfil, objetivo, peso y rutina desde el dashboard web, para administrar mi entrenamiento visualmente.

#### Acceptance Criteria

1. THE Web_Dashboard SHALL presentar una interfaz en español para crear y editar el Fitness_Profile y el Fitness_Goal.
2. WHEN un Authenticated_User envía datos válidos de perfil u objetivo desde el Web_Dashboard, THE Web_Dashboard SHALL persistirlos a través de los endpoints del Fitness_Coach.
3. IF un Authenticated_User envía datos inválidos de perfil u objetivo desde el Web_Dashboard, THEN THE Web_Dashboard SHALL mostrar el mensaje de error en español devuelto por el Fitness_Coach y conservar los datos ingresados.
4. WHEN un Authenticated_User solicita una rutina desde el Web_Dashboard, THE Web_Dashboard SHALL invocar la generación de Workout_Plan a través de los endpoints del Fitness_Coach.
5. THE Web_Dashboard SHALL presentar el Workout_Plan activo con su estructura de días y ejercicios en español.
6. THE Web_Dashboard SHALL presentar el historial de Weight_Entry como una visualización gráfica de progreso.
7. WHEN un Authenticated_User registra un peso desde el Web_Dashboard, THE Web_Dashboard SHALL crear el Weight_Entry a través de los endpoints del Fitness_Coach.

### Requirement 10: Interfaz de Telegram

**User Story:** Como usuario, quiero pedir y ver mi rutina desde el bot de Telegram con lenguaje natural, para interactuar con el coach sin abrir la web.

#### Acceptance Criteria

1. IF el chat de Telegram que solicita una rutina no está vinculado a ningún Authenticated_User, THEN THE Fitness_Coach SHALL responder en español indicando que primero debe vincular su cuenta.
2. WHEN el Telegram_Bot recibe un mensaje de un chat vinculado cuya intención es solicitar una rutina, THE Fitness_Coach SHALL generar un Workout_Plan para el Authenticated_User vinculado a ese chat y responder en español con la rutina.
3. WHEN el Telegram_Bot recibe un mensaje de un chat vinculado que solicita ver la rutina, THE Fitness_Coach SHALL responder en español con el Workout_Plan activo del usuario vinculado a ese chat.
4. WHERE un mensaje de Telegram que solicita una rutina especifica objetivo, equipo o días por semana, THE Fitness_Coach SHALL usar esos valores del mensaje para la generación del Workout_Plan.
5. WHERE un mensaje de Telegram que solicita una rutina no especifica objetivo, equipo o días por semana, THE Fitness_Coach SHALL usar los valores del Fitness_Profile del usuario para la generación del Workout_Plan.

### Requirement 11: Privacidad y descargos

**User Story:** Como usuario, quiero que mis datos corporales estén protegidos y que el coach no me dé consejo médico, para usar la herramienta con confianza.

#### Acceptance Criteria

1. THE Fitness_Coach SHALL proteger todos sus endpoints bajo `/api/fitness` requiriendo la identidad del Authenticated_User vía `get_current_user`.
2. IF una solicitud a un endpoint bajo `/api/fitness` no incluye una identidad autenticada válida, THEN THE Fitness_Coach SHALL rechazar la solicitud sin exponer datos.
3. WHEN un Authenticated_User solicita datos de perfil, peso, objetivo o rutina, THE Fitness_Coach SHALL devolver únicamente los registros que pertenecen a ese usuario, salvo que el solicitante sea administrador.
4. IF un Authenticated_User que no es administrador solicita el Fitness_Profile, los Weight_Entry, el Fitness_Goal o el Workout_Plan de otro usuario, THEN THE Fitness_Coach SHALL rechazar la solicitud sin exponer datos de ese otro usuario.
5. THE Fitness_Coach SHALL incluir en las respuestas de rutina y de objetivo de peso un descargo en español que indique que la información es orientativa, no constituye consejo ni diagnóstico médico, y que se recomienda consultar a un profesional.