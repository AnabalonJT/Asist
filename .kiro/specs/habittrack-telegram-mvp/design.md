# Technical Design Document: HabitTrack Telegram MVP

## Overview

HabitTrack is a hybrid habit tracking system that combines the convenience of Telegram messaging with the power of LLM-based natural language processing and structured web-based data visualization. The system follows a clear separation of concerns: the LLM handles interpretation and narrative generation, while rule-based logic manages business operations like streak calculation, reminder scheduling, and calorie estimation.

### System Architecture Principles

1. **Hybrid Intelligence**: LLM for understanding and narration, deterministic rules for business logic
2. **Interface Separation**: Telegram for logging/notifications, web dashboard for visualization
3. **Free Infrastructure**: OpenRouter free models, PostgreSQL, deployment on free-tier platforms
4. **Token-Based Linking**: Secure one-time tokens connect Telegram users to web accounts
5. **Asynchronous Processing**: Non-blocking operations for LLM calls and message delivery

### Technology Stack

- **Backend**: FastAPI (Python 3.10+) with async/await patterns
- **Frontend**: React 18+ with hooks, React Router, chart library (recharts/chart.js)
- **Database**: PostgreSQL 14+ with async driver (asyncpg)
- **LLM Provider**: OpenRouter API (nvidia/nemotron-3-ultra-550b-a55b:free)
- **Bot Framework**: python-telegram-bot library
- **Authentication**: JWT tokens with httpOnly cookies
- **Deployment**: Render/Railway (unified front+back+DB deployment)
- **ORM**: SQLAlchemy 2.0 with async support
- **Task Scheduling**: APScheduler for reminders and weekly summaries

## Architecture

### High-Level System Architecture

```mermaid
graph TB
    User[User] -->|Messages| TG[Telegram Bot]
    User -->|Views Dashboard| WEB[React Web App]
    
    TG -->|Webhook| API[FastAPI Backend]
    WEB -->|HTTPS| API
    
    API -->|Queries| DB[(PostgreSQL)]
    API -->|Interprets| LLM[OpenRouter LLM]
    API -->|Schedules| SCHED[APScheduler]
    
    SCHED -->|Triggers| API
    API -->|Sends Messages| TG
    
    subgraph "Backend Services"
        API
        SCHED
    end
    
    subgraph "External Services"
        TG
        LLM
    end
    
    subgraph "Data Layer"
        DB
    end
```

### Component Architecture

```mermaid
graph LR
    subgraph "Frontend Layer"
        REACT[React Dashboard]
        AUTH[Auth Context]
        CALENDAR[Calendar View]
        STATS[Stats Components]
    end
    
    subgraph "API Layer"
        ROUTES[FastAPI Routes]
        MIDDLEWARE[Auth Middleware]
        WEBHOOK[Telegram Webhook]
    end
    
    subgraph "Service Layer"
        ACTIVITY[Activity Service]
        REMINDER[Reminder Service]
        LLM_SVC[LLM Service]
        TELEGRAM[Telegram Service]
        CALORIE[Calorie Service]
    end
    
    subgraph "Data Layer"
        MODELS[SQLAlchemy Models]
        REPOS[Repository Pattern]
        MIGRATIONS[Alembic Migrations]
    end
    
    REACT --> ROUTES
    ROUTES --> MIDDLEWARE
    WEBHOOK --> MIDDLEWARE
    MIDDLEWARE --> ACTIVITY
    MIDDLEWARE --> REMINDER
    ACTIVITY --> LLM_SVC
    ACTIVITY --> CALORIE
    ACTIVITY --> TELEGRAM
    REMINDER --> TELEGRAM
    ACTIVITY --> REPOS
    REMINDER --> REPOS
    REPOS --> MODELS
```

### Request Flow: Activity Logging

```mermaid
sequenceDiagram
    participant U as User
    participant TG as Telegram
    participant API as Backend API
    participant LLM as LLM Service
    participant DB as Database
    
    U->>TG: "Ran 5km this morning"
    TG->>API: Webhook: message event
    API->>DB: Check if user linked
    DB-->>API: User found
    API->>LLM: Parse activity message
    LLM-->>API: {type: "running", distance: 5, unit: "km"}
    API->>API: Calculate calories
    API->>DB: Create activity log
    DB-->>API: Activity saved
    API->>TG: Send confirmation
    TG->>U: "✅ Logged: Running 5km (420 cal)"
```

### Request Flow: Account Linking

```mermaid
sequenceDiagram
    participant U as User
    participant WEB as Web Dashboard
    participant API as Backend API
    participant DB as Database
    participant TG as Telegram
    
    U->>WEB: Register (email, password)
    WEB->>API: POST /auth/register
    API->>DB: Create user account
    DB-->>API: User ID
    API->>DB: Generate linking token
    DB-->>API: Token
    API-->>WEB: {token, bot_link}
    WEB->>U: Display bot link
    U->>TG: Click link (opens bot)
    TG->>U: /start {token}
    U->>TG: /start {token}
    TG->>API: Webhook: /start command
    API->>DB: Validate token & link user
    DB-->>API: Linked
    API->>TG: "✅ Account linked!"
    TG->>U: Welcome message
```

## Components and Interfaces

### Backend Components

#### 1. FastAPI Application (`app/main.py`)

**Responsibilities**:
- Application initialization and configuration
- Route registration
- Middleware setup (CORS, authentication, logging)
- Database connection pool management
- APScheduler initialization

**Key Dependencies**:
- FastAPI framework
- SQLAlchemy async engine
- APScheduler BackgroundScheduler

#### 2. Telegram Service (`app/services/telegram_service.py`)

**Responsibilities**:
- Webhook handler for incoming messages
- Message sending via Bot API
- Command parsing (/start, /help)
- Message formatting for confirmations and reminders

**Interface**:
```python
class TelegramService:
    async def handle_webhook(self, update: dict) -> None
    async def send_message(self, chat_id: int, text: str) -> bool
    async def link_account(self, chat_id: int, token: str) -> bool
    def format_activity_confirmation(self, activity: Activity) -> str
    def format_reminder(self, reminder: Reminder) -> str
```

**External Dependencies**:
- python-telegram-bot library
- Telegram Bot API (HTTPS)

#### 3. LLM Service (`app/services/llm_service.py`)

**Responsibilities**:
- Activity log interpretation from natural language
- Correction intent detection and extraction
- Weekly summary generation
- Reminder modification intent parsing
- Prompt engineering and response parsing

**Interface**:
```python
class LLMService:
    async def interpret_activity(self, message: str) -> ActivityData | None
    async def interpret_correction(
        self, message: str, recent_activities: list[Activity]
    ) -> CorrectionData | None
    async def generate_weekly_summary(
        self, activities: list[Activity], streak: int
    ) -> str
    async def interpret_reminder_action(
        self, message: str, reminders: list[Reminder]
    ) -> ReminderAction | None
```

**Data Structures**:
```python
@dataclass
class ActivityData:
    activity_type: str
    duration_minutes: int | None
    distance_km: float | None
    timestamp: datetime | None
    confidence: float

@dataclass
class CorrectionData:
    activity_id: int
    updates: dict[str, Any]
    confidence: float

@dataclass
class ReminderAction:
    action: Literal["pause", "resume", "modify", "delete"]
    reminder_id: int | None
    modifications: dict[str, Any] | None
```

**Prompt Templates**:
- Activity interpretation: Extract structured data from free-form messages
- Correction detection: Identify which activity to modify and what to change
- Summary generation: Create motivating narrative from weekly data
- Reminder parsing: Understand pause/modify intents

**Error Handling**:
- Timeout fallback (10s limit)
- Malformed response handling
- Service unavailability fallback

#### 4. Activity Service (`app/services/activity_service.py`)

**Responsibilities**:
- Activity log creation and updates
- Streak calculation
- Activity history retrieval
- Correction processing

**Interface**:
```python
class ActivityService:
    async def log_activity(
        self, user_id: int, message: str, telegram_chat_id: int
    ) -> Activity
    async def correct_activity(
        self, user_id: int, message: str, telegram_chat_id: int
    ) -> Activity | None
    async def get_recent_activities(
        self, user_id: int, days: int = 7
    ) -> list[Activity]
    async def calculate_streak(self, user_id: int) -> int
    async def get_activities_for_month(
        self, user_id: int, year: int, month: int
    ) -> list[Activity]
```

**Business Rules**:
- Streak: consecutive days with ≥1 activity
- Correction window: only last 7 days
- Timestamp defaults to current time if not specified

#### 5. Calorie Service (`app/services/calorie_service.py`)

**Responsibilities**:
- Calorie estimation based on activity type
- Formula management (CRUD for admin)
- MET-based calculations

**Interface**:
```python
class CalorieService:
    def estimate_calories(
        self, activity_type: str, duration_minutes: int, distance_km: float | None
    ) -> int
    async def get_formula(self, activity_type: str) -> CalorieFormula | None
    async def set_formula(
        self, activity_type: str, met_value: float, distance_factor: float | None
    ) -> CalorieFormula
```

**Calorie Formulas**:
- Base formula: `calories = (MET * weight_kg * duration_hours)`
- Distance-based: `calories = (distance_km * distance_factor)`
- Default weight: 70kg (configurable per user in future)
- Common METs: running=9.8, walking=3.5, cycling=7.5, gym=5.0

#### 6. Reminder Service (`app/services/reminder_service.py`)

**Responsibilities**:
- Reminder CRUD operations
- Scheduled reminder delivery
- Completion tracking
- Reminder pause/resume

**Interface**:
```python
class ReminderService:
    async def create_reminder(
        self, user_id: int, schedule: str, frequency: str, message: str
    ) -> Reminder
    async def update_reminder(self, reminder_id: int, updates: dict) -> Reminder
    async def delete_reminder(self, reminder_id: int) -> None
    async def pause_reminder(self, reminder_id: int) -> None
    async def resume_reminder(self, reminder_id: int) -> None
    async def get_due_reminders(self) -> list[Reminder]
    async def mark_completed(self, reminder_id: int) -> None
```

**Scheduling Rules**:
- Frequency: daily, weekly, custom (cron-like)
- Completion: auto-mark if matching activity logged
- Duplicate prevention: track last_sent_at timestamp

#### 7. Weekly Summary Service (`app/services/summary_service.py`)

**Responsibilities**:
- Compile weekly activity data
- Trigger LLM summary generation
- Deliver summaries via Telegram

**Interface**:
```python
class SummaryService:
    async def generate_and_send_weekly_summary(self, user_id: int) -> None
    async def compile_weekly_data(self, user_id: int) -> WeeklySummaryData
```

**Scheduling**:
- Runs every Sunday at 20:00 user local time (or UTC for MVP)
- APScheduler cron trigger
- Includes link to user dashboard in message

#### 8. Authentication Service (`app/services/auth_service.py`)

**Responsibilities**:
- User registration and login
- JWT token generation and validation
- Password hashing (bcrypt)
- Linking token generation

**Interface**:
```python
class AuthService:
    async def register(self, email: str, password: str) -> tuple[User, str]
    async def login(self, email: str, password: str) -> str | None
    def create_linking_token(self, user_id: int) -> str
    def verify_token(self, token: str) -> dict | None
```

### Frontend Components

#### 1. React Application Structure

```
src/
├── App.tsx                 # Root component, routing
├── contexts/
│   └── AuthContext.tsx     # Authentication state management
├── components/
│   ├── Calendar.tsx        # Monthly calendar view
│   ├── ActivityList.tsx    # Recent activities list
│   ├── StreakDisplay.tsx   # Streak counter with visualization
│   ├── LoginForm.tsx       # Login page
│   └── RegisterForm.tsx    # Registration page
├── services/
│   └── api.ts              # API client (axios/fetch)
└── types/
    └── index.ts            # TypeScript interfaces
```

#### 2. Key Component Interfaces

**Calendar Component**:
```typescript
interface CalendarProps {
  userId: string;
  month: number;
  year: number;
}

interface DayData {
  date: Date;
  activities: Activity[];
  reminders: Reminder[];
  hasActivity: boolean;
}
```

**Activity List Component**:
```typescript
interface ActivityListProps {
  userId: string;
  limit?: number;
}

interface Activity {
  id: number;
  activityType: string;
  duration: number;
  distance?: number;
  calories: number;
  timestamp: string;
}
```

**Streak Display Component**:
```typescript
interface StreakDisplayProps {
  streak: number;
  longestStreak?: number;
}
```

### API Routes

#### Authentication Routes

```
POST   /api/auth/register
  Body: {email: string, password: string}
  Response: {user_id: int, token: string, linking_token: string, bot_link: string}

POST   /api/auth/login
  Body: {email: string, password: string}
  Response: {token: string, user_id: int}

GET    /api/auth/me
  Headers: Authorization: Bearer {token}
  Response: {user_id: int, email: string, telegram_linked: bool}
```

#### Activity Routes

```
GET    /api/activities
  Headers: Authorization: Bearer {token}
  Query: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
  Response: {activities: Activity[]}

GET    /api/activities/streak
  Headers: Authorization: Bearer {token}
  Response: {current_streak: int, longest_streak: int}
```

#### Reminder Routes

```
GET    /api/reminders
  Headers: Authorization: Bearer {token}
  Response: {reminders: Reminder[]}

POST   /api/reminders
  Headers: Authorization: Bearer {token}
  Body: {schedule: string, frequency: string, message: string}
  Response: {reminder: Reminder}

PUT    /api/reminders/{id}
  Headers: Authorization: Bearer {token}
  Body: {schedule?: string, frequency?: string, message?: string, active?: bool}
  Response: {reminder: Reminder}

DELETE /api/reminders/{id}
  Headers: Authorization: Bearer {token}
  Response: {success: bool}
```

#### Dashboard Routes

```
GET    /api/dashboard/{user_id}
  Response: {activities: Activity[], streak: int, reminders: Reminder[]}
  Note: Uses user_id in path for shareable links (no auth required for MVP)
```

#### Telegram Webhook Route

```
POST   /api/telegram/webhook
  Body: Telegram Update object
  Response: {ok: bool}
```

#### Admin Routes (MVP - simple auth check)

```
POST   /api/admin/users
  Headers: Authorization: Bearer {admin_token}
  Body: {email: string, password: string, is_admin: bool}
  Response: {user: User}

POST   /api/admin/calories
  Headers: Authorization: Bearer {admin_token}
  Body: {activity_type: string, met_value: float, distance_factor?: float}
  Response: {formula: CalorieFormula}

PUT    /api/admin/calories/{activity_type}
  Headers: Authorization: Bearer {admin_token}
  Body: {met_value: float, distance_factor?: float}
  Response: {formula: CalorieFormula}
```

## Data Models

### Database Schema

```mermaid
erDiagram
    users ||--o{ activities : has
    users ||--o{ reminders : has
    users ||--o{ linking_tokens : has
    
    users {
        int id PK
        string email UK
        string password_hash
        bool is_admin
        bigint telegram_chat_id UK
        datetime created_at
        datetime updated_at
    }
    
    activities {
        int id PK
        int user_id FK
        string activity_type
        int duration_minutes
        float distance_km
        int calories
        datetime timestamp
        datetime created_at
    }
    
    reminders {
        int id PK
        int user_id FK
        string schedule
        string frequency
        string message
        bool active
        datetime last_sent_at
        datetime created_at
        datetime updated_at
    }
    
    linking_tokens {
        int id PK
        int user_id FK
        string token UK
        bool used
        datetime created_at
        datetime expires_at
    }
    
    calorie_formulas {
        int id PK
        string activity_type UK
        float met_value
        float distance_factor
        datetime created_at
        datetime updated_at
    }
```

### SQLAlchemy Models

#### User Model

```python
class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    password_hash: Mapped[str]
    is_admin: Mapped[bool] = mapped_column(default=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
    
    # Relationships
    activities: Mapped[list["Activity"]] = relationship(back_populates="user")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="user")
    linking_tokens: Mapped[list["LinkingToken"]] = relationship(back_populates="user")
```

#### Activity Model

```python
class Activity(Base):
    __tablename__ = "activities"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    activity_type: Mapped[str] = mapped_column(index=True)
    duration_minutes: Mapped[int | None]
    distance_km: Mapped[float | None]
    calories: Mapped[int]
    timestamp: Mapped[datetime] = mapped_column(index=True, default=func.now())
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="activities")
```

#### Reminder Model

```python
class Reminder(Base):
    __tablename__ = "reminders"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    schedule: Mapped[str]  # HH:MM format or cron expression
    frequency: Mapped[str]  # daily, weekly, custom
    message: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True)
    last_sent_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="reminders")
```

#### LinkingToken Model

```python
class LinkingToken(Base):
    __tablename__ = "linking_tokens"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(unique=True, index=True)
    used: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    expires_at: Mapped[datetime]  # 24 hours from creation
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="linking_tokens")
```

#### CalorieFormula Model

```python
class CalorieFormula(Base):
    __tablename__ = "calorie_formulas"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    activity_type: Mapped[str] = mapped_column(unique=True, index=True)
    met_value: Mapped[float]  # Metabolic Equivalent of Task
    distance_factor: Mapped[float | None]  # Calories per km (optional)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

### Database Indexes

**Performance Optimization**:
```sql
-- User lookups
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_telegram_chat_id ON users(telegram_chat_id);

-- Activity queries
CREATE INDEX idx_activities_user_timestamp ON activities(user_id, timestamp DESC);
CREATE INDEX idx_activities_type ON activities(activity_type);

-- Reminder queries
CREATE INDEX idx_reminders_user_active ON reminders(user_id, active);

-- Token validation
CREATE INDEX idx_linking_tokens_token ON linking_tokens(token);
CREATE INDEX idx_linking_tokens_user_used ON linking_tokens(user_id, used);
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Assessment: Property-Based Testing Applicability

This feature combines pure business logic with infrastructure concerns:

**PBT IS appropriate for**:
- LLM response parsing (Requirements 17.1-17.5)
- Streak calculation logic (Requirement 11)
- Calorie estimation formulas (Requirement 5)
- Activity data transformations

**PBT is NOT appropriate for**:
- Database operations (CRUD on User, Activity, Reminder)
- API endpoint integration (FastAPI routes)
- Telegram Bot API integration (webhook handling, message sending)
- OpenRouter LLM API calls
- Authentication/authorization flows

Given this analysis, I will use the prework tool to analyze the testable requirements before writing correctness properties.


### Property 1: Linking Token Uniqueness

*For any* set of user accounts created in the system, all generated linking tokens SHALL be unique.

**Validates: Requirements 1.5**

### Property 2: Calorie Calculation Completeness

*For any* activity with type and duration, and optionally distance, the calorie estimation SHALL apply the correct activity-specific formula and incorporate all provided parameters (duration and distance when present).

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 3: Schedule Format Validation

*For any* reminder schedule string, the validation logic SHALL correctly accept valid formats (HH:MM, cron expressions) and reject invalid formats.

**Validates: Requirements 7.3**

### Property 4: Reminder Completion Matching

*For any* active reminder and logged activity, if the activity type matches the reminder's target activity, the system SHALL mark the reminder as completed for the current period.

**Validates: Requirements 8.3**

### Property 5: Weekly Activity Compilation

*For any* user account and week period, the compiled weekly data SHALL include all activity logs within that week's date range with correct counts and totals.

**Validates: Requirements 10.1**

### Property 6: Streak Calculation Correctness

*For any* sequence of activities across calendar days, the streak count SHALL equal the number of consecutive days (from today backwards) that have at least one activity, resetting to zero when a day has no activities.

**Validates: Requirements 11.1, 11.2, 11.3, 11.5**

### Property 7: User Data Isolation

*For any* two distinct user accounts, requests authenticated as user A SHALL never return activity logs or reminders belonging to user B.

**Validates: Requirements 14.4**

### Property 8: LLM Response Parsing

*For any* valid LLM response following the expected format, the parser SHALL successfully extract structured activity data with all present fields.

**Validates: Requirements 17.1**

### Property 9: Activity Data Validation

*For any* parsed activity data structure, the validator SHALL reject data missing required fields (activity_type) and accept data with all required fields present.

**Validates: Requirements 17.2**

### Property 10: Activity Data Formatting

*For any* valid activity data structure, the formatter SHALL produce a JSON object conforming to the schema expected by the LLM service.

**Validates: Requirements 17.4**

### Property 11: Round-Trip Serialization

*For any* valid activity data structure, serializing (formatting) then deserializing (parsing) then serializing again SHALL produce an equivalent JSON structure to the first serialization.

**Validates: Requirements 17.5**


## Error Handling

### LLM Service Errors

**Timeout Handling**:
- Set 10-second timeout on all LLM requests
- On timeout: log error, return fallback response to user
- Fallback message: "Sorry, I couldn't process that. Please try rephrasing your message."

**API Errors**:
- HTTP 429 (rate limit): retry with exponential backoff (1s, 2s, 4s)
- HTTP 500 (server error): log, use fallback response
- HTTP 401 (auth error): log, notify admin, disable LLM temporarily
- Network errors: retry once, then fallback

**Malformed Response**:
- JSON parsing failure: log raw response, return fallback
- Missing required fields: log warning, attempt partial interpretation
- Confidence threshold: if LLM confidence < 0.6, ask user for clarification

**Fallback Strategy**:
```python
class LLMServiceError(Exception):
    """Base exception for LLM service errors"""
    pass

async def interpret_with_fallback(message: str) -> ActivityData | None:
    try:
        return await llm_service.interpret_activity(message)
    except asyncio.TimeoutError:
        logger.error("LLM timeout", extra={"message": message})
        return None
    except LLMServiceError as e:
        logger.error("LLM service error", exc_info=e)
        return None
    except Exception as e:
        logger.critical("Unexpected LLM error", exc_info=e)
        return None
```

### Database Errors

**Connection Failures**:
- Use connection pooling with retry logic
- Max retries: 3 with 1s delay
- On exhaustion: return 503 Service Unavailable

**Constraint Violations**:
- Unique constraint (email, telegram_chat_id): return 409 Conflict with descriptive message
- Foreign key violation: return 400 Bad Request
- Not null violation: return 400 Bad Request with field info

**Transaction Handling**:
- Use atomic transactions for multi-step operations (e.g., create user + linking token)
- On rollback: log full context, return appropriate HTTP error
- Deadlock detection: retry transaction once

**Query Errors**:
- Invalid date ranges: validate before query, return 400
- Missing records: return 404 Not Found
- Large result sets: implement pagination

### Telegram Bot Errors

**Webhook Failures**:
- Invalid signature: reject silently (security)
- Malformed update: log and ignore
- Unknown message type: ignore gracefully

**Message Send Failures**:
- User blocked bot: mark in database, stop sending
- Message too long: truncate with "..." indicator
- Rate limit (30 msg/sec): implement queue with rate limiter
- Network error: retry once after 2s

**Bot API Errors**:
```python
async def send_message_safe(chat_id: int, text: str) -> bool:
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        return True
    except telegram.error.Forbidden:
        # User blocked the bot
        await mark_user_blocked(chat_id)
        return False
    except telegram.error.NetworkError:
        # Retry once
        await asyncio.sleep(2)
        try:
            await bot.send_message(chat_id=chat_id, text=text)
            return True
        except Exception:
            logger.error("Failed to send message", extra={"chat_id": chat_id})
            return False
    except Exception as e:
        logger.error("Unexpected telegram error", exc_info=e)
        return False
```

### Authentication Errors

**Invalid Credentials**:
- Wrong password: return 401 with generic message "Invalid credentials"
- Non-existent email: return 401 with same message (prevent enumeration)
- Rate limiting: max 5 login attempts per 15 minutes per IP

**Token Errors**:
- Expired JWT: return 401 with "Token expired"
- Invalid signature: return 401 with "Invalid token"
- Missing token: return 401 with "Authentication required"

**Authorization Errors**:
- Non-admin accessing admin endpoint: return 403 Forbidden (no details)
- Accessing other user's data: return 403 Forbidden

### Validation Errors

**Input Validation**:
- Use Pydantic models for request validation
- Return 422 Unprocessable Entity with field-level errors
- Sanitize error messages (no internal details)

**Business Logic Validation**:
- Invalid reminder schedule: return 400 with human-readable message
- Activity timestamp in future: accept (user might log planned activities)
- Negative duration/distance: return 400

### Scheduler Errors

**Reminder Delivery Failures**:
- If reminder send fails: mark as failed, retry in next cycle
- Max retries: 3 before marking reminder as problematic
- Log failures for manual review

**Weekly Summary Failures**:
- If LLM fails: send generic summary with stats only
- If Telegram fails: log, retry next day
- Ensure summary only sent once per week per user

### Logging Strategy

**Log Levels**:
- DEBUG: LLM prompts/responses (sanitized), detailed flow
- INFO: User actions (login, register, link, log activity)
- WARNING: Retried operations, fallback activations
- ERROR: Failed operations with context
- CRITICAL: System-level failures (DB down, LLM unavailable)

**Structured Logging**:
```python
logger.info(
    "Activity logged",
    extra={
        "user_id": user.id,
        "activity_type": activity.activity_type,
        "calories": activity.calories,
        "source": "telegram"
    }
)
```

**PII Protection**:
- Never log raw passwords
- Hash/truncate email addresses in logs
- Sanitize telegram messages (remove personal info)
- Mask API keys in logs

## Testing Strategy

### Unit Tests

**Purpose**: Test individual functions and business logic in isolation.

**Coverage Areas**:
1. **Calorie Service**:
   - Test MET-based calculation formulas
   - Test distance-based calculations
   - Test formula lookup and caching
   - Edge cases: zero duration, missing formula

2. **Streak Calculation**:
   - Consecutive days logic
   - Gap detection and reset
   - Empty activity list (streak = 0)
   - Activities at day boundaries (timezone handling)

3. **Token Generation**:
   - Format validation
   - Expiration logic (24 hours)
   - Collision handling (very low probability)

4. **Schedule Validation**:
   - Valid formats (HH:MM, cron)
   - Invalid formats rejection
   - Edge cases: 24:00, malformed strings

5. **Message Formatting**:
   - Activity confirmation format
   - Reminder message format
   - Weekly summary structure
   - Truncation for long messages

6. **Authentication**:
   - Password hashing (bcrypt)
   - JWT creation and validation
   - Token expiration
   - Refresh token logic (if implemented)

**Test Examples**:
```python
def test_calorie_calculation_running():
    service = CalorieService()
    calories = service.estimate_calories(
        activity_type="running",
        duration_minutes=30,
        distance_km=5.0
    )
    assert 400 <= calories <= 500  # Reasonable range

def test_streak_with_gap():
    activities = [
        Activity(timestamp=datetime(2024, 1, 10)),
        Activity(timestamp=datetime(2024, 1, 9)),
        # Gap on Jan 8
        Activity(timestamp=datetime(2024, 1, 7)),
    ]
    streak = calculate_streak(activities, current_date=datetime(2024, 1, 10))
    assert streak == 2  # Only Jan 9-10 count
```

### Property-Based Tests

**Purpose**: Verify universal properties across many generated inputs to catch edge cases.

**Library**: Hypothesis (Python)

**Configuration**: Minimum 100 iterations per test

**Test Areas**:

1. **Token Uniqueness (Property 1)**:
```python
@given(st.integers(min_value=1, max_value=1000))
def test_token_uniqueness(num_users):
    """Feature: habittrack-telegram-mvp, Property 1: For any set of user accounts, 
    all generated linking tokens SHALL be unique"""
    tokens = [generate_linking_token(user_id=i) for i in range(num_users)]
    assert len(tokens) == len(set(tokens))
```

2. **Calorie Calculation (Property 2)**:
```python
@given(
    activity_type=st.sampled_from(["running", "walking", "cycling", "gym"]),
    duration=st.integers(min_value=1, max_value=300),
    distance=st.floats(min_value=0.1, max_value=100.0) | st.none()
)
def test_calorie_calculation_completeness(activity_type, duration, distance):
    """Feature: habittrack-telegram-mvp, Property 2: For any activity with type 
    and duration, calorie estimation SHALL apply correct formula"""
    calories = estimate_calories(activity_type, duration, distance)
    assert calories > 0
    # Verify formula selection
    formula = get_formula(activity_type)
    if distance:
        expected = calculate_with_distance(formula, duration, distance)
    else:
        expected = calculate_duration_only(formula, duration)
    assert abs(calories - expected) < 1  # Floating point tolerance
```

3. **Streak Calculation (Property 6)**:
```python
@given(
    activities=st.lists(
        st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2024, 12, 31)),
        min_size=0,
        max_size=100
    )
)
def test_streak_calculation_correctness(activities):
    """Feature: habittrack-telegram-mvp, Property 6: For any sequence of activities, 
    streak count SHALL equal consecutive days with activities"""
    # Sort activities by date
    sorted_activities = sorted(activities, reverse=True)
    streak = calculate_streak(sorted_activities)
    
    # Verify streak definition
    if not sorted_activities:
        assert streak == 0
    else:
        # Count consecutive days from today
        expected_streak = count_consecutive_days(sorted_activities)
        assert streak == expected_streak
```

4. **Round-Trip Serialization (Property 11)**:
```python
@given(
    activity_data=st.builds(
        ActivityData,
        activity_type=st.sampled_from(["running", "walking", "cycling"]),
        duration_minutes=st.integers(min_value=1, max_value=300),
        distance_km=st.floats(min_value=0.1, max_value=100.0) | st.none(),
        timestamp=st.datetimes(),
        confidence=st.floats(min_value=0.0, max_value=1.0)
    )
)
def test_activity_serialization_roundtrip(activity_data):
    """Feature: habittrack-telegram-mvp, Property 11: For any valid activity data, 
    formatting then parsing SHALL produce equivalent structure"""
    json_str = format_activity(activity_data)
    parsed = parse_activity(json_str)
    re_formatted = format_activity(parsed)
    
    assert json_str == re_formatted
    assert parsed == activity_data
```

5. **User Data Isolation (Property 7)**:
```python
@given(
    user_a_id=st.integers(min_value=1, max_value=10000),
    user_b_id=st.integers(min_value=1, max_value=10000)
)
def test_user_data_isolation(user_a_id, user_b_id):
    """Feature: habittrack-telegram-mvp, Property 7: For any two distinct users, 
    user A SHALL never access user B's data"""
    assume(user_a_id != user_b_id)
    
    # Create activities for user B
    create_activity(user_id=user_b_id, activity_type="running")
    
    # Try to access as user A
    user_a_activities = get_activities(user_id=user_a_id)
    
    # Verify no user B activities returned
    assert all(act.user_id == user_a_id for act in user_a_activities)
```

6. **Schedule Validation (Property 3)**:
```python
@given(schedule_str=st.text(min_size=1, max_size=50))
def test_schedule_validation(schedule_str):
    """Feature: habittrack-telegram-mvp, Property 3: For any schedule string, 
    validation SHALL correctly accept/reject based on format"""
    is_valid = validate_schedule(schedule_str)
    
    # Verify against known patterns
    if re.match(r'^\d{2}:\d{2}$', schedule_str):
        # HH:MM format
        hours, minutes = schedule_str.split(':')
        if 0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59:
            assert is_valid
    elif is_valid_cron(schedule_str):
        assert is_valid
    # Other formats should be rejected (is_valid == False)
```

### Integration Tests

**Purpose**: Test interaction between components, external services (mocked), and database.

**Coverage Areas**:

1. **Activity Logging Flow**:
   - Mock LLM service response
   - Verify database insert
   - Verify Telegram confirmation sent
   - Test with various activity types

2. **Account Linking**:
   - Create user and token
   - Send /start command
   - Verify telegram_chat_id updated
   - Verify token marked as used

3. **Reminder Delivery**:
   - Mock scheduler trigger
   - Verify Telegram message sent
   - Test reminder completion on activity log
   - Test duplicate prevention

4. **Weekly Summary**:
   - Create activities for a week
   - Trigger summary generation
   - Mock LLM response
   - Verify Telegram message with dashboard link

5. **API Endpoints**:
   - Test all CRUD operations
   - Test authentication middleware
   - Test error responses
   - Test pagination (if implemented)

**Test Example**:
```python
@pytest.mark.asyncio
async def test_activity_logging_integration(async_client, mock_llm, mock_telegram):
    # Setup
    user = await create_test_user()
    await link_telegram_account(user.id, chat_id=12345)
    
    # Mock LLM response
    mock_llm.interpret_activity.return_value = ActivityData(
        activity_type="running",
        duration_minutes=30,
        distance_km=5.0,
        timestamp=None,
        confidence=0.9
    )
    
    # Send message via webhook
    update = create_telegram_update(chat_id=12345, text="Ran 5km today")
    response = await async_client.post("/api/telegram/webhook", json=update)
    
    # Verify
    assert response.status_code == 200
    activities = await get_activities(user.id)
    assert len(activities) == 1
    assert activities[0].activity_type == "running"
    assert activities[0].calories > 0
    mock_telegram.send_message.assert_called_once()
```

### End-to-End Tests

**Purpose**: Test complete user journeys across the full system stack.

**Critical Paths**:

1. **New User Onboarding**:
   - Register on web dashboard
   - Receive linking token and bot link
   - Click bot link, send /start
   - Verify linked in dashboard

2. **Activity Logging Journey**:
   - Send activity message in Telegram
   - Receive confirmation
   - View activity in web dashboard
   - Verify streak updated

3. **Correction Flow**:
   - Log activity
   - Send correction message
   - Receive updated confirmation
   - Verify correction in dashboard

4. **Reminder Cycle**:
   - Create reminder via API
   - Wait for scheduled time (or mock scheduler)
   - Receive reminder in Telegram
   - Log matching activity
   - Verify reminder marked complete

5. **Weekly Summary Flow**:
   - Log activities throughout week
   - Wait for Sunday 20:00 (or trigger manually)
   - Receive summary in Telegram
   - Click dashboard link
   - Verify data matches

**Testing Approach**:
- Use TestContainers for real PostgreSQL
- Mock external services (Telegram, OpenRouter)
- Selenium/Playwright for web dashboard tests (optional)
- Test in staging environment before production

### Test Data Management

**Fixtures**:
```python
@pytest.fixture
async def test_user():
    user = await User.create(email="test@example.com", password_hash="hashed")
    yield user
    await user.delete()

@pytest.fixture
def sample_activities():
    return [
        {"activity_type": "running", "duration": 30, "distance": 5.0},
        {"activity_type": "walking", "duration": 60, "distance": 3.0},
        {"activity_type": "gym", "duration": 45, "distance": None},
    ]
```

**Database Seeding**:
- Use Alembic for schema setup in tests
- Create seed data for calorie formulas
- Reset database between test runs
- Use transactions with rollback for test isolation

### Continuous Integration

**CI Pipeline**:
1. Lint (flake8, black, isort)
2. Type check (mypy)
3. Unit tests (pytest with coverage)
4. Property tests (pytest with Hypothesis)
5. Integration tests (with TestContainers)
6. Build Docker images
7. Deploy to staging
8. Smoke tests in staging
9. Deploy to production (manual approval)

**Coverage Goals**:
- Unit tests: >80% line coverage
- Property tests: All 11 properties implemented
- Integration tests: All API endpoints covered
- E2E tests: 5 critical user journeys

**Test Performance**:
- Unit tests: <10 seconds total
- Property tests: <30 seconds (100 iterations each)
- Integration tests: <2 minutes
- E2E tests: <5 minutes

### Manual Testing Checklist

**Before Release**:
- [ ] Register new account and link Telegram
- [ ] Log 5 different activity types via Telegram
- [ ] Correct an activity
- [ ] View dashboard with activities
- [ ] Create reminder and verify delivery
- [ ] Pause reminder via natural language
- [ ] Receive weekly summary
- [ ] Test on mobile devices (iOS, Android)
- [ ] Test bot with blocked/unblocked states
- [ ] Verify admin endpoints require auth
- [ ] Test with production LLM (OpenRouter)
- [ ] Monitor logs for errors during testing

## Implementation Notes

### Deployment Configuration

**Environment Variables**:
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/habittrack

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_WEBHOOK_URL=https://your-domain.com/api/telegram/webhook
TELEGRAM_WEBHOOK_SECRET=random-secret-key

# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free

# JWT
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Application
APP_ENV=production
LOG_LEVEL=INFO
FRONTEND_URL=https://your-frontend-domain.com
DEFAULT_USER_WEIGHT_KG=70
```

**Railway/Render Deployment**:
1. Connect GitHub repository
2. Set environment variables in dashboard
3. Configure build command: `pip install -r requirements.txt`
4. Configure start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Enable automatic deploys on main branch
6. Configure PostgreSQL addon
7. Set up domain (for webhook HTTPS requirement)

### Performance Considerations

**Database Optimization**:
- Use connection pooling (asyncpg pool size: 10-20)
- Create indexes on frequently queried columns
- Use `select_related` for joined queries
- Implement pagination for activity lists (50 items per page)
- Consider partitioning activities table by date (future optimization)

**LLM Request Optimization**:
- Cache common activity patterns (future)
- Batch multiple requests if possible (future)
- Use streaming responses for summaries (future)
- Monitor token usage to stay within free tier limits

**Telegram Bot Optimization**:
- Use webhook mode (not polling) for lower latency
- Implement message queue for rate limiting
- Use connection pooling for HTTP requests
- Enable connection keep-alive

**Frontend Optimization**:
- Lazy load dashboard components
- Cache dashboard data in localStorage (with TTL)
- Use React.memo for expensive components
- Optimize bundle size with code splitting
- Use CDN for static assets

### Security Considerations

**API Security**:
- Enable CORS only for frontend domain
- Use HTTPS only (enforce in middleware)
- Implement rate limiting (10 req/sec per IP)
- Sanitize all user inputs
- Use parameterized queries (SQLAlchemy handles this)
- Set security headers (HSTS, CSP, X-Frame-Options)

**Telegram Bot Security**:
- Validate webhook signature
- Use webhook secret token
- Ignore updates from unknown sources
- Never expose internal error details to users

**Authentication Security**:
- Use bcrypt with cost factor 12
- Implement password strength requirements
- Add account lockout after failed attempts
- Use httpOnly cookies for JWT (or Authorization header)
- Implement CSRF protection for web dashboard

**Database Security**:
- Use least-privilege database user
- Never log SQL queries with sensitive data
- Encrypt sensitive data at rest (future)
- Regular database backups
- Use environment variables for credentials (never commit)

### Monitoring and Observability

**Metrics to Track**:
- Request latency (p50, p95, p99)
- Error rates by endpoint
- LLM request success rate
- LLM response time
- Database query performance
- Active user count
- Daily/weekly activity logs
- Streak distribution

**Logging**:
- Structured JSON logs
- Log aggregation (e.g., Logstash, Papertrail)
- Error tracking (e.g., Sentry)
- Request tracing (correlation IDs)

**Alerts**:
- Database connection failures
- LLM service unavailability
- High error rate (>5% of requests)
- Telegram webhook failures
- Disk space usage >80%

### Future Enhancements

**Phase 2 Features** (not in MVP):
- User weight configuration for accurate calories
- Activity photos/attachments
- Social features (challenges, leaderboards)
- Multi-language support
- Custom activity types per user
- Goal setting and tracking
- Data export (CSV, JSON)
- Integration with fitness trackers (Strava, Garmin)
- Voice message interpretation
- Habit templates library
- Advanced analytics and insights
- Team/group tracking
- Reminder snooze functionality
- Time zone support per user
