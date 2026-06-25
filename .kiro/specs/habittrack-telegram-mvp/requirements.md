# Requirements Document

## Introduction

HabitTrack is a habit and sports tracking application that uses Telegram as the logging interface with a web dashboard for data visualization. The system allows users to log activities through free-form natural language messages in Telegram, which are interpreted by an LLM, stored in a PostgreSQL database, and displayed on a web dashboard. The system supports activity logging, corrections, reminders, and weekly summaries to help users track their habits and sports activities with minimal friction.

## Glossary

- **HabitTrack_System**: The complete system including Telegram bot, web backend, database, and web dashboard
- **Telegram_Bot**: The Telegram bot interface that receives user messages and sends responses
- **Web_Dashboard**: The React-based web interface where users view their activity data
- **Backend_API**: The FastAPI server that processes requests, manages data, and coordinates with the LLM
- **LLM_Service**: The OpenRouter-based language model service that interprets logs and generates summaries
- **Activity_Log**: A recorded instance of a habit or sports activity with metadata (type, duration, distance, calories, timestamp)
- **User_Account**: A registered user with credentials, linked Telegram account, and activity history
- **Linking_Token**: A unique token used to connect a Telegram user with a web account
- **Reminder**: A scheduled notification sent via Telegram to prompt a user to log a habit or activity
- **Weekly_Summary**: A conversational message generated weekly summarizing user activity and progress
- **Streak**: The count of consecutive days a user has logged at least one activity
- **Correction_Message**: A free-form message from the user that modifies a previously logged activity

## Requirements

### Requirement 1: User Registration

**User Story:** As a new user, I want to register on the web platform, so that I can create an account and access the HabitTrack system.

#### Acceptance Criteria

1. THE Web_Dashboard SHALL provide a registration form accepting email and password
2. WHEN a user submits valid registration credentials, THE Backend_API SHALL create a User_Account in the database
3. WHEN a user submits invalid registration credentials, THE Backend_API SHALL return a descriptive error message
4. WHEN a user submits valid registration credentials, THE Backend_API SHALL NOT return error messages
5. WHEN a User_Account is created, THE Backend_API SHALL generate a unique Linking_Token for that account
6. WHEN a User_Account is created, THE Web_Dashboard SHALL display the Telegram bot link with the Linking_Token

### Requirement 2: Telegram Account Linking

**User Story:** As a registered user, I want to link my Telegram account to my web account, so that I can log activities via Telegram.

#### Acceptance Criteria

1. WHEN a user clicks the bot link with a valid Linking_Token, THE Telegram_Bot SHALL open in Telegram with the token as a start parameter
2. WHEN a user sends "/start TOKEN" with a valid Linking_Token, THE Backend_API SHALL associate the telegram_user_id with the corresponding User_Account
3. WHEN a user sends "/start TOKEN" with an invalid Linking_Token, THE Telegram_Bot SHALL ignore the message
4. WHEN a user sends "/start TOKEN" with a Linking_Token already used, THE Backend_API SHALL reject the linking attempt
5. WHEN a message is received from an unlinked telegram_user_id, THE Telegram_Bot SHALL ignore the message

### Requirement 3: Free-Form Activity Logging

**User Story:** As a linked user, I want to log activities using natural language in Telegram, so that I can record my habits and sports without following rigid formats.

#### Acceptance Criteria

1. WHEN a linked user sends a free-form activity message, THE Backend_API SHALL send the message to the LLM_Service for interpretation
2. WHEN the LLM_Service interprets a message, THE LLM_Service SHALL extract activity type, duration, distance, and other relevant metadata
3. WHEN the LLM_Service successfully extracts activity data, THE Backend_API SHALL wait until the Telegram_Bot confirms the message can be sent before creating an Activity_Log in the database
4. WHEN an Activity_Log is created, THE Telegram_Bot SHALL send a confirmation message showing the logged activity details
5. THE Telegram_Bot SHALL send confirmation messages without requesting additional input from the user

### Requirement 4: Activity Correction

**User Story:** As a user, I want to correct logged activities using natural language, so that I can fix mistakes without complex interfaces.

#### Acceptance Criteria

1. WHEN a linked user sends a Correction_Message, THE Backend_API SHALL send the message and recent Activity_Log history to the LLM_Service
2. WHEN the LLM_Service identifies a correction intent, THE LLM_Service SHALL extract which Activity_Log to modify and what fields to update
3. WHEN the LLM_Service identifies a valid correction, THE Backend_API SHALL update the corresponding Activity_Log in the database
4. WHEN an Activity_Log is updated, THE Telegram_Bot SHALL send a confirmation message showing the updated activity details
5. WHEN the LLM_Service identifies a correction intent but the correction is ambiguous or unclear, THE Telegram_Bot SHALL ask the user for clarification
6. WHEN the LLM_Service cannot identify which Activity_Log to correct, THE Backend_API SHALL treat the message as a new activity log

### Requirement 5: Calorie Estimation

**User Story:** As a user, I want the system to estimate calories burned for my activities, so that I can track energy expenditure.

#### Acceptance Criteria

1. WHEN an Activity_Log is created with activity type and duration, THE Backend_API SHALL calculate estimated calories burned
2. THE Backend_API SHALL use activity-specific calorie formulas based on activity type and duration
3. WHEN distance is provided for an activity, THE Backend_API SHALL incorporate distance into calorie calculation
4. WHEN an Activity_Log with calories is confirmed, THE Telegram_Bot SHALL include the calorie estimate in the confirmation message

### Requirement 6: Dashboard Data Display

**User Story:** As a user, I want to view my logged activities on a web dashboard, so that I can see my progress over time.

#### Acceptance Criteria

1. THE Web_Dashboard SHALL display a monthly calendar view showing dates with logged activities
2. THE Web_Dashboard SHALL display a graph showing the current activity streak count
3. THE Web_Dashboard SHALL display a list of recent Activity_Log entries with details
4. WHEN a user accesses the dashboard, THE Backend_API SHALL retrieve Activity_Log entries for that User_Account
5. WHEN the Backend_API fails to retrieve Activity_Log entries, THE Web_Dashboard SHALL display empty or cached data
6. THE Web_Dashboard SHALL be accessible via a unique user link containing the user identifier

### Requirement 7: Reminder Configuration

**User Story:** As a user, I want to configure reminders for habits, so that I receive prompts to log activities at specific times.

#### Acceptance Criteria

1. THE Backend_API SHALL provide endpoints to create, update, and delete Reminder configurations
2. WHEN a Reminder is created, THE Backend_API SHALL store the schedule, frequency, and message content in the database
3. THE Backend_API SHALL validate that Reminder schedules are properly formatted
4. WHEN a Reminder configuration is invalid, THE Backend_API SHALL return a descriptive error message

### Requirement 8: Reminder Delivery

**User Story:** As a user, I want to receive reminders via Telegram, so that I am prompted to complete my habits at the right time.

#### Acceptance Criteria

1. WHEN a Reminder schedule time is reached, THE Backend_API SHALL send the reminder message via the Telegram_Bot
2. THE Telegram_Bot SHALL format reminder messages with the configured message content and a reminder indicator
3. WHEN a user logs an activity mentioned in a Reminder, THE Backend_API SHALL mark that Reminder as completed for the current period regardless of whether the reminder was delivered
4. THE Backend_API SHALL not send duplicate Reminder messages within the same scheduled period

### Requirement 9: Reminder Pause and Modification

**User Story:** As a user, I want to pause or modify reminders using natural language, so that I can control notifications easily.

#### Acceptance Criteria

1. WHEN a linked user sends a message requesting to pause a Reminder, THE Backend_API SHALL send the message to the LLM_Service
2. WHEN the LLM_Service identifies a pause intent, THE Backend_API SHALL deactivate the corresponding Reminder
3. WHEN a Reminder is paused, THE Telegram_Bot SHALL send a confirmation message
4. WHEN a linked user sends a message requesting to modify a Reminder, THE LLM_Service SHALL extract the modification parameters
5. WHEN a Reminder modification is identified, THE Backend_API SHALL update the Reminder configuration in the database

### Requirement 10: Weekly Summary Generation

**User Story:** As a user, I want to receive a weekly summary of my activities, so that I can review my progress in a conversational format.

#### Acceptance Criteria

1. WHEN a week ends for a User_Account, THE Backend_API SHALL compile Activity_Log data for that week
2. WHEN weekly Activity_Log data is compiled, THE Backend_API SHALL send it to the LLM_Service for summary generation
3. THE LLM_Service SHALL generate a conversational summary in a human, motivating tone
4. THE LLM_Service SHALL include activity counts, streaks, totals, and observations in the summary
5. WHEN a summary is generated, THE Telegram_Bot SHALL send the summary message including a link to the user's Web_Dashboard
6. WHEN a week ends with zero activities, THE Backend_API SHALL still send a weekly summary message

### Requirement 11: Activity Streak Calculation

**User Story:** As a user, I want the system to track my activity streak, so that I can see how many consecutive days I have logged activities.

#### Acceptance Criteria

1. WHEN Activity_Log entries are retrieved for a User_Account, THE Backend_API SHALL calculate the current streak count
2. THE Backend_API SHALL define a streak as consecutive calendar days with at least one Activity_Log
3. WHEN a day has no Activity_Log entries, THE Backend_API SHALL reset the streak count to zero
4. THE Backend_API SHALL include streak count in weekly summaries and dashboard data
5. WHEN a User_Account has no Activity_Log entries, THE Backend_API SHALL display a streak count of zero

### Requirement 12: Dashboard Calendar Reminder Display

**User Story:** As a user, I want to see configured reminders on my dashboard calendar, so that I can view scheduled habits alongside logged activities.

#### Acceptance Criteria

1. WHEN the Web_Dashboard displays the monthly calendar, THE Backend_API SHALL include Reminder data for the displayed month
2. THE Web_Dashboard SHALL display Reminder entries on their scheduled dates in the calendar view
3. THE Web_Dashboard SHALL visually distinguish Reminder entries from Activity_Log entries in the calendar
4. THE Web_Dashboard SHALL display both completed and pending Reminder entries for each day

### Requirement 13: Admin User Management

**User Story:** As an admin, I want to configure user accounts and sports definitions, so that I can manage the system during MVP.

#### Acceptance Criteria

1. WHERE an admin role is assigned, THE Backend_API SHALL provide endpoints to create, update, and delete User_Account records
2. WHERE an admin role is assigned, THE Backend_API SHALL provide endpoints to define and modify sports activity types
3. WHERE an admin role is assigned, THE Backend_API SHALL provide endpoints to configure calorie formulas for activity types
4. WHEN a non-admin user attempts to access admin endpoints, THE Backend_API SHALL silently deny access without returning error details

### Requirement 14: Authentication and Authorization

**User Story:** As a user, I want my data to be protected by authentication, so that only I can access my activity logs and dashboard.

#### Acceptance Criteria

1. WHEN a user attempts to access the Web_Dashboard, THE Backend_API SHALL require valid authentication credentials
2. THE Backend_API SHALL use session tokens or JWT for authenticated requests
3. WHEN an unauthenticated request is made to protected endpoints, THE Backend_API SHALL return an authentication error
4. THE Backend_API SHALL ensure that users can only access their own Activity_Log entries and Reminder configurations

### Requirement 15: LLM Service Integration

**User Story:** As the system, I want to integrate with OpenRouter free LLM models, so that I can interpret logs and generate summaries without cost.

#### Acceptance Criteria

1. THE Backend_API SHALL connect to OpenRouter API using configured API credentials
2. THE Backend_API SHALL use nvidia/nemotron-3-ultra-550b-a55b:free model for activity log interpretation
3. THE Backend_API SHALL use nvidia/nemotron-3-ultra-550b-a55b:free model for weekly summary generation
4. WHEN OpenRouter is unavailable, THE Backend_API SHALL support fallback to alternative LLM services or local models for log interpretation
5. WHEN the LLM_Service request fails, THE Backend_API SHALL log the error and return a fallback response
6. WHEN error logging fails, THE Backend_API SHALL treat the entire error handling as failed
7. THE Backend_API SHALL format prompts with clear instructions for log interpretation and summary generation

### Requirement 16: Database Schema Management

**User Story:** As a developer, I want a well-defined database schema, so that activity data is stored consistently and efficiently.

#### Acceptance Criteria

1. THE Backend_API SHALL create and maintain tables for User_Account, Activity_Log, Reminder, and Linking_Token entities
2. THE Backend_API SHALL enforce foreign key relationships between User_Account and related entities
3. THE Backend_API SHALL store Activity_Log entries with timestamp, activity_type, duration, distance, calories, and user_id fields
4. THE Backend_API SHALL store Reminder entries with schedule, frequency, message, active_status, and user_id fields
5. THE Backend_API SHALL use database migrations to manage schema changes

### Requirement 17: Parser and Pretty Printer for LLM Responses

**User Story:** As a developer, I want to reliably parse LLM responses into structured data, so that extracted activity information is correctly stored.

#### Acceptance Criteria

1. WHEN the LLM_Service returns activity interpretation, THE Backend_API SHALL parse the response into structured fields
2. THE Backend_API SHALL validate that parsed activity data contains required fields
3. WHEN parsing fails, THE Backend_API SHALL log the error and return a user-friendly error message
4. THE Backend_API SHALL format activity data into a consistent JSON schema before sending to the LLM_Service
5. FOR ALL valid activity data structures, parsing then formatting then parsing SHALL produce an equivalent data structure (round-trip property)
