# Requirements Document

## Introduction

El **Meal Planner** (bot chef) es una nueva capacidad de HabitTrack que ayuda al usuario a planificar sus comidas de la semana usando principalmente los alimentos que ya tiene disponibles y ajustándose a sus metas nutricionales. El usuario declara su **inventario/despensa** (qué alimentos tiene y, opcionalmente, cuánto), define sus **preferencias y restricciones dietéticas** (por ejemplo vegetariano, vegano, sin gluten, alergias) y el sistema genera, mediante el LLM de OpenRouter, un **plan de comidas semanal** (desayuno, almuerzo, cena y snacks por día) que prioriza el inventario disponible y se aproxima a las **metas de calorías y macronutrientes** del usuario dentro de una tolerancia razonable.

Las metas nutricionales se derivan del **perfil fitness** que ya expone la feature *fitness-coach*: el Fitness_Coach entrega el peso actual, el peso objetivo, la fecha objetivo, el nivel y el tipo de objetivo (`meal_planner_view`), y calcula el ajuste calórico diario (`daily_kcal_delta`/Target_Rate). A partir de ese ajuste y del objetivo, el Meal_Planner calcula las calorías objetivo diarias y la distribución de macros (más proteína y superávit para ganar músculo; déficit con proteína suficiente para adelgazar; mantenimiento para mantener). El usuario también puede **sobrescribir manualmente** sus metas de calorías y macros. Cuando no existe perfil fitness, el Meal_Planner ofrece dos caminos: completar el perfil fitness primero, o ingresar metas manuales.

La base de datos de **alimentos** (información nutricional por 100 g) se siembra con un catálogo base y se puebla progresivamente: el administrador gestiona el catálogo global compartido, mientras que cualquier usuario puede añadir alimentos a su propio inventario. El plan generado se persiste (un plan activo por usuario), se puede consultar y regenerar, y opcionalmente puede producir una **lista de compras** con lo que falta.

Toda la interfaz web, las respuestas del bot de Telegram y los mensajes de error son en español. Los identificadores de código, nombres de modelos y comentarios son en inglés. El sistema entrega estimaciones informativas, no consejo nutricional ni médico profesional, e incluye descargos apropiados; la verificación de ingredientes y alérgenos es responsabilidad del usuario.

Alcance: gestión del catálogo de alimentos (seed + añadir), inventario/despensa del usuario, derivación de metas calóricas/macros desde el perfil fitness con override manual, preferencias/restricciones dietéticas, generación del plan de comidas semanal adaptado a inventario + metas + restricciones con tolerancia calórica, alineación con el objetivo fitness, manejo de fallos del LLM, interfaces web y Telegram, privacidad (roles admin vs. usuario para catálogo global vs. inventario propio), descargos y lista de compras (opcional).

Fuera de alcance: la generación de rutinas de entrenamiento y el cálculo del ritmo de peso (feature fitness-coach, que este documento consume); el consejo o diagnóstico nutricional/médico profesional; el seguimiento automático de lo efectivamente comido y su comparación con lo planificado; integraciones con proveedores de compras o entrega de alimentos.

## Glossary

- **Meal_Planner**: El subsistema de HabitTrack objeto de este documento, responsable del catálogo de alimentos, el inventario del usuario, las preferencias/restricciones, las metas nutricionales, la generación y persistencia del plan de comidas y la lista de compras.
- **Fitness_Coach**: Feature existente de HabitTrack que gestiona el perfil fitness y el objetivo. El Meal_Planner la consume como dependencia.
- **Fitness_Profile**: Registro 1:1 con el usuario gestionado por el Fitness_Coach. Expone al Meal_Planner peso actual, peso objetivo, fecha objetivo, nivel y tipo de objetivo mediante `meal_planner_view`.
- **Target_Rate**: Salida del Fitness_Coach para objetivos de peso, que incluye el ajuste calórico diario (`daily_kcal_delta`) y su dirección (déficit, superávit o mantenimiento). Consumido por el Meal_Planner para derivar las metas.
- **Goal_Type**: Tipo de objetivo del Fitness_Profile. Valores relevantes para el Meal_Planner: `weight_target`, `lose_weight`, `gain_muscle`, `maintain`, `improve_endurance`, `performance`.
- **Food**: Alimento del catálogo con información nutricional por 100 g de referencia: nombre, calorías (kcal), proteínas (g), grasas (g), carbohidratos (g) y fibra (g) opcional. Pertenece al catálogo global compartido.
- **Food_Catalog**: El conjunto de registros Food globales compartidos entre todos los usuarios, gestionado por el administrador y sembrado con un catálogo base.
- **Seed_Catalog**: El conjunto inicial de Food cargado al inicializar el sistema.
- **User_Food_Inventory**: Registro que asocia a un usuario con un Food que tiene disponible, con una cantidad opcional expresada en gramos.
- **Dietary_Profile**: Registro 1:1 con el usuario que almacena sus preferencias y restricciones dietéticas: banderas de dieta (vegetariano, vegano, sin gluten) y una lista de alérgenos/ingredientes a evitar.
- **Diet_Flag**: Preferencia dietética booleana perteneciente al conjunto {vegetariano, vegano, sin_gluten}.
- **Allergen**: Cadena de texto de 1 a 50 caracteres que identifica un ingrediente o alérgeno que el usuario declara evitar.
- **Nutrition_Targets**: Registro 1:1 con el usuario que almacena las metas diarias de calorías (kcal) y macros (proteínas g, grasas g, carbohidratos g), junto con el origen de dichas metas (`derived` desde el Fitness_Profile o `manual` por override del usuario).
- **Calorie_Tolerance**: Margen aceptable entre las calorías totales de un día del plan y las calorías objetivo diarias, definido como ±10 % de las calorías objetivo.
- **Meal_Plan**: Plan de comidas semanal generado y persistido, con estructura de 7 días, cada día con comidas (desayuno, almuerzo, cena, snacks), cada comida con ítems (alimento, cantidad aproximada en gramos) y totales de calorías y macros por día. Un usuario tiene a lo más un Meal_Plan activo a la vez.
- **Meal**: Una comida dentro de un día del Meal_Plan, con un tipo perteneciente al conjunto {desayuno, almuerzo, cena, snack}.
- **Meal_Item**: Un ítem dentro de una Meal, compuesto por un alimento y una cantidad aproximada en gramos.
- **Shopping_List**: Lista opcional derivada de un Meal_Plan y del User_Food_Inventory, que enumera los alimentos y cantidades que faltan para cumplir el plan.
- **LLM_Service**: La integración con OpenRouter (`app/services/llm_service.py`) que recibe inventario, metas de calorías/macros y preferencias/restricciones y devuelve el Meal_Plan en JSON.
- **Web_Dashboard**: La interfaz web React de HabitTrack.
- **Telegram_Bot**: El bot de Telegram de HabitTrack.
- **Authenticated_User**: Usuario que ha iniciado sesión y cuya identidad se resuelve vía `get_current_user`.
- **Administrator**: Usuario con `is_admin` verdadero, cuya identidad se resuelve vía `get_current_admin`.

## Requirements

### Requirement 1: Catálogo de alimentos (seed y gestión por administrador)

**User Story:** Como administrador, quiero mantener un catálogo global de alimentos con información nutricional por 100 g, para que los usuarios dispongan de datos consistentes al armar su inventario y sus planes.

#### Acceptance Criteria

1. WHEN el sistema inicia y el catálogo de alimentos está vacío, THE Meal_Planner SHALL cargar el conjunto de alimentos semilla (seed) con sus valores nutricionales por 100 g.
2. WHEN el sistema inicia y el catálogo de alimentos contiene al menos un alimento, THE Meal_Planner SHALL conservar el catálogo existente sin volver a cargar el conjunto semilla (seed).
3. WHEN un Administrator crea o actualiza un Food con nombre de 1 a 100 caracteres, calorías de 0 a 900 kcal por 100 g, proteínas de 0 a 100 g por 100 g, grasas de 0 a 100 g por 100 g y carbohidratos de 0 a 100 g por 100 g, THE Meal_Planner SHALL registrar el Food en el Food_Catalog con esos valores.
4. WHERE se indica la fibra al crear o actualizar un Food, THE Meal_Planner SHALL aceptar un valor de fibra de 0 a 100 g por 100 g.
5. IF un Administrator crea o actualiza un Food con el nombre fuera del rango de 1 a 100 caracteres o con calorías, proteínas, grasas, carbohidratos o fibra fuera de los rangos permitidos, THEN THE Meal_Planner SHALL rechazar la operación, conservar el estado previo del Food_Catalog y mostrar un mensaje en español que indique el valor inválido.
6. IF un Authenticated_User sin rol de Administrator intenta crear, actualizar o eliminar un Food del Food_Catalog, THEN THE Meal_Planner SHALL rechazar la operación, conservar el estado previo del Food_Catalog y mostrar un mensaje en español que indique la falta de permisos.
7. WHEN un Authenticated_User consulta el Food_Catalog, THE Meal_Planner SHALL devolver, para cada Food, su nombre y sus valores nutricionales por 100 g.

### Requirement 2: Inventario/despensa del usuario

**User Story:** Como usuario, quiero registrar los alimentos que tengo disponibles, para que el chef arme el plan de la semana con lo que ya tengo.

#### Acceptance Criteria

1. WHEN un Authenticated_User agrega a su inventario un Food cuyo nombre ya existe en el Food_Catalog con una cantidad de 1 a 100000 g, THE Meal_Planner SHALL registrar el Food en el User_Food_Inventory del usuario con esa cantidad.
2. WHEN un Authenticated_User agrega a su inventario un Food cuyo nombre ya está presente en su inventario, THE Meal_Planner SHALL actualizar la cantidad del Food existente sin crear una entrada duplicada.
3. WHEN un Authenticated_User agrega a su inventario un alimento cuyo nombre no existe en el Food_Catalog y proporciona sus valores nutricionales por 100 g dentro de los rangos válidos del catálogo, THE Meal_Planner SHALL crear el Food en el Food_Catalog y registrarlo en el User_Food_Inventory del usuario con la cantidad indicada.
4. IF un Authenticated_User agrega a su inventario un Food con una cantidad fuera del rango de 1 a 100000 g, o un alimento nuevo sin valores nutricionales o con valores fuera de los rangos válidos del catálogo, THEN THE Meal_Planner SHALL rechazar la operación, conservar el estado previo del User_Food_Inventory y del Food_Catalog y mostrar un mensaje en español que indique el dato inválido.
5. WHEN un Authenticated_User elimina un Food de su inventario, THE Meal_Planner SHALL quitar el Food del User_Food_Inventory del usuario y conservar el Food en el Food_Catalog.
6. WHEN un Authenticated_User consulta su inventario, THE Meal_Planner SHALL devolver, para cada Food, su nombre y su cantidad disponible en gramos.

### Requirement 3: Preferencias y restricciones dietéticas

**User Story:** Como usuario, quiero declarar mis preferencias y restricciones dietéticas, para que el plan de comidas respete mi dieta y evite mis alérgenos.

#### Acceptance Criteria

1. WHEN un Authenticated_User declara una o más Diet_Flag pertenecientes al conjunto {vegetariano, vegano, sin_gluten} y uno o más Allergen, cada uno con un nombre de 1 a 50 caracteres, THE Meal_Planner SHALL registrar en el Dietary_Profile del usuario las Diet_Flag y los Allergen indicados con una relación 1:1.
2. WHEN un Authenticated_User declara un Allergen cuyo nombre ya está presente en su Dietary_Profile, THE Meal_Planner SHALL conservar una sola entrada de ese Allergen sin crear duplicados.
3. IF un Authenticated_User declara una Diet_Flag con un valor fuera del conjunto {vegetariano, vegano, sin_gluten} o un Allergen con un nombre fuera del rango de 1 a 50 caracteres, THEN THE Meal_Planner SHALL rechazar la operación, conservar el estado previo del Dietary_Profile y mostrar un mensaje en español que indique el valor inválido.
4. WHEN un Authenticated_User actualiza sus preferencias y restricciones dietéticas con datos válidos, THE Meal_Planner SHALL reemplazar por completo las Diet_Flag y los Allergen previos del Dietary_Profile por los nuevos valores indicados.
5. WHEN un Authenticated_User consulta su Dietary_Profile, THE Meal_Planner SHALL devolver las Diet_Flag y la lista de Allergen registrados.
6. WHERE el Authenticated_User no ha definido un Dietary_Profile, THE Meal_Planner SHALL tratar sus preferencias como sin Diet_Flag activas y sin Allergen declarados.

### Requirement 4: Derivación de metas nutricionales desde el perfil fitness

**User Story:** Como usuario, quiero que mis metas de calorías y macros se calculen a partir de mi objetivo fitness, para que mi alimentación se alinee con mi entrenamiento.

#### Acceptance Criteria

1. WHEN un Authenticated_User solicita derivar sus metas nutricionales y existe un Fitness_Profile con peso corporal en kg y Goal_Type definidos, THE Meal_Planner SHALL calcular un gasto de mantenimiento estimado en kcal/día a partir de los datos del Fitness_Profile y generar Nutrition_Targets con origen `derived`.
2. WHILE el Goal_Type es `gain_muscle`, THE Meal_Planner SHALL fijar las calorías objetivo diarias en el gasto de mantenimiento estimado más el superávit calórico diario del Target_Rate, y fijar la meta de proteínas en al menos 1,8 gramos por kilogramo de peso actual.
3. WHILE el Goal_Type es `lose_weight` o es `weight_target` con dirección de déficit, THE Meal_Planner SHALL fijar las calorías objetivo diarias en el gasto de mantenimiento estimado menos el déficit calórico diario del Target_Rate, y fijar la meta de proteínas en al menos 1,6 gramos por kilogramo de peso actual.
4. WHILE el Goal_Type es `maintain`, THE Meal_Planner SHALL fijar las calorías objetivo diarias iguales al gasto de mantenimiento estimado, y fijar la meta de proteínas en al menos 1,4 gramos por kilogramo de peso actual.
5. WHEN el Meal_Planner calcula las Nutrition_Targets, THE Meal_Planner SHALL repartir las calorías restantes tras cubrir la meta de proteínas entre grasas y carbohidratos usando 4 kcal por gramo de proteína, 4 kcal por gramo de carbohidrato y 9 kcal por gramo de grasa, de modo que la suma de las calorías de proteínas, grasas y carbohidratos sea igual a las calorías objetivo diarias con una tolerancia de ±10 kcal.
6. IF un Authenticated_User solicita derivar sus metas nutricionales y no existe un Fitness_Profile con peso corporal y Goal_Type definidos, THEN THE Meal_Planner SHALL rechazar la derivación, no generar Nutrition_Targets y devolver un mensaje en español que indique que primero debe completar su Fitness_Profile en el Fitness_Coach o ingresar metas manuales.
7. WHEN el Meal_Planner devuelve Nutrition_Targets derivadas de un objetivo de peso, THE Meal_Planner SHALL incluir un descargo en español que indique que las metas son una estimación orientativa y no constituyen consejo nutricional ni médico.

### Requirement 5: Override manual de metas nutricionales

**User Story:** Como usuario, quiero poder ingresar o ajustar manualmente mis metas de calorías y macros, para usar el planificador aunque no tenga perfil fitness o quiera valores propios.

#### Acceptance Criteria

1. WHEN un Authenticated_User ingresa metas manuales con calorías objetivo entre 800 y 6000 kcal inclusive, proteínas entre 0 y 500 g inclusive, grasas entre 0 y 500 g inclusive y carbohidratos entre 0 y 1000 g inclusive, THE Meal_Planner SHALL almacenar las Nutrition_Targets con origen `manual` con los valores enviados.
2. IF alguna meta manual enviada está fuera de su rango válido (calorías 800-6000, proteínas 0-500 g, grasas 0-500 g, carbohidratos 0-1000 g), THEN THE Meal_Planner SHALL rechazar la totalidad de la operación, conservar sin cambios las Nutrition_Targets previas y devolver un mensaje de error en español que identifique cada campo fuera de rango y su rango válido.
3. WHEN un Authenticated_User guarda metas manuales válidas mientras ya existen Nutrition_Targets con origen `derived`, THE Meal_Planner SHALL reemplazar las Nutrition_Targets por las manuales y registrar el origen como `manual`.
4. WHEN un Authenticated_User consulta sus Nutrition_Targets, THE Meal_Planner SHALL devolver las calorías objetivo diarias, las metas de proteínas, grasas y carbohidratos, y el origen `derived` o `manual`.
5. IF un Authenticated_User solicita generar un plan de comidas y no existen Nutrition_Targets ni un Fitness_Profile del que derivarlas, THEN THE Meal_Planner SHALL rechazar la generación del plan y devolver un mensaje en español que indique que debe derivar sus metas desde el Fitness_Coach o ingresarlas manualmente antes de generar el plan.

### Requirement 6: Generación del plan de comidas semanal

**User Story:** Como usuario, quiero que el chef genere un plan de comidas de la semana con los alimentos que tengo y mis metas, para saber qué comer cada día sin planificarlo yo.

#### Acceptance Criteria

1. WHEN un Authenticated_User solicita generar un plan de comidas y existen Nutrition_Targets definidas y el inventario contiene al menos un Food, THE Meal_Planner SHALL invocar al LLM_Service proporcionando el User_Food_Inventory, las Nutrition_Targets y el Dietary_Profile del usuario.
2. WHEN el LLM_Service devuelve un plan interpretable y dentro de tolerancia, THE Meal_Planner SHALL persistir el Meal_Plan y marcarlo como el único Meal_Plan activo del usuario.
3. THE Meal_Plan SHALL contener exactamente 7 días, y cada día SHALL contener al menos una Meal con tipo perteneciente al conjunto {desayuno, almuerzo, cena, snack}.
4. THE Meal_Planner SHALL componer cada Meal con uno o más Meal_Item, donde cada Meal_Item especifica un alimento y una cantidad entre 1 y 100000 gramos inclusive.
5. THE Meal_Planner SHALL calcular y almacenar, para cada uno de los 7 días, los totales de calorías, proteínas, carbohidratos y grasas.
6. WHEN el Meal_Planner genera el plan, THE Meal_Planner SHALL priorizar los alimentos presentes en el User_Food_Inventory del usuario por sobre alimentos ausentes del inventario.
7. WHEN el Meal_Planner acepta un Meal_Plan generado, THE Meal_Planner SHALL verificar que las calorías totales de cada día se encuentren dentro de la Calorie_Tolerance de ±10 % respecto de las calorías objetivo diarias de las Nutrition_Targets.
8. IF las calorías totales de al menos un día del Meal_Plan generado quedan fuera de la Calorie_Tolerance de ±10 %, THEN THE Meal_Planner SHALL rechazar ese Meal_Plan, conservar el Meal_Plan activo previo sin modificarlo y devolver un mensaje de error en español que indique el rechazo por incumplimiento de tolerancia y ofrezca regenerar el plan.
9. IF un Authenticated_User solicita generar un plan y no existen Nutrition_Targets definidas, THEN THE Meal_Planner SHALL rechazar la solicitud y devolver un mensaje en español que indique que debe definir sus metas nutricionales antes de generar el plan.
10. IF un Authenticated_User solicita generar un plan y el inventario no contiene ningún Food, THEN THE Meal_Planner SHALL rechazar la solicitud y devolver un mensaje en español que indique que debe registrar alimentos en su inventario antes de generar el plan.
11. THE Meal_Planner SHALL mantener a lo más un Meal_Plan activo por usuario en todo momento.
12. WHEN un Authenticated_User consulta su plan de comidas y existe un Meal_Plan activo, THE Meal_Planner SHALL devolver el Meal_Plan activo con sus 7 días, comidas, Meal_Item y totales por día.
13. IF un Authenticated_User consulta su plan de comidas y no existe ningún Meal_Plan activo, THEN THE Meal_Planner SHALL devolver un mensaje en español que indique que no existe un plan activo y que puede generar uno.

### Requirement 7: Respeto de restricciones dietéticas en el plan

**User Story:** Como usuario con restricciones dietéticas, quiero que el plan nunca incluya alimentos que no puedo comer, para poder seguirlo con seguridad.

#### Acceptance Criteria

1. IF la Diet_Flag `vegetariano` está activa en el Dietary_Profile del usuario y el Meal_Plan generado incluye al menos un Meal_Item cuyo alimento sea carne o pescado, THEN THE Meal_Planner SHALL rechazar el Meal_Plan, conservar el Meal_Plan activo previo sin modificarlo y devolver un mensaje de error en español que indique el rechazo por incumplimiento de la restricción vegetariana y ofrezca regenerar el plan.
2. IF la Diet_Flag `vegano` está activa en el Dietary_Profile del usuario y el Meal_Plan generado incluye al menos un Meal_Item cuyo alimento sea de origen animal, THEN THE Meal_Planner SHALL rechazar el Meal_Plan, conservar el Meal_Plan activo previo sin modificarlo y devolver un mensaje de error en español que indique el rechazo por incumplimiento de la restricción vegana y ofrezca regenerar el plan.
3. IF la Diet_Flag `sin_gluten` está activa en el Dietary_Profile del usuario y el Meal_Plan generado incluye al menos un Meal_Item cuyo alimento contenga gluten, THEN THE Meal_Planner SHALL rechazar el Meal_Plan, conservar el Meal_Plan activo previo sin modificarlo y devolver un mensaje de error en español que indique el rechazo por incumplimiento de la restricción sin gluten y ofrezca regenerar el plan.
4. IF el Dietary_Profile del usuario declara al menos un Allergen y el Meal_Plan generado incluye un Meal_Item cuyo alimento coincide con un Allergen declarado, THEN THE Meal_Planner SHALL rechazar el Meal_Plan, conservar el Meal_Plan activo previo sin modificarlo y devolver un mensaje de error en español que indique el rechazo por incluir un alérgeno declarado y ofrezca regenerar el plan.

### Requirement 8: Alineación con el objetivo fitness

**User Story:** Como usuario, quiero que mi plan de comidas se alinee con mi objetivo fitness, para cerrar el ciclo de entrenamiento y nutrición.

#### Acceptance Criteria

1. WHILE el Goal_Type del Fitness_Profile es `gain_muscle` y las Nutrition_Targets tienen origen `derived`, THE Meal_Planner SHALL generar un Meal_Plan cuyas calorías objetivo diarias sean mayores que el gasto de mantenimiento y cuya meta diaria de proteínas sea de al menos 1,8 gramos por kilogramo de peso actual.
2. WHILE el Goal_Type del Fitness_Profile es `lose_weight` o es `weight_target` con dirección de déficit y las Nutrition_Targets tienen origen `derived`, THE Meal_Planner SHALL generar un Meal_Plan cuyas calorías objetivo diarias sean menores que el gasto de mantenimiento.
3. WHEN un Authenticated_User posee Nutrition_Targets con origen `derived` y solicita derivar sus metas o generar un plan después de haber actualizado su objetivo en el Fitness_Coach, THE Meal_Planner SHALL recalcular las Nutrition_Targets `derived` usando el peso actual, el tipo de objetivo y el ajuste calórico diario vigentes en el Fitness_Coach antes de generar el plan.
4. WHERE las Nutrition_Targets tienen origen `manual`, THE Meal_Planner SHALL usar los valores manuales para la generación del plan aunque difieran del objetivo fitness del usuario.
5. IF un Authenticated_User con Nutrition_Targets de origen `derived` solicita derivar o generar un plan y el Fitness_Coach ya no expone un Fitness_Profile con objetivo definido, THEN THE Meal_Planner SHALL rechazar el recálculo `derived`, preservar sin cambios el Meal_Plan activo previo y devolver un mensaje en español que indique que debe completar su objetivo en el Fitness_Coach o ingresar metas manuales.

### Requirement 9: Manejo de fallos del LLM

**User Story:** Como usuario, quiero que el chef responda con claridad cuando la generación del plan falla, para saber que puedo reintentar sin perder mis datos.

#### Acceptance Criteria

1. IF el LLM_Service no produce una respuesta completa dentro de los 60 segundos posteriores a la invocación durante la generación de un plan, THEN THE Meal_Planner SHALL abortar la generación y devolver un mensaje de error en español que indique que la generación no se completó y que ofrezca reintentar.
2. IF el LLM_Service responde con un error o no devuelve ninguna respuesta durante la generación de un plan, THEN THE Meal_Planner SHALL abortar la generación y devolver un mensaje de error en español que indique que la generación falló y que ofrezca reintentar.
3. IF el LLM_Service devuelve contenido que no puede interpretarse como un Meal_Plan estructurado válido, THEN THE Meal_Planner SHALL descartar la respuesta y devolver un mensaje de error en español que indique que la generación no pudo interpretarse y que ofrezca reintentar.
4. WHEN la generación de un plan falla por cualquier causa, THE Meal_Planner SHALL preservar sin cambios el User_Food_Inventory, el Dietary_Profile, las Nutrition_Targets y el Meal_Plan activo previo del usuario.
5. WHEN un Authenticated_User reintenta la generación tras un fallo, THE Meal_Planner SHALL reutilizar el User_Food_Inventory, el Dietary_Profile y las Nutrition_Targets existentes del usuario sin requerir que los vuelva a introducir.

### Requirement 10: Interfaz web

**User Story:** Como usuario, quiero gestionar mi inventario, preferencias y metas y ver mi plan desde el dashboard web, para administrar mi alimentación visualmente.

#### Acceptance Criteria

1. THE Web_Dashboard SHALL presentar una interfaz en español para gestionar el User_Food_Inventory, el Dietary_Profile y las Nutrition_Targets.
2. WHEN un Authenticated_User envía datos válidos de inventario, preferencias o metas desde el Web_Dashboard, THE Web_Dashboard SHALL persistirlos a través de los endpoints del Meal_Planner.
3. IF un Authenticated_User envía datos inválidos desde el Web_Dashboard, THEN THE Web_Dashboard SHALL mostrar el mensaje de error en español devuelto por el Meal_Planner y conservar sin modificar los valores que el usuario había ingresado en el formulario.
4. WHEN un Authenticated_User solicita un plan de comidas desde el Web_Dashboard, THE Web_Dashboard SHALL invocar la generación del Meal_Plan a través de los endpoints del Meal_Planner.
5. WHEN un Authenticated_User visualiza un Meal_Plan activo en el Web_Dashboard, THE Web_Dashboard SHALL presentar su estructura de días, comidas, ítems y totales por día en español, incluyendo el descargo correspondiente.
6. IF un Authenticated_User abre la vista del plan en el Web_Dashboard sin poseer un Meal_Plan activo, THEN THE Web_Dashboard SHALL mostrar un mensaje en español que indique que no existe un plan activo y ofrezca generar uno.

### Requirement 11: Interfaz de Telegram

**User Story:** Como usuario, quiero pedir mi plan de comidas desde el bot de Telegram con lenguaje natural, para interactuar con el chef sin abrir la web.

#### Acceptance Criteria

1. IF el chat de Telegram que solicita un plan de comidas no está vinculado a ningún Authenticated_User, THEN THE Meal_Planner SHALL responder en español indicando que primero debe vincular su cuenta.
2. WHEN el Telegram_Bot recibe un mensaje de un chat vinculado cuya intención es solicitar la generación de un plan de comidas, THE Meal_Planner SHALL generar un Meal_Plan para el Authenticated_User vinculado a ese chat y responder en español con el plan.
3. WHEN el Telegram_Bot recibe un mensaje de un chat vinculado cuya intención es ver el plan de comidas, THE Meal_Planner SHALL responder en español con el Meal_Plan activo del usuario vinculado a ese chat.
4. WHERE un mensaje de Telegram que solicita un plan de comidas enumera alimentos disponibles, THE Meal_Planner SHALL añadir cada alimento al User_Food_Inventory del usuario vinculado antes de generar el plan, creando el Food en el Food_Catalog con los valores nutricionales indicados en el mensaje cuando el alimento no exista en el catálogo.
5. WHERE un mensaje de Telegram que solicita un plan de comidas indica un objetivo del conjunto {ganar músculo, adelgazar, mantener} y el usuario vinculado no posee Nutrition_Targets con origen `manual`, THE Meal_Planner SHALL derivar las Nutrition_Targets aplicando ese objetivo antes de generar el plan.
6. IF el Telegram_Bot recibe un mensaje de un chat vinculado cuya intención de plan de comidas no puede resolverse, o el usuario vinculado no posee Nutrition_Targets ni inventario con al menos un Food, THEN THE Meal_Planner SHALL responder en español indicando la acción que el usuario debe realizar para poder generar o ver el plan.

### Requirement 12: Privacidad y descargos

**User Story:** Como usuario, quiero que mis datos dietéticos y de inventario estén protegidos y que el chef no me dé consejo nutricional profesional, para usar la herramienta con confianza.

#### Acceptance Criteria

1. THE Meal_Planner SHALL proteger todos sus endpoints bajo `/api/meals` requiriendo la identidad del Authenticated_User vía `get_current_user`.
2. IF una solicitud a un endpoint bajo `/api/meals` no incluye una identidad autenticada válida, THEN THE Meal_Planner SHALL rechazar la solicitud sin devolver ningún dato de inventario, preferencias, metas ni plan.
3. WHEN un Authenticated_User solicita su inventario, preferencias, metas o plan, THE Meal_Planner SHALL devolver únicamente los registros que pertenecen a ese usuario, salvo que el solicitante sea Administrator.
4. IF un Authenticated_User que no es Administrator solicita el User_Food_Inventory, el Dietary_Profile, las Nutrition_Targets o el Meal_Plan de otro usuario, THEN THE Meal_Planner SHALL rechazar la solicitud y devolver un mensaje de error en español sin incluir ni confirmar la existencia de datos de ese otro usuario.
5. THE Meal_Planner SHALL restringir la creación, actualización y eliminación de Food en el Food_Catalog global a solicitudes de un Administrator vía `get_current_admin`, permitiendo a cualquier Authenticated_User gestionar únicamente su propio User_Food_Inventory.
6. THE Meal_Planner SHALL incluir en las respuestas de Meal_Plan y de Nutrition_Targets un descargo en español que indique que la información es orientativa, no constituye consejo nutricional ni médico, y que el usuario es responsable de verificar los ingredientes y alérgenos de los alimentos.

### Requirement 13: Lista de compras (opcional)

**User Story:** Como usuario, quiero obtener una lista de lo que me falta comprar a partir de mi plan, para hacer las compras de la semana fácilmente. (Requisito opcional / nice-to-have.)

#### Acceptance Criteria

1. WHEN un Authenticated_User solicita la Shopping_List de su Meal_Plan activo, THE Meal_Planner SHALL calcular por cada alimento la cantidad total en gramos requerida en el Meal_Plan menos la cantidad disponible en el User_Food_Inventory de ese usuario.
2. WHERE la cantidad total requerida de un alimento en el Meal_Plan es mayor que la cantidad disponible en el User_Food_Inventory, THE Meal_Planner SHALL incluir ese alimento en la Shopping_List con la cantidad faltante redondeada al gramo entero superior, con un mínimo de 1 gramo.
3. WHERE la cantidad disponible de un alimento en el User_Food_Inventory es mayor o igual que la cantidad total requerida en el Meal_Plan, THE Meal_Planner SHALL excluir ese alimento de la Shopping_List.
4. IF un Authenticated_User solicita la Shopping_List sin poseer un Meal_Plan activo, THEN THE Meal_Planner SHALL devolver un mensaje en español que indique que primero debe generar un plan de comidas.
5. WHERE un alimento requerido por el Meal_Plan está presente en el User_Food_Inventory sin una cantidad declarada, THE Meal_Planner SHALL tratar su cantidad disponible como 0 gramos al calcular la cantidad faltante de ese alimento.