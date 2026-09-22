# Requirements Document

## Introduction

Esta funcionalidad permite a los usuarios de HabitTrack recuperar el acceso a su cuenta cuando olvidan su contraseña, usando el bot de Telegram como canal de entrega en lugar del correo electrónico. Dado que el despliegue actual (Fly.io / Railway) no tiene un servicio de email configurado, la recuperación se realiza enviando un código de un solo uso al chat de Telegram vinculado a la cuenta.

El flujo consta de dos pasos desde la pantalla de inicio de sesión del frontend: (1) el usuario ingresa su email y solicita la recuperación; el backend, si la cuenta existe y tiene Telegram vinculado, genera un código de recuperación de corta duración y lo envía por el bot; (2) el usuario ingresa el código recibido y una nueva contraseña, y el backend valida el código y actualiza la contraseña.

El diseño reutiliza los patrones existentes del sistema: el modelo de token de un solo uso con expiración (`LinkingToken`), el `AuthService` con hashing bcrypt y validación de tokens, y el mecanismo de envío de mensajes de Telegram (`_send`). Por privacidad, el sistema nunca revela si un email está registrado o si tiene Telegram vinculado (protección contra enumeración de cuentas).

Los usuarios sin Telegram vinculado no pueden recuperar su contraseña por este canal; esa recuperación se realiza mediante un script de administrador y se documenta como limitación fuera de alcance de esta funcionalidad.

## Glossary

- **Backend**: La aplicación FastAPI de HabitTrack que expone los endpoints bajo `/api/`.
- **Frontend**: La aplicación React de HabitTrack servida en el navegador.
- **Auth_Service**: El servicio de autenticación (`app/services/auth_service.py`) responsable de hashing de contraseñas, tokens JWT y tokens de un solo uso.
- **Telegram_Bot**: El componente que envía y recibe mensajes de Telegram (`_send` en `app/routes/telegram.py` y el servicio `telegram_bot.py`).
- **Recovery_Code**: Un código de recuperación numérico de 6 dígitos, de un solo uso y de corta duración, generado por el Backend y enviado al usuario a través del Telegram_Bot.
- **Recovery_Token**: El registro persistente que respalda un Recovery_Code, con campos `user_id`, `code`, `used`, `created_at`, `expires_at`, siguiendo el patrón de `LinkingToken`.
- **User**: Una cuenta de HabitTrack con `email` (único), `password_hash` y `telegram_chat_id` (nulo si no está vinculado a Telegram).
- **Linked_User**: Un User cuyo `telegram_chat_id` no es nulo.
- **Forgot_Password_Endpoint**: `POST /api/auth/forgot-password`, que recibe un email e inicia la recuperación.
- **Reset_Password_Endpoint**: `POST /api/auth/reset-password`, que recibe email, código y nueva contraseña, y actualiza la contraseña.
- **Generic_Response**: Una respuesta neutral que no revela si el email existe ni si tiene Telegram vinculado.
- **Code_Expiry_Minutes**: La ventana de validez de un Recovery_Code, fijada en 15 minutos.
- **Min_Password_Length**: La longitud mínima de una contraseña, fijada en 6 caracteres (consistente con `PUT /api/auth/change-password`).
- **Rate_Limit_Window**: El período usado para limitar las solicitudes de recuperación por email, fijado en 15 minutos.
- **Max_Requests_Per_Window**: El número máximo de solicitudes de recuperación permitidas por email dentro de un Rate_Limit_Window, fijado en 3.

## Requirements

### Requirement 1: Solicitud de recuperación de contraseña

**User Story:** Como usuario que olvidó su contraseña, quiero solicitar la recuperación ingresando mi email, para recibir un código que me permita restablecerla.

#### Acceptance Criteria

1. WHEN el Frontend envía una solicitud al Forgot_Password_Endpoint con un email cuyo formato es válido y que corresponde a un Linked_User (un User con `telegram_chat_id` no nulo), THE Backend SHALL generar un Recovery_Code numérico de exactamente 6 dígitos de un solo uso, con expiración de Code_Expiry_Minutes igual a 15 minutos, y enviarlo al `telegram_chat_id` de ese User a través del Telegram_Bot.
2. WHEN el Backend genera un Recovery_Code para un User, THE Backend SHALL persistir un Recovery_Token con `user_id` igual al identificador del User, `code` igual al Recovery_Code generado, `used` en falso, `created_at` igual al instante de creación, y `expires_at` igual a `created_at` más Code_Expiry_Minutes (15 minutos).
3. WHEN el Forgot_Password_Endpoint termina de procesar cualquier solicitud con email de formato válido, THE Backend SHALL responder con código de estado HTTP 200 y con un Generic_Response en español cuyo cuerpo es idéntico en todos los casos (email existente, email inexistente o email sin `telegram_chat_id`), sin revelar si el email corresponde a un User registrado.
4. IF el email enviado al Forgot_Password_Endpoint tiene formato válido pero no corresponde a ningún User, THEN THE Backend SHALL responder con el mismo Generic_Response y HTTP 200, sin generar ningún Recovery_Token ni enviar ningún mensaje de Telegram.
5. IF el email enviado al Forgot_Password_Endpoint tiene formato válido y corresponde a un User cuyo `telegram_chat_id` es nulo, THEN THE Backend SHALL responder con el mismo Generic_Response y HTTP 200, sin generar ningún Recovery_Token ni enviar ningún mensaje de Telegram.
6. IF el envío del Recovery_Code al Telegram_Bot falla después de haber persistido el Recovery_Token, THEN THE Backend SHALL responder con el mismo Generic_Response y HTTP 200, manteniendo persistido el Recovery_Token generado.
7. WHEN el Forgot_Password_Endpoint recibe una solicitud con un email con formato inválido, THE Backend SHALL responder con código de estado HTTP 422 y un mensaje de validación en español que indique que el formato del email es inválido, sin generar ningún Recovery_Token ni enviar ningún mensaje de Telegram.

### Requirement 2: Invalidación de códigos previos

**User Story:** Como usuario, quiero que solo mi código de recuperación más reciente sea válido, para que códigos antiguos no puedan usarse para restablecer mi contraseña.

#### Acceptance Criteria

1. WHEN el Backend genera un nuevo Recovery_Token para un User, THE Backend SHALL marcar con `used` en verdadero todos los Recovery_Token no usados y no expirados previos de ese User antes de persistir el nuevo Recovery_Token.
2. WHILE un User posee más de un Recovery_Token con `used` en falso y `expires_at` posterior o igual al momento actual, THE Backend SHALL considerar válido únicamente el Recovery_Token con el mayor `created_at`, y en caso de empate en `created_at`, el de mayor `id`.
3. WHEN el Backend evalúa la validez de un Recovery_Token distinto del más reciente definido en el criterio 2, THE Backend SHALL tratarlo como no válido para el restablecimiento de contraseña.

### Requirement 3: Restablecimiento de contraseña con código

**User Story:** Como usuario que recibió un código por Telegram, quiero ingresar el código junto con una nueva contraseña, para restablecer el acceso a mi cuenta.

#### Acceptance Criteria

1. WHEN el Frontend envía una solicitud al Reset_Password_Endpoint con un email, un código que coincide con el Recovery_Token válido más reciente de ese User (no usado y no expirado), y una contraseña nueva cuya longitud está entre Min_Password_Length (6) y 128 caracteres inclusive, THE Backend SHALL actualizar el `password_hash` del User con el hash bcrypt de la nueva contraseña.
2. WHEN el Backend actualiza exitosamente el `password_hash` de un User en el Reset_Password_Endpoint, THE Backend SHALL responder con código de estado HTTP 200 y un mensaje de éxito en español.
3. WHEN el Backend restablece exitosamente la contraseña usando un Recovery_Token, THE Backend SHALL marcar ese Recovery_Token con `used` en verdadero.
4. WHEN el Reset_Password_Endpoint recibe una solicitud, THE Backend SHALL evaluar las condiciones de rechazo en el siguiente orden determinista y detenerse en la primera que se cumpla: (1) código no coincidente con ningún Recovery_Token del User, (2) Recovery_Token con `used` en verdadero, (3) Recovery_Token con `expires_at` anterior al momento actual, (4) longitud de la contraseña nueva fuera del rango de Min_Password_Length (6) a 128 caracteres inclusive.
5. IF el código enviado al Reset_Password_Endpoint no coincide con ningún Recovery_Token del User, THEN THE Backend SHALL responder con código de estado HTTP 400 y un mensaje de error genérico en español que no revele si el email está registrado, y SHALL dejar el `password_hash` del User sin cambios.
6. IF el código enviado al Reset_Password_Endpoint coincide con un Recovery_Token cuyo `used` es verdadero, THEN THE Backend SHALL rechazar la solicitud con código de estado HTTP 400 y un mensaje de error en español, y SHALL dejar el `password_hash` del User sin cambios.
7. IF el código enviado al Reset_Password_Endpoint coincide con un Recovery_Token cuyo `expires_at` es anterior al momento actual, THEN THE Backend SHALL rechazar la solicitud con código de estado HTTP 400 y un mensaje de error en español, y SHALL dejar el `password_hash` del User sin cambios.
8. IF la contraseña nueva enviada al Reset_Password_Endpoint tiene longitud menor a Min_Password_Length (6) o mayor a 128 caracteres, THEN THE Backend SHALL rechazar la solicitud con código de estado HTTP 400 y un mensaje de error en español indicando el rango de longitud permitido, SHALL dejar el Recovery_Token sin marcar como usado, y SHALL dejar el `password_hash` del User sin cambios.
9. WHEN el Backend actualiza exitosamente el `password_hash` de un User, THE Auth_Service SHALL producir un hash bcrypt tal que la verificación de la nueva contraseña contra ese hash sea verdadera y la verificación de la contraseña anterior contra ese hash sea falsa.

### Requirement 4: Protección contra enumeración de cuentas

**User Story:** Como responsable de seguridad, quiero que las respuestas de recuperación no revelen qué emails están registrados, para prevenir la enumeración de cuentas por parte de atacantes.

#### Acceptance Criteria

1. THE Forgot_Password_Endpoint SHALL responder con un Generic_Response idéntico en cuerpo y en código de estado HTTP 200 para cualquier email, independientemente de si el email corresponde a un User existente, a un Linked_User o a ningún User.
2. IF el Reset_Password_Endpoint rechaza una solicitud porque el email no corresponde a ningún User, porque el código no coincide con ningún Recovery_Token del User, o porque el Recovery_Token está usado o expirado, THEN THE Backend SHALL responder con un mensaje de error genérico en español idéntico para las tres condiciones que no indique si el email está registrado.
3. WHEN el Forgot_Password_Endpoint completa el procesamiento de cualquier solicitud, THE Backend SHALL responder en un tiempo menor o igual a 2 segundos, con una variación entre el tiempo de respuesta para un email de un Linked_User y el de un email inexistente menor o igual a 500 milisegundos.

### Requirement 5: Limitación de tasa de solicitudes

**User Story:** Como responsable de seguridad, quiero limitar la frecuencia de solicitudes de recuperación por email, para evitar el envío masivo de mensajes de Telegram y el abuso del sistema.

#### Acceptance Criteria

1. IF un email acumula un número de solicitudes al Forgot_Password_Endpoint igual a Max_Requests_Per_Window (3) dentro de un Rate_Limit_Window (15 minutos), THEN THE Backend SHALL responder con código de estado HTTP 429 y un mensaje en español para solicitudes adicionales de ese email dentro del mismo Rate_Limit_Window.
2. WHILE un email se encuentra limitado por tasa, THE Backend SHALL abstenerse de generar Recovery_Token y de enviar mensajes de Telegram para ese email.
3. WHEN transcurre un Rate_Limit_Window (15 minutos) desde la primera solicitud contabilizada de un email, THE Backend SHALL restablecer a cero el contador de solicitudes de ese email y SHALL volver a aceptar hasta Max_Requests_Per_Window (3) solicitudes en la siguiente ventana.

### Requirement 6: Entrega del código por Telegram

**User Story:** Como usuario con Telegram vinculado, quiero recibir mi código de recuperación por el bot de Telegram en español, para poder usarlo en el frontend.

#### Acceptance Criteria

1. WHEN el Backend envía un Recovery_Code a un Linked_User, THE Telegram_Bot SHALL enviar al `telegram_chat_id` del User un mensaje en español que contenga el Recovery_Code y su vigencia expresada en minutos.
2. IF el envío del mensaje de Telegram falla, THEN THE Backend SHALL registrar el error internamente y SHALL responder al Forgot_Password_Endpoint con el mismo Generic_Response sin exponer al llamador detalle alguno del fallo del envío.
3. IF el Backend intenta enviar un Recovery_Code a un User cuyo `telegram_chat_id` es nulo, THEN THE Backend SHALL abstenerse de invocar al Telegram_Bot y SHALL responder al Forgot_Password_Endpoint con el mismo Generic_Response.

### Requirement 7: Flujo de recuperación en el frontend

**User Story:** Como usuario, quiero un flujo guiado en la pantalla de inicio de sesión para recuperar mi contraseña, para completar la recuperación sin salir de la aplicación web.

#### Acceptance Criteria

1. WHEN el Frontend muestra la pantalla de inicio de sesión, THE Frontend SHALL mostrar un enlace con el texto "¿Olvidaste tu contraseña?".
2. WHEN el usuario activa el enlace "¿Olvidaste tu contraseña?", THE Frontend SHALL mostrar un primer paso que solicita el email del usuario.
3. WHEN el usuario envía el email en el primer paso, THE Frontend SHALL llamar al Forgot_Password_Endpoint, SHALL mostrar un indicador de carga y SHALL deshabilitar el botón de envío mientras la solicitud está pendiente.
4. WHEN el Forgot_Password_Endpoint responde con código de estado HTTP 200, THE Frontend SHALL mostrar el segundo paso que solicita el código de recuperación y la nueva contraseña.
5. WHEN el usuario envía el código y la nueva contraseña en el segundo paso, THE Frontend SHALL llamar al Reset_Password_Endpoint, SHALL mostrar un indicador de carga y SHALL deshabilitar el botón de envío mientras la solicitud está pendiente.
6. WHEN el Reset_Password_Endpoint responde con código de estado HTTP 200, THE Frontend SHALL mostrar un mensaje de éxito en español y SHALL redirigir al usuario a la pantalla de inicio de sesión en un tiempo menor o igual a 5 segundos.
7. IF una llamada al Forgot_Password_Endpoint o al Reset_Password_Endpoint responde con un código de estado de error, THEN THE Frontend SHALL mostrar el mensaje de error en español devuelto por el Backend, SHALL mantener al usuario en el paso actual y SHALL conservar los datos ingresados en los campos del formulario excepto el campo de contraseña, que SHALL vaciarse.