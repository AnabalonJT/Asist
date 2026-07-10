# Implementation Plan: HabitTrack Telegram MVP

## Overview

This implementation plan breaks down the HabitTrack Telegram MVP into discrete, sequential coding tasks. The feature enables users to track habits and sports activities through natural language messages in Telegram, with data visualization on a web dashboard. The system uses LLM-based natural language processing for activity interpretation and weekly summaries, with deterministic business logic for streaks, reminders, and calorie estimation.

**Technology Stack**: FastAPI (Python 3.10+), React 18+, PostgreSQL 14+, python-telegram-bot, OpenRouter API, SQLAlchemy 2.0, APScheduler

**Implementation Approach**: Bottom-up incremental development starting with database and core services, then building up to API endpoints, bot integration, and frontend components. Each task builds on previous work and includes validation through code execution.

## Tasks

- [x] 1. Set up project structure and database foundation
  - [x] 1.1 Initialize Python backend project with FastAPI
    - Create project directory structure (`app/`, `app/services/`, `app/models/`, `app/routes/`, `tests/`)
    - Set up `requirements.txt` with core dependencies (FastAPI, SQLAlchemy, asyncpg, python-telegram-bot, APScheduler, bcrypt, PyJWT, httpx, pydantic)
    - Create `app/main.py` with FastAPI application initialization
    - Configure CORS middleware for frontend integration
    - Set up environment variable loading with `python-dotenv`
    - _Requirements: 16.1, 16.2_

  - [x] 1.2 Configure database with SQLAlchemy and Alembic
    - Install and initialize Alembic for database migrations
    - Create `app/database.py` with async SQLAlchemy engine and session management
    - Configure connection pooling with asyncpg (pool size 10-20)
    - Set up database URL from environment variables
    - Create initial Alembic migration structure
    - _Requirements: 16.1, 16.5_

  - [x] 1.3 Define SQLAlchemy models for all entities
    - Create `app/models/user.py` with User model (id, email, password_hash, is_admin, telegram_chat_id, timestamps)
    - Create `app/models/activity.py` with Activity model (id, user_id, activity_type, duration_minutes, distance_km, calories, timestamp)
    - Create `app/models/reminder.py` with Reminder model (id, user_id, schedule, frequency, message, active, last_sent_at)
    - Create `app/models/linking_token.py` with LinkingToken model (id, user_id, token, used, created_at, expires_at)
    - Create `app/models/calorie_formula.py` with CalorieFormula model (id, activity_type, met_value, distance_factor)
    - Configure relationships between models using SQLAlchemy ORM
    - _Requirements: 16.1, 16.2, 16.3, 16.4_

  - [x] 1.4 Create database migration and indexes
    - Generate Alembic migration from SQLAlchemy models
    - Add performance indexes: users(email), users(telegram_chat_id), activities(user_id, timestamp), reminders(user_id, active), linking_tokens(token)
    - Add composite index on activities(user_id, timestamp DESC) for streak queries
    - Run migration to create all tables and indexes
    - _Requirements: 16.1, 16.2, 16.5_

  - [x] 1.5 Seed database with default calorie formulas
    - Create seed data script for CalorieFormula table
    - Add common activity types with MET values: running (9.8), walking (3.5), cycling (7.5), gym (5.0), swimming (8.0), yoga (3.0)
    - Add distance factors where applicable (running: 60 cal/km, walking: 40 cal/km, cycling: 35 cal/km)
    - Run seed script to populate calorie formulas
    - _Requirements: 5.1, 5.2_

- [x] 2. Checkpoint - Database foundation complete
  - Ensure all tables created, indexes applied, seed data loaded. Verify database connection works. Ask the user if questions arise.

- [x] 3. Implement core business logic services
  - [x] 3.1 Create CalorieService for activity calorie estimation
    - Create `app/services/calorie_service.py` with CalorieService class
    - Implement `estimate_calories(activity_type, duration_minutes, distance_km)` method
    - Use MET-based formula: calories = (MET × weight_kg × duration_hours) where default weight is 70kg
    - When distance provided, use distance-based formula: calories = (distance_km × distance_factor)
    - Implement `get_formula(activity_type)` to retrieve CalorieFormula from database
    - Implement `set_formula(activity_type, met_value, distance_factor)` for admin formula management
    - Handle missing formulas with default MET value of 5.0
    - _Requirements: 5.1, 5.2, 5.3_

  - [x]* 3.2 Write property test for calorie calculation completeness
    - **Property 2: Calorie Calculation Completeness**
    - **Validates: Requirements 5.1, 5.2, 5.3**
    - Use Hypothesis to generate test cases with activity types, durations, and optional distances
    - Verify that all provided parameters are incorporated into the calculation
    - Test that calories > 0 for all valid inputs
    - Verify correct formula selection based on activity type

  - [x]* 3.3 Write unit tests for CalorieService
    - Test MET-based calculation with known inputs
    - Test distance-based calculation when distance provided
    - Test fallback to default MET when formula not found
    - Test edge cases: zero duration (should return 0), very large values
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 3.4 Implement streak calculation logic
    - Create `app/services/activity_service.py` with ActivityService class
    - Implement `calculate_streak(user_id)` method
    - Query activities ordered by timestamp descending
    - Count consecutive days from today backwards where at least one activity exists
    - Reset streak to 0 when a day with no activities is found
    - Return 0 when user has no activities
    - Handle timezone considerations (use UTC for MVP)
    - _Requirements: 11.1, 11.2, 11.3, 11.5_

  - [x]* 3.5 Write property test for streak calculation correctness
    - **Property 6: Streak Calculation Correctness**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.5**
    - Use Hypothesis to generate random activity sequences with various date patterns
    - Verify streak equals consecutive days count from today backwards
    - Test empty activity list returns 0
    - Test activities with gaps correctly reset streak
    - Test activities at day boundaries

  - [x]* 3.6 Write unit tests for streak calculation
    - Test consecutive days (expected streak > 1)
    - Test with gap in middle (streak should be from most recent consecutive days)
    - Test empty activities (streak = 0)
    - Test single day activity (streak = 1)
    - Test activities spanning multiple months
    - _Requirements: 11.1, 11.2, 11.3, 11.5_

  - [x] 3.7 Implement ActivityService CRUD methods
    - Implement `get_recent_activities(user_id, days=7)` to retrieve recent activity logs
    - Implement `get_activities_for_month(user_id, year, month)` for calendar view
    - Implement `create_activity(user_id, activity_type, duration_minutes, distance_km, calories, timestamp)` method
    - Implement `update_activity(activity_id, updates)` method for corrections
    - Implement `get_activity_by_id(activity_id)` method
    - Add data isolation checks to ensure users only access their own activities
    - _Requirements: 3.1, 3.2, 3.3, 4.3, 6.4, 14.4_

  - [x]* 3.8 Write property test for user data isolation
    - **Property 7: User Data Isolation**
    - **Validates: Requirements 14.4**
    - Use Hypothesis to generate two distinct user IDs
    - Create activities for user B, query as user A
    - Verify user A never receives user B's data
    - Test with various query methods (by date range, by month, recent activities)

- [x] 4. Checkpoint - Core business logic complete
  - Ensure CalorieService and ActivityService work correctly. Run property tests and unit tests. Ask the user if questions arise.


- [x] 5. Implement authentication and user management
  - [x] 5.1 Create AuthService with password hashing and JWT generation
    - Create `app/services/auth_service.py` with AuthService class
    - Implement password hashing using bcrypt with cost factor 12
    - Implement `register(email, password)` method that creates user and returns JWT token
    - Implement `login(email, password)` method that validates credentials and returns JWT token
    - Implement `verify_token(token)` method to validate and decode JWT tokens
    - Use JWT_SECRET_KEY, JWT_ALGORITHM, and JWT_EXPIRATION_HOURS from environment
    - _Requirements: 1.2, 1.3, 14.1, 14.2_

  - [x] 5.2 Implement linking token generation and validation
    - Add `create_linking_token(user_id)` method to AuthService
    - Generate unique random token (UUID4 format)
    - Store token in database with 24-hour expiration
    - Implement `validate_linking_token(token)` method
    - Check token exists, not used, and not expired
    - Mark token as used after successful validation
    - _Requirements: 1.5, 2.2, 2.3, 2.4_

  - [x]* 5.3 Write property test for linking token uniqueness
    - **Property 1: Linking Token Uniqueness**
    - **Validates: Requirements 1.5**
    - Use Hypothesis to generate multiple user account creations
    - Verify all generated tokens are unique
    - Test with 100-1000 token generations

  - [x]* 5.4 Write unit tests for AuthService
    - Test successful registration creates user and returns valid JWT
    - Test duplicate email registration fails
    - Test login with correct credentials succeeds
    - Test login with wrong password fails
    - Test JWT token validation and expiration
    - Test linking token expiration after 24 hours
    - Test linking token reuse prevention
    - _Requirements: 1.2, 1.3, 1.4, 2.2, 2.3, 2.4, 14.1, 14.2_

  - [x] 5.5 Create authentication middleware
    - Create `app/middleware/auth.py` with JWT authentication dependency
    - Implement `get_current_user(token: str)` dependency for protected routes
    - Extract JWT from Authorization header (Bearer token)
    - Validate token and retrieve user from database
    - Return 401 Unauthorized for invalid/expired tokens
    - Implement `get_current_admin_user` dependency for admin-only routes
    - _Requirements: 14.1, 14.2, 14.3_

- [x] 6. Implement reminder management services
  - [x] 6.1 Create schedule validation utility
    - Create `app/utils/schedule_validator.py` with validation functions
    - Implement `validate_schedule(schedule_str)` for HH:MM format (00:00 to 23:59)
    - Implement cron expression validation (basic validation for now)
    - Return validation result with error message if invalid
    - _Requirements: 7.3, 7.4_

  - [x]* 6.2 Write property test for schedule format validation
    - **Property 3: Schedule Format Validation**
    - **Validates: Requirements 7.3**
    - Use Hypothesis to generate random strings
    - Verify validator correctly accepts valid HH:MM formats
    - Verify validator rejects invalid formats
    - Test edge cases: 24:00, 25:00, -1:00, malformed strings

  - [x] 6.3 Create ReminderService for reminder management
    - Create `app/services/reminder_service.py` with ReminderService class
    - Implement `create_reminder(user_id, schedule, frequency, message)` method
    - Validate schedule format before creating reminder
    - Implement `update_reminder(reminder_id, updates)` method
    - Implement `delete_reminder(reminder_id)` method
    - Implement `pause_reminder(reminder_id)` and `resume_reminder(reminder_id)` methods
    - Implement `get_due_reminders()` to fetch reminders scheduled for current time
    - Implement `mark_completed(reminder_id)` to track reminder completion
    - _Requirements: 7.1, 7.2, 7.3, 8.3, 9.2, 9.5_

  - [x] 6.4 Implement reminder completion matching logic
    - Add `check_reminder_completion(user_id, activity_type)` method to ReminderService
    - Query active reminders for user that match the activity type
    - Mark matching reminders as completed for current period
    - Update last_sent_at to prevent duplicate sends
    - _Requirements: 8.3_

  - [x]* 6.5 Write property test for reminder completion matching
    - **Property 4: Reminder Completion Matching**
    - **Validates: Requirements 8.3**
    - Use Hypothesis to generate reminders and activities
    - Verify matching activity types correctly mark reminders as completed
    - Verify non-matching activities don't affect reminders

  - [x]* 6.6 Write unit tests for ReminderService
    - Test creating reminder with valid schedule
    - Test creating reminder with invalid schedule fails
    - Test updating reminder active status (pause/resume)
    - Test getting due reminders returns only scheduled items
    - Test reminder completion marking
    - Test duplicate reminder prevention (same period)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.3, 8.4, 9.2, 9.5_

- [x] 7. Checkpoint - Authentication and reminders complete
  - Ensure AuthService and ReminderService work. Run tests. Ask the user if questions arise.

- [x] 8. Implement LLM service integration
  - [x] 8.1 Create LLM service client for OpenRouter
    - Create `app/services/llm_service.py` with LLMService class
    - Configure OpenRouter API connection using httpx async client
    - Set API key and model (nvidia/nemotron-3-ultra-550b-a55b:free) from environment
    - Implement `_call_llm(prompt, system_message)` private method with 10-second timeout
    - Add retry logic with exponential backoff for rate limits (429)
    - Add error handling for network errors, timeouts, and API errors
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

  - [x] 8.2 Implement activity interpretation with prompt engineering
    - Create prompt template for activity log interpretation
    - Prompt should extract: activity_type, duration_minutes, distance_km, timestamp, confidence
    - Implement `interpret_activity(message: str)` method
    - Parse LLM JSON response into ActivityData dataclass
    - Return None if parsing fails or confidence < 0.6
    - Add fallback handling for malformed responses
    - _Requirements: 3.1, 15.7, 17.1_

  - [x] 8.3 Implement activity data parser and validator
    - Create `app/utils/activity_parser.py` with parsing functions
    - Implement `parse_activity_data(json_str)` to convert JSON to ActivityData
    - Validate required fields (activity_type must be present)
    - Implement `format_activity_data(activity_data)` to convert ActivityData to JSON
    - Handle optional fields (duration, distance, timestamp)
    - _Requirements: 17.1, 17.2, 17.4_

  - [x]* 8.4 Write property test for LLM response parsing
    - **Property 8: LLM Response Parsing**
    - **Validates: Requirements 17.1**
    - Use Hypothesis to generate valid LLM response JSON structures
    - Verify parser successfully extracts all present fields
    - Test with various field combinations (with/without optional fields)

  - [x]* 8.5 Write property test for activity data validation
    - **Property 9: Activity Data Validation**
    - **Validates: Requirements 17.2**
    - Use Hypothesis to generate activity data with missing fields
    - Verify validator rejects data missing required fields (activity_type)
    - Verify validator accepts data with all required fields

  - [x]* 8.6 Write property test for activity data formatting
    - **Property 10: Activity Data Formatting**
    - **Validates: Requirements 17.4**
    - Use Hypothesis to generate valid ActivityData structures
    - Verify formatter produces JSON conforming to expected schema
    - Verify all fields are correctly serialized

  - [x]* 8.7 Write property test for round-trip serialization
    - **Property 11: Round-Trip Serialization**
    - **Validates: Requirements 17.5**
    - Use Hypothesis to generate valid ActivityData structures
    - Format → Parse → Format and verify equivalence
    - Test with various field combinations to ensure consistency

  - [x] 8.8 Implement correction interpretation
    - Create prompt template for correction intent detection
    - Include recent activity history in prompt context
    - Implement `interpret_correction(message, recent_activities)` method
    - Parse response into CorrectionData dataclass (activity_id, updates dict)
    - Return None if no correction intent detected or ambiguous
    - _Requirements: 4.1, 4.2, 4.6_

  - [x] 8.9 Implement weekly summary generation
    - Create prompt template for weekly summary generation
    - Prompt should create motivating, conversational summary including activity counts, streaks, totals, and observations
    - Implement `generate_weekly_summary(activities, streak)` method
    - Compile WeeklySummaryData with activity statistics
    - Call LLM with summary prompt and return generated text
    - _Requirements: 10.2, 10.3, 10.4_

  - [x] 8.10 Implement reminder action interpretation
    - Create prompt template for reminder pause/modify intent detection
    - Include user's active reminders in prompt context
    - Implement `interpret_reminder_action(message, reminders)` method
    - Parse response into ReminderAction dataclass (action, reminder_id, modifications)
    - Support actions: pause, resume, modify, delete
    - _Requirements: 9.1, 9.2, 9.4, 9.5_

  - [x]* 8.11 Write unit tests for LLM service
    - Mock OpenRouter API responses
    - Test activity interpretation with valid response
    - Test activity interpretation with malformed response (fallback)
    - Test timeout handling
    - Test API error handling (429, 500, network errors)
    - Test correction interpretation with ambiguous messages
    - _Requirements: 15.4, 15.5, 15.6, 17.3_

- [x] 9. Checkpoint - LLM integration complete
  - Ensure LLM service correctly interprets activities, corrections, and generates summaries. Run property tests. Ask the user if questions arise.


- [x] 10. Implement Telegram bot service
  - [x] 10.1 Create TelegramService for bot operations
    - Create `app/services/telegram_service.py` with TelegramService class
    - Initialize python-telegram-bot Application with bot token from environment
    - Implement `send_message(chat_id, text)` method with error handling
    - Handle user blocking bot (Forbidden error) by logging and returning False
    - Handle rate limits with retry logic
    - Implement message truncation for messages exceeding Telegram limits
    - _Requirements: 3.4, 3.5, 8.2_

  - [x] 10.2 Implement message formatting utilities
    - Add `format_activity_confirmation(activity)` method to TelegramService
    - Format: "✅ Logged: {activity_type} {duration}min {distance}km ({calories} cal)"
    - Add `format_reminder(reminder)` method with reminder indicator
    - Add `format_weekly_summary(summary_text, dashboard_link)` method
    - Include user dashboard link in weekly summaries
    - _Requirements: 3.4, 8.2, 10.5_

  - [x] 10.3 Implement webhook handler for incoming messages
    - Create `app/routes/telegram.py` with webhook endpoint
    - Implement POST `/api/telegram/webhook` route
    - Parse Telegram Update object from request body
    - Validate webhook secret token if configured
    - Extract message text and chat_id from update
    - Handle /start command separately
    - Ignore messages from unlinked users (check database)
    - _Requirements: 2.1, 2.2, 2.5, 3.1_

  - [x] 10.4 Implement /start command for account linking
    - Add `/start` command handler in webhook route
    - Extract token from command parameters (/start TOKEN)
    - Call AuthService to validate linking token
    - Update user's telegram_chat_id in database
    - Send confirmation message "✅ Account linked! You can now log activities."
    - Ignore invalid or already-used tokens silently
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 10.5 Wire activity logging flow through Telegram
    - For non-command messages from linked users, call LLMService to interpret activity
    - Call CalorieService to estimate calories from interpreted activity data
    - Wait for Telegram send confirmation before creating Activity record in database
    - Call ActivityService to create activity log
    - Check for reminder completion and mark if applicable
    - Send confirmation message via TelegramService with activity details
    - Handle LLM failures with fallback message
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.4, 8.3_

  - [x] 10.6 Wire correction flow through Telegram
    - For messages that might be corrections, get recent activities (last 7 days)
    - Call LLMService to interpret correction intent
    - If correction identified, update activity via ActivityService
    - Send confirmation with updated activity details
    - If ambiguous, ask user for clarification
    - If no correction intent, treat as new activity (fallback to logging flow)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 10.7 Wire reminder action flow through Telegram
    - For messages that might be reminder commands, get user's active reminders
    - Call LLMService to interpret reminder action (pause, resume, modify, delete)
    - Execute action via ReminderService
    - Send confirmation message
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x]* 10.8 Write integration tests for Telegram webhook
    - Mock LLM service responses
    - Mock Telegram Bot API
    - Test /start command with valid token links account
    - Test /start with invalid token is ignored
    - Test activity logging message flow end-to-end
    - Test correction message flow
    - Test unlinked user messages are ignored
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.3, 3.4, 4.3, 4.4_

- [x] 11. Checkpoint - Telegram bot integration complete
  - Ensure webhook receives messages, interprets them, and sends confirmations. Test linking flow. Ask the user if questions arise.

- [x] 12. Implement scheduled tasks with APScheduler
  - [x] 12.1 Set up APScheduler for background tasks
    - Create `app/scheduler.py` with scheduler initialization
    - Configure BackgroundScheduler with AsyncIOScheduler
    - Add scheduler startup and shutdown to FastAPI lifespan events
    - _Requirements: 8.1, 10.1_

  - [x] 12.2 Implement reminder delivery job
    - Create scheduled job to run every minute
    - Call ReminderService to get due reminders
    - For each reminder, send message via TelegramService
    - Update last_sent_at timestamp after successful send
    - Implement retry logic (max 3 retries) for failed sends
    - Log failures for manual review
    - _Requirements: 8.1, 8.2, 8.4_

  - [x] 12.3 Implement weekly summary job
    - Create scheduled job to run every Sunday at 20:00 UTC
    - Query all active users
    - For each user, compile weekly activity data via ActivityService
    - Calculate streak via ActivityService
    - Generate summary via LLMService
    - Send summary via TelegramService with dashboard link
    - Handle LLM failures with fallback generic summary (stats only)
    - Ensure summary sent only once per week per user
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 12.4 Implement weekly activity data compilation
    - Create `app/services/summary_service.py` with SummaryService class
    - Implement `compile_weekly_data(user_id)` method
    - Query activities for last 7 days
    - Calculate totals: activity counts by type, total calories, total distance, total duration
    - Include streak count
    - Return WeeklySummaryData dataclass with all statistics
    - _Requirements: 10.1_

  - [x]* 12.5 Write property test for weekly activity compilation
    - **Property 5: Weekly Activity Compilation**
    - **Validates: Requirements 10.1**
    - Use Hypothesis to generate activities within week period
    - Verify compiled data includes all activities in date range
    - Verify counts and totals are correctly calculated

  - [x]* 12.6 Write unit tests for scheduled jobs
    - Mock ReminderService and TelegramService
    - Test reminder delivery job processes due reminders
    - Test duplicate reminder prevention within same period
    - Test weekly summary job compiles and sends summaries
    - Test summary fallback when LLM fails
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 10.1, 10.5, 10.6_

- [x] 13. Checkpoint - Scheduled tasks complete
  - Ensure reminders deliver on schedule and weekly summaries generate. Test scheduler. Ask the user if questions arise.

- [x] 14. Implement backend API routes
  - [x] 14.1 Create authentication routes
    - Create `app/routes/auth.py` with authentication endpoints
    - Implement POST `/api/auth/register` accepting email and password
    - Call AuthService to register user and create linking token
    - Return user_id, JWT token, linking_token, and bot_link in response
    - Implement POST `/api/auth/login` accepting email and password
    - Call AuthService to validate credentials and return JWT token
    - Implement GET `/api/auth/me` with authentication required
    - Return current user info (user_id, email, telegram_linked status)
    - Handle errors: duplicate email (409), invalid credentials (401)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 14.1, 14.2_

  - [x] 14.2 Create activity routes
    - Create `app/routes/activities.py` with activity endpoints
    - Implement GET `/api/activities` with authentication required
    - Accept query parameters: start_date, end_date (optional)
    - Call ActivityService to get activities for current user
    - Implement GET `/api/activities/streak` with authentication required
    - Call ActivityService to calculate current streak
    - Return current_streak and longest_streak (longest can be calculated or tracked separately)
    - Ensure data isolation (users can only access their own activities)
    - _Requirements: 6.4, 11.4, 14.4_

  - [x] 14.3 Create reminder routes
    - Create `app/routes/reminders.py` with reminder endpoints
    - Implement GET `/api/reminders` with authentication required
    - Return all reminders for current user
    - Implement POST `/api/reminders` with authentication required
    - Accept schedule, frequency, message in request body
    - Validate schedule format, return 400 if invalid
    - Call ReminderService to create reminder
    - Implement PUT `/api/reminders/{id}` with authentication required
    - Accept optional fields: schedule, frequency, message, active
    - Call ReminderService to update reminder
    - Implement DELETE `/api/reminders/{id}` with authentication required
    - Call ReminderService to delete reminder
    - Ensure users can only modify their own reminders
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 14.4_

  - [x] 14.4 Create dashboard route
    - Create `app/routes/dashboard.py` with dashboard endpoint
    - Implement GET `/api/dashboard/{user_id}` without authentication (shareable links)
    - Call ActivityService to get activities, streak, and monthly calendar data
    - Call ReminderService to get reminders for user
    - Return combined dashboard data: activities, streak, reminders, calendar data
    - Handle invalid user_id (404)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 12.1, 12.2, 12.3, 12.4_

  - [x] 14.5 Create admin routes
    - Create `app/routes/admin.py` with admin endpoints
    - Implement POST `/api/admin/users` with admin authentication required
    - Accept email, password, is_admin in request body
    - Call AuthService to create user account
    - Implement POST `/api/admin/calories` with admin authentication required
    - Accept activity_type, met_value, distance_factor in request body
    - Call CalorieService to create or update calorie formula
    - Implement PUT `/api/admin/calories/{activity_type}` with admin authentication
    - Update existing formula with new values
    - Return 403 Forbidden for non-admin users (no details)
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x] 14.6 Register all routes with FastAPI application
    - Import all route modules in `app/main.py`
    - Register routers with appropriate prefixes: /api/auth, /api/activities, /api/reminders, /api/dashboard, /api/telegram, /api/admin
    - Add OpenAPI documentation tags for route organization
    - _Requirements: All API routes_

  - [x]* 14.7 Write integration tests for API routes
    - Use FastAPI TestClient for route testing
    - Test user registration and login flows
    - Test protected routes require valid JWT
    - Test activity CRUD with authentication
    - Test reminder CRUD with authentication
    - Test dashboard data retrieval
    - Test admin routes require admin role
    - Test error responses (400, 401, 403, 404, 409)
    - _Requirements: 1.1, 1.2, 1.3, 6.4, 7.1, 13.1, 14.1, 14.2, 14.3, 14.4_

- [x] 15. Checkpoint - Backend API complete
  - Ensure all API routes work correctly. Test with HTTP client or Postman. Run integration tests. Ask the user if questions arise.


- [x] 16. Implement React frontend application
  - [x] 16.1 Initialize React project with Vite and TypeScript
    - Create React project using Vite with TypeScript template
    - Install dependencies: react-router-dom, axios, recharts (or chart.js), date-fns
    - Set up project structure: `src/components/`, `src/contexts/`, `src/services/`, `src/types/`, `src/pages/`
    - Configure Vite proxy for API requests to backend
    - Set up environment variables for API base URL
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 16.2 Create TypeScript interfaces for API data types
    - Create `src/types/index.ts` with interfaces
    - Define User interface (id, email, telegram_linked)
    - Define Activity interface (id, activityType, duration, distance, calories, timestamp)
    - Define Reminder interface (id, schedule, frequency, message, active)
    - Define DashboardData interface (activities, streak, reminders, calendar)
    - Define API response types for authentication, activities, reminders
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 16.3 Create API client service
    - Create `src/services/api.ts` with API client using axios
    - Set base URL from environment variables
    - Configure authorization header interceptor for JWT token
    - Implement authentication methods: register, login
    - Implement activity methods: getActivities, getStreak
    - Implement reminder methods: getReminders, createReminder, updateReminder, deleteReminder
    - Implement dashboard method: getDashboardData
    - Handle errors and return appropriate error messages
    - _Requirements: 1.1, 6.4, 7.1, 14.1, 14.2_

  - [x] 16.4 Create AuthContext for global authentication state
    - Create `src/contexts/AuthContext.tsx` with React Context
    - Manage authentication state: user, token, isAuthenticated
    - Store JWT token in localStorage
    - Implement login, logout, and register functions
    - Provide useAuth hook for components to access auth state
    - Automatically load token from localStorage on mount
    - _Requirements: 1.1, 14.1, 14.2_

  - [x] 16.5 Create registration page
    - Create `src/pages/RegisterPage.tsx` with registration form
    - Form fields: email (required), password (required)
    - Call API client register method on submit
    - Display linking token and bot link after successful registration
    - Show bot link as clickable button that opens Telegram
    - Handle validation errors and display to user
    - Navigate to login after registration
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 16.6 Create login page
    - Create `src/pages/LoginPage.tsx` with login form
    - Form fields: email (required), password (required)
    - Call API client login method on submit
    - Store JWT token in AuthContext and localStorage
    - Navigate to dashboard after successful login
    - Display error message for invalid credentials
    - Include link to registration page
    - _Requirements: 1.1, 14.1, 14.2_

  - [x] 16.7 Create calendar view component
    - Create `src/components/Calendar.tsx` for monthly calendar display
    - Accept month and year as props
    - Fetch activities for the selected month via API
    - Display calendar grid with days of the month
    - Mark days with logged activities (visual indicator like colored dot)
    - Display reminders on their scheduled dates (different visual indicator)
    - Visually distinguish activity days from reminder days
    - Allow navigation between months (previous/next buttons)
    - _Requirements: 6.1, 12.1, 12.2, 12.3_

  - [x] 16.8 Create activity list component
    - Create `src/components/ActivityList.tsx` for recent activities
    - Fetch recent activities via API client
    - Display list with activity details: type, duration, distance, calories, timestamp
    - Format timestamp in human-readable format (e.g., "2 hours ago", "Jan 15 at 10:30 AM")
    - Show empty state when no activities exist
    - Limit display to last 10-20 activities with "Load more" option
    - _Requirements: 6.3_

  - [x] 16.9 Create streak display component
    - Create `src/components/StreakDisplay.tsx` for streak counter
    - Fetch streak data via API client
    - Display current streak count prominently
    - Add visual element (e.g., fire emoji 🔥 or progress bar)
    - Optionally display longest streak
    - Show motivating message when streak is high
    - _Requirements: 6.2, 11.4_

  - [x] 16.10 Create dashboard page with all components
    - Create `src/pages/DashboardPage.tsx` as main dashboard
    - Include StreakDisplay, Calendar, and ActivityList components
    - Fetch dashboard data via API client
    - Display user greeting with email
    - Show Telegram linking status (linked/not linked)
    - Add logout button
    - Ensure responsive layout for mobile and desktop
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 16.11 Set up React Router with protected routes
    - Configure React Router in `src/App.tsx`
    - Define routes: /register, /login, /dashboard, /dashboard/:userId (shareable)
    - Implement ProtectedRoute component that checks authentication
    - Redirect unauthenticated users to login page
    - Redirect authenticated users from login/register to dashboard
    - _Requirements: 6.6, 14.1_

  - [x] 16.12 Style components with CSS or UI library
    - Add CSS styling to all components
    - Use consistent color scheme and typography
    - Ensure mobile-responsive design
    - Add loading states for async operations
    - Add error states with user-friendly messages
    - Optionally integrate UI library (Material-UI, Chakra UI, or Tailwind CSS)
    - _Requirements: 6.1, 6.2, 6.3_

  - [x]* 16.13 Write component tests for critical UI flows
    - Use React Testing Library for component tests
    - Test registration form submission
    - Test login form submission
    - Test calendar rendering with activities
    - Test activity list display
    - Test streak display updates
    - Test protected route redirection
    - _Requirements: 1.1, 6.1, 6.2, 6.3, 14.1_

- [x] 17. Checkpoint - Frontend application complete
  - Ensure React app connects to backend, displays data correctly, and handles authentication. Test all pages. Ask the user if questions arise.

- [x] 18. Set up deployment configuration
  - [x] 18.1 Create environment configuration files
    - Create `.env.example` for backend with all required environment variables
    - Document each variable: DATABASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_URL, OPENROUTER_API_KEY, JWT_SECRET_KEY, etc.
    - Create `.env.example` for frontend with API_BASE_URL
    - Add `.env` to `.gitignore`
    - _Requirements: All infrastructure_

  - [x] 18.2 Create Docker configuration (optional for local development)
    - Create `Dockerfile` for backend application
    - Create `docker-compose.yml` with backend, frontend, and PostgreSQL services
    - Configure PostgreSQL with health checks
    - Configure volume mounts for development
    - Document Docker usage in README
    - _Requirements: Infrastructure_

  - [x] 18.3 Configure deployment for Railway or Render
    - Create `render.yaml` or Railway configuration file
    - Configure web service for backend (FastAPI)
    - Configure static site for frontend (React build)
    - Configure PostgreSQL database service
    - Set build commands: backend (`pip install -r requirements.txt`), frontend (`npm run build`)
    - Set start commands: backend (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`)
    - Configure environment variables in platform dashboard
    - _Requirements: Infrastructure_

  - [x] 18.4 Set up Telegram webhook configuration
    - Create script to set Telegram webhook URL: `scripts/set_webhook.py`
    - Use Telegram Bot API setWebhook method
    - Set webhook URL to: `https://your-domain.com/api/telegram/webhook`
    - Set webhook secret token for validation
    - Verify webhook is set correctly
    - Document webhook setup in README
    - _Requirements: 2.1, 3.1_

  - [x] 18.5 Configure database migrations for production
    - Ensure Alembic migrations run on deployment
    - Add migration command to deployment start script
    - Set up automatic database backups (platform feature)
    - Test migration rollback procedure
    - _Requirements: 16.5_

  - [x] 18.6 Add logging and monitoring configuration
    - Configure structured logging with JSON format for production
    - Set up log levels based on environment (DEBUG for dev, INFO for prod)
    - Add request/response logging middleware
    - Configure error tracking (optional: Sentry integration)
    - Set up health check endpoint: GET `/health`
    - _Requirements: Infrastructure_

- [x] 19. Checkpoint - Deployment ready
  - Ensure deployment configuration is complete. Test deployment to staging environment. Ask the user if questions arise.

- [x] 20. End-to-end testing and final integration
  - [x]* 20.1 Run comprehensive end-to-end test: new user onboarding
    - Register new user on web dashboard
    - Verify linking token and bot link displayed
    - Click bot link (or manually send /start command with token)
    - Verify account linked in Telegram
    - Verify Telegram linked status shows in web dashboard
    - _Requirements: 1.1, 1.2, 1.5, 1.6, 2.1, 2.2, 2.4_

  - [x]* 20.2 Run comprehensive end-to-end test: activity logging journey
    - Send activity message in Telegram: "Ran 5km this morning"
    - Verify confirmation message received in Telegram with calories
    - Log into web dashboard
    - Verify activity appears in activity list
    - Verify activity appears in calendar
    - Verify streak updated correctly
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.1, 5.4, 6.1, 6.2, 6.3, 11.4_

  - [x]* 20.3 Run comprehensive end-to-end test: correction flow
    - Log initial activity in Telegram
    - Send correction message: "Actually it was 6km not 5km"
    - Verify updated confirmation received
    - Check web dashboard shows corrected activity
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 6.3_

  - [x]* 20.4 Run comprehensive end-to-end test: reminder cycle
    - Create reminder via web API (POST /api/reminders)
    - Wait for scheduled time or trigger scheduler manually
    - Verify reminder message received in Telegram
    - Log matching activity in Telegram
    - Verify reminder marked as completed
    - _Requirements: 7.1, 7.2, 8.1, 8.2, 8.3_

  - [x]* 20.5 Run comprehensive end-to-end test: weekly summary
    - Create multiple activities throughout the week (seed data or manual)
    - Trigger weekly summary job manually or wait for Sunday 20:00
    - Verify summary message received in Telegram with statistics and dashboard link
    - Click dashboard link and verify data matches summary
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x]* 20.6 Verify error handling and edge cases
    - Test LLM timeout/failure (mock or temporary API issue)
    - Test database connection failure
    - Test Telegram bot blocked by user
    - Test invalid JWT token (expired, malformed)
    - Test unauthorized access attempts
    - Verify all errors logged appropriately
    - Verify user receives friendly error messages
    - _Requirements: 14.3, 15.5, 15.6, 17.3_

- [x] 21. Final checkpoint - System complete
  - Ensure all end-to-end flows work correctly. Verify error handling. Run all tests (unit, property, integration, E2E). Ask the user if questions arise.

- [x] 22. Documentation and README
  - [x] 22.1 Write comprehensive README documentation
    - Add project overview and features
    - Document architecture and technology stack
    - Add setup instructions for local development
    - Document environment variables and configuration
    - Add API documentation or link to OpenAPI docs
    - Document deployment process
    - Add usage examples and screenshots
    - Include troubleshooting section
    - _Requirements: All_

  - [x] 22.2 Create API documentation
    - Document all API endpoints with request/response examples
    - Use FastAPI automatic OpenAPI documentation
    - Ensure OpenAPI docs accessible at `/docs` and `/redoc`
    - _Requirements: All API routes_

  - [x] 22.3 Add code comments and docstrings
    - Add docstrings to all service classes and methods
    - Document complex business logic with inline comments
    - Add type hints to all functions
    - Document LLM prompt templates and their purposes
    - _Requirements: All_

## Notes

- **Language**: All implementation is in **Python 3.10+** for backend (FastAPI, SQLAlchemy) and **TypeScript** for frontend (React 18+)
- **Testing Philosophy**: Property-based tests validate universal correctness properties; unit tests validate specific examples and edge cases; integration tests validate component interaction
- **Optional Tasks**: Tasks marked with `*` are optional and can be skipped for faster MVP delivery, but are recommended for production readiness
- **Incremental Development**: Each task builds on previous work. Validate core functionality early through code execution, not just by writing tests
- **Requirements Traceability**: Each task explicitly references the requirements it implements for full coverage verification
- **Checkpoints**: Ensure incremental validation at reasonable breaks to catch issues early
- **Error Handling**: All services include comprehensive error handling, logging, and fallback mechanisms
- **Security**: Authentication, authorization, and data isolation are enforced throughout the system
- **Performance**: Database indexes, connection pooling, and async operations ensure system scales efficiently
- **Deployment**: Configuration supports free-tier platforms (Render, Railway) with PostgreSQL, zero infrastructure cost


## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["1.4", "1.5"] },
    { "id": 3, "tasks": ["3.1", "5.1", "6.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "5.3", "6.2"] },
    { "id": 5, "tasks": ["3.4", "5.2", "6.3"] },
    { "id": 6, "tasks": ["3.5", "3.6", "5.4", "6.4"] },
    { "id": 7, "tasks": ["3.7", "6.5", "6.6"] },
    { "id": 8, "tasks": ["3.8", "8.1"] },
    { "id": 9, "tasks": ["8.2", "8.3"] },
    { "id": 10, "tasks": ["8.4", "8.5", "8.6", "8.7"] },
    { "id": 11, "tasks": ["8.8", "8.9", "8.10"] },
    { "id": 12, "tasks": ["8.11", "10.1"] },
    { "id": 13, "tasks": ["10.2", "10.3"] },
    { "id": 14, "tasks": ["10.4", "10.5"] },
    { "id": 15, "tasks": ["10.6", "10.7"] },
    { "id": 16, "tasks": ["10.8", "12.1"] },
    { "id": 17, "tasks": ["12.2", "12.3", "12.4"] },
    { "id": 18, "tasks": ["12.5", "12.6"] },
    { "id": 19, "tasks": ["14.1", "14.2", "14.3"] },
    { "id": 20, "tasks": ["14.4", "14.5"] },
    { "id": 21, "tasks": ["14.6"] },
    { "id": 22, "tasks": ["14.7", "16.1"] },
    { "id": 23, "tasks": ["16.2", "16.3"] },
    { "id": 24, "tasks": ["16.4"] },
    { "id": 25, "tasks": ["16.5", "16.6"] },
    { "id": 26, "tasks": ["16.7", "16.8", "16.9"] },
    { "id": 27, "tasks": ["16.10"] },
    { "id": 28, "tasks": ["16.11", "16.12"] },
    { "id": 29, "tasks": ["16.13", "18.1"] },
    { "id": 30, "tasks": ["18.2", "18.3"] },
    { "id": 31, "tasks": ["18.4", "18.5", "18.6"] },
    { "id": 32, "tasks": ["20.1", "20.2", "20.3"] },
    { "id": 33, "tasks": ["20.4", "20.5"] },
    { "id": 34, "tasks": ["20.6"] },
    { "id": 35, "tasks": ["22.1", "22.2", "22.3"] }
  ]
}
```


## Phase 2: Enhanced Features

- [ ] 23. Strength training detailed logging
  - [ ] 23.1 Update LLM prompt for multi-set strength parsing
    - Modify system prompt to extract: exercise name, sets array [{reps, weight_kg}]
    - Support formats: "10x4 con 50kg press banca", "10 reps 40kg, 10 reps 50kg, 8x60kg"
    - Return activity_type as exercise name (e.g. "press banca") not "strength"/"weights"
    - Include total volume calculation (sets × reps × weight)
    - _Requirements: strength logging_

  - [ ] 23.2 Update Activity model for strength data
    - Add `sets_data` JSON column to Activity (nullable, for strength exercises)
    - Format: [{"reps": 10, "weight_kg": 50}, {"reps": 10, "weight_kg": 50}, ...]
    - Add `exercise_name` field (e.g. "Press Banca", "Sentadillas")
    - Keep backward compatible with existing activities
    - _Requirements: strength logging_

  - [ ] 23.3 Update bot confirmation for strength exercises
    - Show exercise name (not "Strength" or "Weights")
    - Show sets detail: "3 series: 10×40kg, 10×50kg, 8×60kg"
    - Show total volume instead of calories (e.g. "Vol: 1,880 kg")
    - _Requirements: strength logging_

  - [ ] 23.4 Update dashboard to display strength exercises
    - Show sets/reps/weight for strength activities instead of calories
    - Show exercise name properly in activity list
    - _Requirements: strength logging_

- [ ] 24. Habit goals system
  - [ ] 24.1 Create Goal model
    - New table `goals` with: id, user_id, activity_type, target_frequency (times per period), period (daily/weekly/monthly), target_count, created_at, active
    - Examples: "correr 3 veces por semana", "meditar todos los días"
    - _Requirements: habit goals_

  - [ ] 24.2 Add goal intent to LLM prompt
    - Detect "quiero correr 3 veces por semana" as goal creation
    - Support: daily (todos los días), weekly (X veces por semana), specific days
    - _Requirements: habit goals_

  - [ ] 24.3 Implement goal progress tracking
    - Calculate current progress: how many times completed this period
    - Show progress in confirmation: "🎯 Meta correr: 2/3 esta semana"
    - Auto-detect when goal is met: "🏆 ¡Meta cumplida!"
    - _Requirements: habit goals_

  - [ ] 24.4 Show goals in dashboard
    - Progress bars or circular indicators for each goal
    - Show completed/target for current period
    - Color coding: green (on track), yellow (behind), red (missed)
    - _Requirements: habit goals_

  - [ ] 24.5 Goal management via bot
    - "mis metas" → list active goals with progress
    - "eliminar meta de correr" → deactivate goal
    - _Requirements: habit goals_

- [ ] 25. Advanced reminder scheduling
  - [ ] 25.1 Update Reminder model for flexible schedules
    - Add `schedule_type` field: "daily", "weekdays", "specific_days", "once", "interval"
    - Add `schedule_days` field: JSON array of days (e.g. [1,3] = lunes y miércoles, [5,6] = fin de semana)
    - Add `schedule_date` field: for one-time reminders (e.g. "2026-07-06")
    - Add `schedule_interval` field: "every_other_week", "biweekly"
    - _Requirements: advanced reminders_

  - [ ] 25.2 Update LLM prompt for advanced reminder parsing
    - "recuérdame correr los lunes y miércoles a las 7:30" → specific_days=[0,2], schedule="07:30"
    - "el lunes 6 de julio a las 8am ir al Dr" → once, schedule_date="2026-07-06", schedule="08:00"
    - "recordatorio de gym solo fines de semana" → specific_days=[5,6]
    - "cada 2 semanas ir al dentista" → interval="biweekly"
    - _Requirements: advanced reminders_

  - [ ] 25.3 Update scheduler for flexible delivery
    - Check day-of-week against schedule_days
    - Check specific date for one-time reminders
    - Auto-delete or deactivate one-time reminders after delivery
    - Handle "every other week" logic with last_sent_at
    - _Requirements: advanced reminders_

  - [ ] 25.4 Update reminder display in dashboard and bot
    - Show schedule in human-readable format: "Lun y Mié a las 7:30"
    - Show one-time reminders with date: "6 Jul 08:00 — Ir al Dr"
    - Distinguish between recurring and one-time in the UI
    - _Requirements: advanced reminders_

- [ ] 26. Checkpoint - Phase 2 complete
  - All enhanced features working: strength logging, goals, advanced reminders
  - Deploy and verify in production


- [ ] 27. Interactive calendar and layout fix
  - [ ] 27.1 Make calendar days clickable with activity modal
    - When user clicks a day in the calendar, open a modal/popup
    - Modal shows all activities for that day with details (type, duration, distance, calories, time)
    - Show strength exercises with sets/reps/weight
    - Show life activities with their details
    - Modal should be dismissible by clicking outside or pressing X
    - _Requirements: dashboard UX_

  - [ ] 27.2 Move reminders above challenges in dashboard layout
    - Reorder DashboardPage: Stats → Reminders → Challenges → Goals → Calendar → Activity Feed
    - _Requirements: dashboard UX_
