# Requirements Document

## Introduction

El **Food Add Redesign** (rediseño de "agregar alimento") es una nueva capacidad de HabitTrack que reemplaza la experiencia actual de agregar alimentos en la página de Comidas (`src/pages/MealsPage.tsx`). Hoy esa página muestra el catálogo completo y la despensa como listas largas, usa un formulario de inventario siempre visible y carga de golpe el escáner de código de barras; el usuario reportó que no entiende el "catálogo", que no quiere ver toda la lista y que la cámara aparece de inmediato. Este rediseño construye **sobre** las features existentes *meal-planner* y *food-barcode* sin reimplementarlas: reutiliza el modelo `Food` (nutrición por 100 g y banderas dietéticas), el inventario `UserFoodInventory`, la validación `validate_food_fields`, los flujos `create_food`/`add_inventory`, el `Food_Lookup_Service` (Open Food Facts) y los endpoints de lookup por código de barras y búsqueda por nombre.

El rediseño aporta seis cambios de experiencia:

1. **Búsqueda incremental unificada.** En lugar de mostrar la lista completa del catálogo y la despensa, el usuario escribe un término y los resultados aparecen a medida que teclea (con un retardo breve que evita disparar una consulta por cada tecla). La búsqueda cubre, en un único listado de resultados, el catálogo local (`Food`), el inventario propio del usuario, las recetas del usuario y, como respaldo best-effort, Open Food Facts por nombre.
2. **Formulario dinámico en lugar de modal.** Un botón "Crear nuevo" carga de forma diferida (inline, sin modal) un formulario para crear o agregar un alimento nuevo cuando ningún resultado coincide.
3. **Marca por producto.** Un mismo alimento puede existir con distintas marcas; el usuario puede asociar una marca (`brand`) opcional al alimento. `Food` ya recibe la marca desde Open Food Facts en *food-barcode* como dato auxiliar del candidato, pero no la persiste; este rediseño añade una columna `brand` opcional al modelo `Food` y la expone en el alta y en los resultados.
4. **Recetas.** El usuario puede crear recetas combinando varios ingredientes (varios `Food` con gramos); la nutrición total de la receta se deriva de la suma ponderada de sus ingredientes. Las recetas se buscan y aparecen en la búsqueda incremental junto con los alimentos, y una receta puede agregarse al inventario/plan como una sola unidad.
5. **Cámara de carga diferida.** El escáner de código de barras (`Barcode_Scanner`, `@zxing/browser`) se carga de forma diferida (code-splitting / import dinámico) y solo se inicializa cuando el usuario elige la acción de escanear, en lugar de montarse al abrir la página.
6. **Flujo unificado "Agregar alimento".** Un panel inline con acciones/pestañas reúne escanear código, buscar por nombre, buscar en el inventario, buscar en recetas o crear nuevo (alimento o receta). La distribución se inspira en la experiencia de "agregar alimento" de MapMyFitness, pero se construye a la manera de HabitTrack, sin copiar su interfaz.

Las banderas dietéticas `is_meat`, `is_animal` y `has_gluten` del modelo `Food` **se conservan tal cual**: el *meal-planner* las usa en `check_dietary_compliance` junto con el `Dietary_Profile` para validar los planes, y eliminarlas rompería esa feature. El rediseño no las quita del modelo ni de la validación; el nuevo formulario puede no destacarlas, pero siguen disponibles.

La **separación de privilegios** de *meal-planner* y *food-barcode* se mantiene: buscar y escanear están disponibles para cualquier usuario autenticado; escribir en el **catálogo global** sigue siendo exclusivo del administrador; un usuario no administrador que agrega un alimento lo agrega a su propio inventario (creando una fila `Food` si hace falta mediante el flujo `add_inventory`). Las recetas son privadas de cada usuario.

Toda la interfaz web y los mensajes de error son en español. Los identificadores de código, nombres de modelos y comentarios son en inglés. HabitTrack dirige su producto a usuarios hispanohablantes.

Alcance: columna `brand` opcional en `Food`; modelos `Recipe` y `Recipe_Ingredient` con nutrición agregada derivada; endpoint de búsqueda incremental unificada; endpoints CRUD de recetas y de alta de una receta al inventario; componente web de flujo unificado "Agregar alimento" con carga diferida de la cámara y búsqueda incremental con retardo; privacidad y separación de privilegios.

Fuera de alcance: el reconocimiento por foto de la etiqueta nutricional (OCR); el escaneo o la creación de recetas desde Telegram; la edición del catálogo global por usuarios no administradores; la generación del plan de comidas (la gestiona *meal-planner*); el seguimiento de lo efectivamente comido; cualquier dato nutricional por porción distinto del valor por 100 g normalizado.

## Glossary

- **Food_Add_Redesign**: El subsistema de HabitTrack objeto de este documento, responsable del flujo unificado de "Agregar alimento" en la Meals_Page: búsqueda incremental unificada, formulario dinámico de alta, recetas y carga diferida del escáner.
- **Meal_Planner**: Feature existente de HabitTrack que gestiona el catálogo de alimentos, el inventario del usuario, el perfil dietético, las metas y el plan de comidas. El Food_Add_Redesign la reutiliza y extiende mínimamente.
- **Food_Barcode**: Feature existente que añade la columna `barcode` a Food, el Food_Lookup_Service (Open Food Facts por código y por nombre) y los endpoints de lookup y búsqueda. El Food_Add_Redesign la reutiliza.
- **Food**: Alimento del catálogo con información nutricional por 100 g: nombre, calorías (kcal), proteínas (g), grasas (g), carbohidratos (g) y fibra (g) opcional, más las banderas dietéticas `is_meat`, `is_animal`, `has_gluten` y la columna opcional `barcode`. El Food_Add_Redesign le añade una columna `brand` opcional.
- **Brand**: Marca comercial opcional asociada a un Food, representada como una cadena de 1 a 100 caracteres. Permite distinguir productos del mismo alimento provenientes de distintos fabricantes.
- **Food_Catalog**: El conjunto de registros Food globales compartidos entre todos los usuarios, gestionado por el Administrator.
- **User_Food_Inventory**: Registro que asocia a un Authenticated_User con un Food que tiene disponible, con una cantidad opcional expresada en gramos.
- **Recipe**: Preparación creada por un Authenticated_User que combina uno o más Recipe_Ingredient. Pertenece a su autor (privada) y tiene un nombre de 1 a 100 caracteres y una nutrición agregada por 100 g derivada de sus ingredientes.
- **Recipe_Ingredient**: Componente de una Recipe que asocia un Food con una cantidad en gramos de 1 a 100000. La nutrición de la Recipe se deriva de la suma de sus Recipe_Ingredient.
- **Recipe_Nutrition**: Los valores nutricionales por 100 g (kcal, proteínas, grasas, carbohidratos y fibra) de una Recipe, calculados como la suma de los aportes nutricionales de cada Recipe_Ingredient dividida entre la masa total de la Recipe y normalizada a 100 g.
- **Search_Result**: Elemento devuelto por la búsqueda incremental unificada, con un `kind` perteneciente al conjunto {`catalog`, `inventory`, `recipe`, `off`}, un nombre, la Brand cuando exista y los valores nutricionales por 100 g disponibles.
- **Incremental_Search**: La búsqueda que devuelve Search_Result a medida que el usuario escribe, consultando el Food_Catalog, el User_Food_Inventory del usuario, sus Recipe y, como respaldo, Open_Food_Facts por nombre.
- **Search_Debounce**: El retardo de 300 milisegundos que el Web_Dashboard espera tras la última pulsación de tecla antes de disparar una Incremental_Search, para no emitir una consulta por cada tecla.
- **Open_Food_Facts**: Fuente de datos externa, gratuita y abierta (sin clave de API), consultada por el Food_Lookup_Service para obtener datos nutricionales por nombre o por Barcode.
- **Food_Lookup_Service**: Capa de servicio del backend (`app/services/food_lookup_service.py`) que consulta Open_Food_Facts con httpx asíncrono, con un Lookup_Timeout acotado, y mapea la respuesta a la forma de un Food_Candidate. El Food_Add_Redesign la reutiliza sin modificarla.
- **Food_Candidate**: Payload normalizado (nombre, barcode, kcal, proteínas, grasas, carbohidratos, fibra opcional, Brand e imagen) que el Food_Barcode devuelve para confirmar antes de agregar.
- **Lookup_Timeout**: El tiempo máximo de espera para una consulta a Open_Food_Facts, igual a 10 segundos.
- **Barcode_Scanner**: El componente web (`src/components/BarcodeScanner.tsx`, `@zxing/browser`) que accede a la cámara mediante `getUserMedia` y decodifica un Barcode, con entrada manual de respaldo. El Food_Add_Redesign lo carga de forma diferida.
- **Barcode**: Código de barras del producto (EAN/UPC), una cadena de 8 a 14 dígitos.
- **Add_Food_Panel**: El panel inline (sin modal) de la Meals_Page que reúne las acciones de agregar alimento: escanear, buscar por nombre, buscar en el inventario, buscar en recetas o crear nuevo.
- **Create_Food_Form**: El formulario, cargado de forma diferida e inline, para crear o agregar un Food nuevo con su nutrición por 100 g, su Brand opcional y sus banderas dietéticas.
- **Create_Recipe_Form**: El formulario, cargado de forma diferida e inline, para crear una Recipe seleccionando Food como Recipe_Ingredient con sus gramos.
- **Web_Dashboard**: La interfaz web React de HabitTrack.
- **Meals_Page**: La página web de Comidas (`src/pages/MealsPage.tsx`) donde se integra el Food_Add_Redesign.
- **Authenticated_User**: Usuario que ha iniciado sesión y cuya identidad se resuelve vía `get_current_user`.
- **Administrator**: Usuario con `is_admin` verdadero, cuya identidad se resuelve vía `get_current_admin`.

## Requirements

### Requirement 1: Marca (brand) opcional en el catálogo

**User Story:** Como usuario, quiero asociar una marca a un alimento, para distinguir productos del mismo alimento provenientes de distintos fabricantes.

#### Acceptance Criteria

1. THE Food_Add_Redesign SHALL añadir al modelo Food una columna `brand` de tipo texto, anulable, con una longitud máxima de 100 caracteres.
2. WHEN un Authenticated_User crea o agrega un Food con una Brand de 1 a 100 caracteres, THE Food_Add_Redesign SHALL registrar el Food con esa Brand.
3. WHERE un Food se crea o se agrega sin Brand, THE Food_Add_Redesign SHALL almacenar el valor de `brand` como nulo.
4. IF un Authenticated_User crea o agrega un Food con una Brand cuya longitud supera los 100 caracteres, THEN THE Food_Add_Redesign SHALL rechazar la operación, conservar el estado previo del Food_Catalog y del User_Food_Inventory y devolver un mensaje en español que indique que la marca no es válida.
5. WHEN el Food_Add_Redesign devuelve un Food en un Search_Result o en el detalle del catálogo, THE Food_Add_Redesign SHALL incluir la Brand del Food cuando esté presente.

### Requirement 2: Búsqueda incremental unificada

**User Story:** Como usuario, quiero que los resultados aparezcan a medida que escribo, buscando a la vez en el catálogo, mi inventario y mis recetas, para no tener que revisar toda la lista.

#### Acceptance Criteria

1. WHEN un Authenticated_User escribe un término de búsqueda de 1 a 100 caracteres, THE Food_Add_Redesign SHALL devolver una lista de Search_Result que incluya los Food del Food_Catalog, los Food del User_Food_Inventory del usuario y las Recipe del usuario cuyo nombre coincida con el término.
2. WHEN una Incremental_Search produce menos de un resultado local entre el Food_Catalog, el User_Food_Inventory y las Recipe del usuario, THE Food_Add_Redesign SHALL consultar Open_Food_Facts por el mismo término y añadir sus productos como Search_Result adicionales con `kind` igual a `off`.
3. WHEN el Food_Add_Redesign devuelve un Search_Result, THE Food_Add_Redesign SHALL incluir en cada Search_Result su `kind`, su nombre, la Brand cuando exista y los valores de calorías, proteínas, grasas y carbohidratos por 100 g disponibles.
4. THE Web_Dashboard SHALL esperar el Search_Debounce de 300 milisegundos tras la última pulsación de tecla del Authenticated_User antes de solicitar al Food_Add_Redesign una Incremental_Search.
5. IF un Authenticated_User escribe un término de búsqueda fuera del rango de 1 a 100 caracteres, THEN THE Food_Add_Redesign SHALL rechazar la búsqueda y devolver un mensaje en español que indique que el término de búsqueda no es válido.
6. IF la consulta de búsqueda a Open_Food_Facts supera el Lookup_Timeout o falla por un error de red o de la fuente externa, THEN THE Food_Add_Redesign SHALL devolver los Search_Result locales disponibles sin exponer un error interno.
7. WHEN un Authenticated_User distinto del Administrator ejecuta una Incremental_Search, THE Food_Add_Redesign SHALL incluir en los Search_Result de `kind` igual a `inventory` o a `recipe` únicamente registros que pertenezcan a ese usuario.

### Requirement 3: Formulario dinámico de alta de alimento

**User Story:** Como usuario, quiero un formulario que se cargue al pulsar un botón en vez de un modal, para crear un alimento nuevo solo cuando lo necesito.

#### Acceptance Criteria

1. WHEN un Authenticated_User pulsa la acción "Crear nuevo" en el Add_Food_Panel, THE Web_Dashboard SHALL cargar de forma diferida el Create_Food_Form e insertarlo en línea dentro del Add_Food_Panel sin abrir un modal.
2. WHEN un Authenticated_User envía el Create_Food_Form con un nombre de 1 a 100 caracteres, valores nutricionales por 100 g dentro de los rangos válidos del catálogo y una Brand opcional válida, THE Food_Add_Redesign SHALL agregar el Food a su User_Food_Inventory mediante el flujo de alta de inventario, creando el Food en el Food_Catalog si su nombre no existe.
3. WHEN el Create_Food_Form crea un Food nuevo, THE Food_Add_Redesign SHALL conservar las banderas dietéticas `is_meat`, `is_animal` y `has_gluten` indicadas en el formulario con sus valores por defecto en falso cuando no se indiquen.
4. IF un Authenticated_User envía el Create_Food_Form con un valor nutricional por 100 g fuera de los rangos válidos del catálogo o con un nombre fuera del rango de 1 a 100 caracteres, THEN THE Food_Add_Redesign SHALL rechazar el alta, conservar el estado previo del Food_Catalog y del User_Food_Inventory y devolver un mensaje en español que indique el dato inválido.
5. WHEN un Authenticated_User cancela el Create_Food_Form, THE Web_Dashboard SHALL ocultar el formulario y conservar sin cambios el Food_Catalog y el User_Food_Inventory.

### Requirement 4: Creación de recetas a partir de ingredientes

**User Story:** Como usuario, quiero crear recetas combinando varios alimentos con sus gramos, para reutilizarlas como una sola unidad al armar mi plan.

#### Acceptance Criteria

1. WHEN un Authenticated_User crea una Recipe con un nombre de 1 a 100 caracteres y uno o más Recipe_Ingredient, cada uno con un Food existente y una cantidad de 1 a 100000 gramos, THE Food_Add_Redesign SHALL registrar la Recipe y sus Recipe_Ingredient asociados al usuario.
2. WHEN el Food_Add_Redesign registra o consulta una Recipe, THE Food_Add_Redesign SHALL calcular la Recipe_Nutrition por 100 g como la suma de los aportes de calorías, proteínas, grasas y carbohidratos de cada Recipe_Ingredient dividida entre la masa total en gramos de la Recipe y multiplicada por 100.
3. IF un Authenticated_User crea una Recipe con el nombre fuera del rango de 1 a 100 caracteres, sin ningún Recipe_Ingredient, o con un Recipe_Ingredient cuya cantidad esté fuera del rango de 1 a 100000 gramos, THEN THE Food_Add_Redesign SHALL rechazar la operación, no registrar la Recipe y devolver un mensaje en español que indique el dato inválido.
4. IF un Authenticated_User crea una Recipe que referencia un Food que no existe en el Food_Catalog, THEN THE Food_Add_Redesign SHALL rechazar la operación, no registrar la Recipe y devolver un mensaje en español que indique que el ingrediente no existe.
5. WHEN un Authenticated_User consulta sus Recipe, THE Food_Add_Redesign SHALL devolver, para cada Recipe, su nombre, sus Recipe_Ingredient con el nombre del Food y los gramos, y su Recipe_Nutrition por 100 g.
6. WHEN un Authenticated_User elimina una Recipe propia, THE Food_Add_Redesign SHALL quitar la Recipe y sus Recipe_Ingredient y conservar los Food referenciados en el Food_Catalog.

### Requirement 5: Agregar una receta al inventario como unidad

**User Story:** Como usuario, quiero agregar una receta completa a mi inventario de una vez, para no tener que agregar cada ingrediente por separado.

#### Acceptance Criteria

1. WHEN un Authenticated_User agrega una Recipe propia a su User_Food_Inventory con una cantidad de 1 a 100000 gramos, THE Food_Add_Redesign SHALL registrar la Recipe en el User_Food_Inventory del usuario como una sola unidad con esa cantidad.
2. WHEN un Authenticated_User agrega una Recipe que ya está presente en su User_Food_Inventory, THE Food_Add_Redesign SHALL actualizar la cantidad de la Recipe existente sin crear una entrada duplicada.
3. IF un Authenticated_User agrega una Recipe a su inventario con una cantidad fuera del rango de 1 a 100000 gramos, THEN THE Food_Add_Redesign SHALL rechazar la operación, conservar el estado previo del User_Food_Inventory y devolver un mensaje en español que indique el dato inválido.
4. IF un Authenticated_User agrega al inventario una Recipe que no le pertenece, THEN THE Food_Add_Redesign SHALL rechazar la operación y devolver un mensaje en español sin confirmar la existencia de esa Recipe.

### Requirement 6: Carga diferida del escáner de código de barras

**User Story:** Como usuario, quiero que la cámara no aparezca de golpe al abrir la página, sino solo cuando elija escanear, para que la pantalla no muestre todo de una vez.

#### Acceptance Criteria

1. WHEN un Authenticated_User abre la Meals_Page, THE Web_Dashboard SHALL mostrar el Add_Food_Panel sin montar el Barcode_Scanner ni solicitar acceso a la cámara.
2. WHEN un Authenticated_User selecciona la acción de escanear en el Add_Food_Panel, THE Web_Dashboard SHALL importar de forma diferida el Barcode_Scanner y montarlo en línea.
3. WHILE el Barcode_Scanner se está importando de forma diferida, THE Web_Dashboard SHALL mostrar un indicador de carga en español.
4. WHEN el Barcode_Scanner decodifica o el Authenticated_User envía un Barcode, THE Web_Dashboard SHALL solicitar al Food_Barcode el lookup de ese Barcode.
5. WHEN un Authenticated_User cierra o abandona la acción de escanear, THE Web_Dashboard SHALL detener la cámara y liberar el flujo de vídeo del Barcode_Scanner.

### Requirement 7: Flujo unificado "Agregar alimento"

**User Story:** Como usuario, quiero un único panel con acciones claras para agregar un alimento, para elegir cómo buscar o crear sin confundirme con el catálogo completo.

#### Acceptance Criteria

1. WHEN un Authenticated_User abre la Meals_Page, THE Web_Dashboard SHALL presentar el Add_Food_Panel con las acciones de escanear código, buscar por nombre, buscar en el inventario, buscar en recetas y crear nuevo, todas con texto en español.
2. WHEN un Authenticated_User selecciona una acción del Add_Food_Panel, THE Web_Dashboard SHALL mostrar únicamente el contenido de esa acción dentro del Add_Food_Panel sin mostrar las listas completas del catálogo ni de la despensa.
3. WHEN un Authenticated_User selecciona un Search_Result de `kind` igual a `catalog`, `inventory` o `off`, THE Web_Dashboard SHALL mostrar el paso de confirmación del Food_Candidate antes de agregarlo.
4. WHEN un Authenticated_User selecciona un Search_Result de `kind` igual a `recipe`, THE Web_Dashboard SHALL ofrecer agregar esa Recipe al User_Food_Inventory como una sola unidad.
5. WHERE el Authenticated_User activa `prefers-reduced-motion`, THE Web_Dashboard SHALL mostrar las transiciones del Add_Food_Panel sin animaciones de movimiento.
6. IF una Incremental_Search no produce ningún Search_Result, THEN THE Web_Dashboard SHALL mostrar un mensaje en español que ofrezca crear un alimento o una receta nuevos mediante la acción "Crear nuevo".

### Requirement 8: Privacidad y separación de privilegios

**User Story:** Como responsable del producto, quiero que agregar alimentos y recetas respete los permisos y la privacidad, para mantener la integridad del catálogo global y de los datos de cada usuario.

#### Acceptance Criteria

1. WHEN un Authenticated_User ejecuta una Incremental_Search, crea una Recipe, consulta sus Recipe o agrega un Food o una Recipe a su inventario, THE Food_Add_Redesign SHALL atender la solicitud sin requerir rol de Administrator.
2. THE Food_Add_Redesign SHALL restringir la creación, actualización y eliminación de un Food directamente en el Food_Catalog global a solicitudes de un Administrator vía `get_current_admin`.
3. WHEN un Authenticated_User sin rol de Administrator agrega un Food mediante el Create_Food_Form, THE Food_Add_Redesign SHALL agregar el Food únicamente a su propio User_Food_Inventory mediante el flujo de alta de inventario, creando una fila Food si el nombre no existe.
4. IF un Authenticated_User sin rol de Administrator solicita las Recipe o el User_Food_Inventory de otro usuario, THEN THE Food_Add_Redesign SHALL rechazar la solicitud y devolver un mensaje en español sin confirmar la existencia de datos de ese otro usuario.
5. THE Food_Add_Redesign SHALL proteger todos sus endpoints bajo `/api/meals` requiriendo la identidad del Authenticated_User vía `get_current_user`.
