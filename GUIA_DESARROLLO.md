# HabitTrack — Guía de Instalación para Desarrollo

## Descripción

HabitTrack es una aplicación de seguimiento de hábitos y deportes que usa Telegram como interfaz de registro y un dashboard web para visualización. El sistema interpreta mensajes en lenguaje natural mediante IA (LLM) y registra actividades automáticamente.

---

## Requisitos previos

Necesitas tener instalado:

| Software | Versión mínima | Descarga |
|----------|---------------|----------|
| **Docker Desktop** | 4.0+ | https://www.docker.com/products/docker-desktop/ |
| **Git** | 2.30+ | https://git-scm.com/downloads |

> **Nota**: Docker Desktop incluye Docker Compose. No necesitas instalar Python ni Node.js — todo corre dentro de contenedores.

### Verificar instalación

Abre una terminal (CMD, PowerShell o Terminal) y ejecuta:

```bash
docker --version
# Debe mostrar: Docker version 24.x o superior

git --version
# Debe mostrar: git version 2.x
```

---

## Paso 1: Clonar el repositorio

```bash
git clone https://github.com/TU_USUARIO/Asist.git
cd Asist
```

---

## Paso 2: Configurar variables de entorno

Copia el archivo de ejemplo y edítalo:

```bash
# En Windows (CMD):
copy .env.example .env

# En Mac/Linux:
cp .env.example .env
```

Abre `.env` con cualquier editor de texto y configura estas 3 variables **obligatorias**:

```env
# Token de tu bot de Telegram (obtener de @BotFather en Telegram)
TELEGRAM_TOKEN=tu_token_aqui
TELEGRAM_BOT_TOKEN=tu_token_aqui

# Username del bot (sin @)
TELEGRAM_BOT_USERNAME=NombreDeTuBot

# API key de OpenRouter (gratis en https://openrouter.ai)
OPENROUTER_API_KEY=sk-or-v1-tu_key_aqui
```

### ¿Cómo obtener el token de Telegram?

1. Abre Telegram y busca **@BotFather**
2. Envía `/newbot`
3. Sigue las instrucciones (nombre + username)
4. BotFather te dará un token como: `123456789:ABCdefGHIjklmNOPqrstUVwxyz`
5. Copia ese token en `TELEGRAM_TOKEN` y `TELEGRAM_BOT_TOKEN`

### ¿Cómo obtener la API key de OpenRouter?

1. Ve a https://openrouter.ai
2. Crea una cuenta (gratis)
3. Ve a https://openrouter.ai/keys
4. Crea una nueva key
5. Copia la key en `OPENROUTER_API_KEY`

> El modelo que usamos (`nvidia/nemotron-3-ultra-550b-a55b:free`) es gratuito.

---

## Paso 3: Levantar el proyecto

```bash
docker compose up --build
```

La primera vez tardará unos minutos descargando imágenes. Verás logs como:

```
db-1   | PostgreSQL init process complete; ready for start up.
app-1  | Database tables ensured
app-1  | Bot connected: @TuBot (id=123456789)
app-1  | Telegram bot polling started successfully
app-1  | APScheduler started
```

**El proyecto está listo cuando veas el mensaje del bot connected.**

---

## Paso 4: Usar la aplicación

### Dashboard Web

Abre en tu navegador:

```
http://localhost
```

1. **Regístrate** con email y contraseña
2. Click en **"Conectar Telegram"**
3. Se abrirá Telegram con tu bot → presiona **START**
4. El bot confirmará: "✅ ¡Cuenta vinculada!"

### Bot de Telegram

Una vez vinculado, envía mensajes al bot como:

| Mensaje | Qué hace |
|---------|----------|
| "Corrí 5km" | Registra running, calcula calorías |
| "30 min de yoga" | Registra yoga, 30 minutos |
| "Fui al gym 1 hora" | Registra gym, 60 min |
| "4 series de press banca 80kg" | Registra fuerza con detalle |
| "Leí 30 minutos" | Registra hábito (sin calorías) |
| "Medité 10 min" | Registra hábito |
| "Recuérdame meditar a las 8:00" | Crea recordatorio diario |
| "Mis recordatorios" | Lista recordatorios activos |
| "Mi zona es America/Santiago" | Cambia zona horaria |

### Dashboard

Vuelve a `http://localhost` para ver:
- Estadísticas (actividades, calorías, racha, tiempo)
- Calendario mensual con días activos
- Desglose por tipo de actividad
- Actividad reciente

> El dashboard se actualiza automáticamente cada 30 segundos.

---

## Comandos útiles

| Comando | Qué hace |
|---------|----------|
| `docker compose up --build` | Levanta todo (DB + App) |
| `docker compose down` | Detiene todo |
| `docker compose down -v` | Detiene y **borra la base de datos** |
| `docker compose logs -f app` | Ver logs de la aplicación |
| `docker compose restart app` | Reiniciar solo la app |

---

## Solución de problemas

### "502 Bad Gateway"
La aplicación aún está arrancando. Espera 10-15 segundos y recarga.

### El bot no responde
- Verifica que `TELEGRAM_TOKEN` en `.env` sea correcto
- Verifica en los logs que diga "Bot connected: @TuBot"
- Si dice "No valid Telegram bot token", revisa el token

### Error de conexión a base de datos
```bash
docker compose down -v
docker compose up --build
```

### "OpenRouter error 401"
Tu `OPENROUTER_API_KEY` es inválida. Genera una nueva en https://openrouter.ai/keys

---

## Arquitectura del proyecto

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│   Dashboard     │────▶│   FastAPI    │────▶│ PostgreSQL  │
│   (React)       │     │   Backend    │     │   (Docker)  │
└─────────────────┘     └──────┬───────┘     └─────────────┘
                               │
                        ┌──────┴───────┐
                        │              │
                   ┌────▼────┐   ┌─────▼──────┐
                   │Telegram │   │ OpenRouter  │
                   │Bot API  │   │ LLM (free) │
                   └─────────┘   └────────────┘
```

- **Frontend**: React + Tailwind CSS (servido por FastAPI en producción)
- **Backend**: Python FastAPI con SQLAlchemy async
- **Bot**: python-telegram-bot en modo polling
- **LLM**: OpenRouter (modelo gratuito nvidia/nemotron)
- **DB**: PostgreSQL 16

---

## Detener el proyecto

```bash
# Ctrl+C en la terminal donde corre docker compose
# O en otra terminal:
docker compose down
```

Para borrar todos los datos y empezar de cero:

```bash
docker compose down -v
```
