# Requirements Document

## Introduction

El **Food Barcode** (buscador y escáner de alimentos) es una nueva capacidad de HabitTrack que replica la experiencia de "agregar alimento" de MyFitnessPal sobre la feature existente *meal-planner*. Añade dos formas de encontrar un alimento y agregarlo rápidamente, sin tener que teclear a mano sus datos nutricionales:

1. **Búsqueda y escaneo por código de barras.** Desde la web, el usuario escanea el código de barras del producto con la cámara del dispositivo o pega/escribe el código manualmente. El sistema consulta primero el catálogo local (`Food`) por el código de barras y, si no lo encuentra, consulta la fuente externa Open Food Facts. Con los datos obtenidos se **pre-rellena** la información nutricional por 100 g y se le muestra al usuario un paso de confirmación ("¿Es este el alimento que quieres agregar?"). Al confirmar, el alimento se agrega al inventario del usuario (y, si hace falta, se crea el `Food` correspondiente), de modo que **la próxima vez** el mismo código quede reconocido en el catálogo local.
2. **Búsqueda por nombre.** El usuario escribe el nombre de un alimento en un cuadro de búsqueda; el sistema busca primero en el catálogo local y, como respaldo (best-effort), en Open Food Facts; el usuario elige un resultado y lo agrega.

La **fuente de datos externa** es Open Food Facts (gratuita, abierta, sin clave de API). Se consulta vía su API v2 por código de barras y vía su endpoint de búsqueda por nombre, siempre con un User-Agent descriptivo y un tiempo de espera acotado. La fuente externa se trata como **best-effort**: si no responde a tiempo, falla o no contiene el producto, el sistema degrada con gracia y devuelve un mensaje en español ("no encontrado" / "la fuente externa no está disponible") sin exponer errores crudos.

La feature **reutiliza** el modelo `Food`, el inventario `UserFoodInventory`, la validación `validate_food_fields` y los flujos `create_food`/`add_inventory` del meal-planner. La única extensión del modelo de datos es una columna `barcode` (texto, única, indexada, anulable) en `Food`. La **separación de privilegios** del meal-planner se conserva: la búsqueda y el escaneo están disponibles para cualquier usuario autenticado, pero escribir en el **catálogo global** sigue siendo exclusivo del administrador; por eso, cuando un usuario no administrador agrega un alimento escaneado, este va a **su propio inventario** (creando una fila `Food` si hace falta, mediante el flujo existente de `add_inventory`), nunca como una edición privilegiada del catálogo global.

Toda la interfaz web y los mensajes de error son en español. Los identificadores de código, nombres de modelos y comentarios son en inglés. HabitTrack dirige su producto a usuarios hispanohablantes.

Alcance: columna `barcode` en `Food`; servicio de búsqueda externa Open Food Facts (por código y por nombre) con mapeo a los campos nutricionales por 100 g, timeout y degradación limpia; endpoints de búsqueda y lookup para usuarios autenticados; componente web de escáner de código de barras por cámara con entrada manual y cuadro de búsqueda por nombre, integrado en la página de Comidas; el paso de confirmación previo a agregar; la privacidad/separación de privilegios admin vs. usuario.

Fuera de alcance (ver sección "Futuro / fuera de alcance" en el diseño): el reconocimiento por foto de la etiqueta nutricional (OCR); las recetas con porciones; el escaneo desde Telegram; la edición del catálogo global por usuarios no administradores; cualquier dato nutricional por porción distinto del valor por 100 g normalizado.

## Glossary

- **Food_Barcode**: El subsistema de HabitTrack objeto de este documento, responsable de buscar alimentos por código de barras o por nombre (en el catálogo local y en Open Food Facts) y de pre-rellenar sus datos para que el usuario los confirme y los agregue a su inventario.
- **Meal_Planner**: Feature existente de HabitTrack que gestiona el catálogo de alimentos, el inventario del usuario, el perfil dietético, las metas y el plan de comidas. El Food_Barcode la reutiliza y extiende mínimamente.
- **Food**: Alimento del catálogo con información nutricional por 100 g de referencia: nombre, calorías (kcal), proteínas (g), grasas (g), carbohidratos (g) y fibra (g) opcional, más banderas dietéticas. Pertenece al catálogo global compartido. El Food_Barcode le añade una columna `barcode` opcional.
- **Food_Catalog**: El conjunto de registros Food globales compartidos entre todos los usuarios, gestionado por el administrador.
- **User_Food_Inventory**: Registro que asocia a un usuario con un Food que tiene disponible, con una cantidad opcional expresada en gramos.
- **Barcode**: Código de barras del producto (p. ej. EAN-13, UPC), representado como una cadena de dígitos. Se usa como clave de búsqueda externa y como columna opcional, única e indexada, del Food.
- **Open_Food_Facts**: Fuente de datos externa, gratuita y abierta (sin clave de API), consultada por el Food_Barcode para obtener datos nutricionales a partir de un Barcode o de un término de búsqueda por nombre.
- **Food_Lookup_Service**: Capa de servicio del backend (`app/services/food_lookup_service.py`) que consulta Open_Food_Facts con httpx asíncrono, con un tiempo de espera acotado, y mapea la respuesta a la forma de un Food (kcal/proteínas/grasas/carbohidratos/fibra por 100 g).
- **Food_Candidate**: Payload normalizado (forma de FoodIn: nombre, barcode, kcal, proteínas, grasas, carbohidratos, fibra opcional e información auxiliar como marca e imagen) que el Food_Barcode devuelve al cliente para que el usuario lo confirme antes de agregarlo.
- **Lookup_Timeout**: El tiempo máximo de espera para una consulta a Open_Food_Facts, igual a 10 segundos.
- **Confirmation_Step**: El paso de la interfaz web en el que se muestra al usuario el Food_Candidate con el texto "¿Es este el alimento que quieres agregar?" para que confirme o cancele antes de agregarlo.
- **Barcode_Scanner**: El componente web que accede a la cámara del dispositivo mediante `getUserMedia` y decodifica un Barcode a partir del vídeo, con una entrada manual de respaldo.
- **Web_Dashboard**: La interfaz web React de HabitTrack.
- **Meals_Page**: La página web de Comidas (`src/pages/MealsPage.tsx`) del meal-planner, donde se integra el Food_Barcode.
- **Authenticated_User**: Usuario que ha iniciado sesión y cuya identidad se resuelve vía `get_current_user`.
- **Administrator**: Usuario con `is_admin` verdadero, cuya identidad se resuelve vía `get_current_admin`.

## Requirements

### Requirement 1: Columna de código de barras en el catálogo

**User Story:** Como usuario, quiero que un alimento que escaneé quede asociado a su código de barras en el catálogo, para que la próxima vez que lo escanee el sistema lo reconozca al instante sin consultar la fuente externa.

#### Acceptance Criteria

1. THE Food_Barcode SHALL añadir al modelo Food una columna `barcode` de tipo texto, única, indexada y anulable.
2. WHEN un Administrator o el flujo de inventario crea un Food con un Barcode compuesto solo por dígitos y de 8 a 14 caracteres, THE Food_Barcode SHALL registrar el Food con ese Barcode.
3. WHERE un Food no tiene Barcode asociado, THE Food_Barcode SHALL almacenar el valor de `barcode` como nulo.
4. IF se intenta registrar un Food con un Barcode ya presente en otro Food del Food_Catalog, THEN THE Food_Barcode SHALL rechazar la operación, conservar el estado previo del Food_Catalog y devolver un mensaje en español que indique que ese código ya está asociado a otro alimento.
5. WHEN el Food_Barcode busca un Food por un Barcode dado, THE Food_Barcode SHALL comparar el Barcode normalizado (sin espacios al inicio o al final) de forma exacta contra la columna `barcode`.

### Requirement 2: Lookup por código de barras (catálogo local primero, luego Open Food Facts)

**User Story:** Como usuario, quiero escanear o escribir el código de barras de un producto y que el sistema me traiga sus datos nutricionales, para no tener que teclearlos a mano.

#### Acceptance Criteria

1. WHEN un Authenticated_User solicita el lookup de un Barcode y existe un Food en el Food_Catalog cuyo `barcode` coincide, THE Food_Barcode SHALL devolver un Food_Candidate construido a partir de ese Food e indicar que el origen es el catálogo local.
2. WHEN un Authenticated_User solicita el lookup de un Barcode que no coincide con ningún Food del Food_Catalog, THE Food_Barcode SHALL consultar Open_Food_Facts por ese Barcode.
3. WHEN Open_Food_Facts responde que el producto existe para el Barcode consultado, THE Food_Barcode SHALL mapear la respuesta a un Food_Candidate con nombre, Barcode y los valores de calorías, proteínas, grasas y carbohidratos por 100 g, e indicar que el origen es la fuente externa.
4. WHERE Open_Food_Facts incluye el valor de fibra por 100 g para el Barcode consultado, THE Food_Barcode SHALL incluir ese valor de fibra en el Food_Candidate.
5. WHERE Open_Food_Facts no incluye un campo nutricional por 100 g para el Barcode consultado, THE Food_Barcode SHALL representar ese campo como nulo en el Food_Candidate sin interrumpir el mapeo del resto de los campos.
6. IF un Authenticated_User solicita el lookup de un Barcode cuyo formato no es una cadena de 8 a 14 dígitos, THEN THE Food_Barcode SHALL rechazar la consulta y devolver un mensaje en español que indique que el código de barras no es válido.
7. IF Open_Food_Facts responde que no existe producto para el Barcode consultado, THEN THE Food_Barcode SHALL devolver un mensaje en español que indique que el alimento no fue encontrado.
8. IF la consulta a Open_Food_Facts supera el Lookup_Timeout o falla por un error de red o de la fuente externa, THEN THE Food_Barcode SHALL devolver un mensaje en español que indique que la fuente externa no está disponible, sin exponer un error interno.

### Requirement 3: Búsqueda por nombre (catálogo local primero, luego Open Food Facts)

**User Story:** Como usuario, quiero buscar un alimento escribiendo su nombre, para encontrarlo y agregarlo aunque no tenga el código de barras a mano.

#### Acceptance Criteria

1. WHEN un Authenticated_User busca por un término de nombre de 1 a 100 caracteres, THE Food_Barcode SHALL devolver una lista de Food_Candidate que incluya los Food del Food_Catalog cuyo nombre coincide con el término buscado.
2. WHEN una búsqueda por nombre produce menos de un resultado desde el Food_Catalog, THE Food_Barcode SHALL consultar Open_Food_Facts por el mismo término y añadir sus productos como Food_Candidate adicionales.
3. WHEN el Food_Barcode devuelve resultados de búsqueda por nombre, THE Food_Barcode SHALL incluir en cada Food_Candidate el nombre y los valores de calorías, proteínas, grasas y carbohidratos por 100 g disponibles.
4. IF un Authenticated_User busca por nombre con un término fuera del rango de 1 a 100 caracteres, THEN THE Food_Barcode SHALL rechazar la búsqueda y devolver un mensaje en español que indique que el término de búsqueda no es válido.
5. IF la consulta de búsqueda a Open_Food_Facts supera el Lookup_Timeout o falla por un error de red o de la fuente externa, THEN THE Food_Barcode SHALL devolver los resultados del Food_Catalog disponibles sin exponer un error interno.

### Requirement 4: Mapeo de la respuesta de Open Food Facts a un Food_Candidate

**User Story:** Como usuario, quiero que los datos de la fuente externa lleguen limpios y en los mismos rangos que el catálogo, para que al confirmar el alimento se guarde sin errores.

#### Acceptance Criteria

1. WHEN el Food_Lookup_Service mapea una respuesta de producto de Open_Food_Facts, THE Food_Barcode SHALL tomar las calorías por 100 g del campo de energía en kcal por 100 g y las proteínas, grasas y carbohidratos por 100 g de sus respectivos campos por 100 g.
2. WHERE un campo nutricional por 100 g está ausente o es nulo en la respuesta de Open_Food_Facts, THE Food_Barcode SHALL representar ese campo como nulo en el Food_Candidate.
3. WHERE la respuesta de Open_Food_Facts no incluye un nombre de producto, THE Food_Barcode SHALL usar como nombre del Food_Candidate el Barcode consultado.
4. WHEN el Food_Lookup_Service mapea una respuesta de producto de Open_Food_Facts, THE Food_Barcode SHALL incluir en el Food_Candidate la marca y la URL de la imagen del producto cuando estén presentes en la respuesta.
5. THE Food_Barcode SHALL enviar en cada consulta a Open_Food_Facts un encabezado User-Agent descriptivo que identifique a la aplicación.

### Requirement 5: Confirmación y alta en el inventario del usuario

**User Story:** Como usuario, quiero confirmar que el alimento encontrado es el correcto antes de agregarlo, para no guardar un producto equivocado.

#### Acceptance Criteria

1. WHEN el Food_Barcode devuelve un Food_Candidate al Web_Dashboard, THE Web_Dashboard SHALL mostrar un Confirmation_Step con el texto "¿Es este el alimento que quieres agregar?" junto con el nombre y los valores nutricionales del Food_Candidate.
2. WHEN un Authenticated_User confirma un Food_Candidate cuyo nombre no existe en el Food_Catalog y cuyos valores nutricionales por 100 g están dentro de los rangos válidos del catálogo, THE Food_Barcode SHALL crear el Food en el Food_Catalog con su Barcode y registrarlo en el User_Food_Inventory del usuario.
3. WHEN un Authenticated_User confirma un Food_Candidate cuyo nombre ya existe en el Food_Catalog, THE Food_Barcode SHALL registrar el Food existente en el User_Food_Inventory del usuario sin crear una entrada duplicada en el Food_Catalog.
4. IF un Authenticated_User confirma un Food_Candidate con valores nutricionales por 100 g fuera de los rangos válidos del catálogo, THEN THE Food_Barcode SHALL rechazar el alta, conservar el estado previo del User_Food_Inventory y del Food_Catalog y devolver un mensaje en español que indique el dato inválido.
5. WHEN un Authenticated_User cancela el Confirmation_Step, THE Web_Dashboard SHALL descartar el Food_Candidate y conservar sin cambios el User_Food_Inventory y el Food_Catalog.

### Requirement 6: Separación de privilegios (catálogo global vs. inventario propio)

**User Story:** Como responsable del producto, quiero que agregar un alimento escaneado no permita a un usuario cualquiera editar el catálogo global, para mantener la integridad de los datos compartidos.

#### Acceptance Criteria

1. WHEN un Authenticated_User solicita un lookup por Barcode o una búsqueda por nombre, THE Food_Barcode SHALL atender la solicitud sin requerir rol de Administrator.
2. WHEN un Authenticated_User sin rol de Administrator confirma un Food_Candidate, THE Food_Barcode SHALL agregar el alimento únicamente a su propio User_Food_Inventory mediante el flujo de alta de inventario, creando una fila Food si el nombre no existe.
3. THE Food_Barcode SHALL conservar la restricción de que crear, actualizar o eliminar un Food directamente en el Food_Catalog como operación de catálogo requiere rol de Administrator.

### Requirement 7: Escáner de código de barras y entrada manual en la web

**User Story:** Como usuario, quiero escanear el código con la cámara o escribirlo si no tengo cámara, para capturar el producto de la forma que me resulte más cómoda.

#### Acceptance Criteria

1. WHEN un Authenticated_User abre el Barcode_Scanner en el Meals_Page, THE Web_Dashboard SHALL solicitar acceso a la cámara mediante `getUserMedia` y, al concederse, mostrar el vídeo para decodificar un Barcode.
2. WHEN el Barcode_Scanner decodifica un Barcode a partir del vídeo, THE Web_Dashboard SHALL solicitar al Food_Barcode el lookup de ese Barcode.
3. WHEN un Authenticated_User escribe o pega un Barcode en el campo de entrada manual y lo envía, THE Web_Dashboard SHALL solicitar al Food_Barcode el lookup de ese Barcode.
4. IF el acceso a la cámara es denegado o no existe cámara disponible, THEN THE Web_Dashboard SHALL mostrar un mensaje en español y habilitar la entrada manual del Barcode como alternativa.
5. WHEN un Authenticated_User escribe un término en el cuadro de búsqueda por nombre y lo envía, THE Web_Dashboard SHALL solicitar al Food_Barcode la búsqueda por ese término y mostrar la lista de Food_Candidate resultante.
