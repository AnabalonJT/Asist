# Requirements Document

## Introduction

The Admin Panel is an administrator-only section of HabitTrack that lets a user with administrative privileges see how the rest of the users are using the application. It provides a system-wide usage overview (aggregate totals and active-user counts) and a per-user usage breakdown (goals, reminders, activities, and challenges owned by each user), plus optional detail for a single user.

The feature reuses the existing authentication system: the `is_admin` flag on the User account and the `get_current_admin` FastAPI dependency that returns HTTP 403 for non-admin requests. All backend endpoints live under `/api/admin`. On the frontend, the panel is gated behind the current user's `is_admin` flag so that non-administrators neither see nor can reach it.

The panel exposes only aggregate and usage-level information. It does not expose password hashes, JWTs, or raw Telegram chat identifiers; Telegram association is surfaced only as a "linked / not linked" state.

## Glossary

- **Admin_Panel**: The administrator-only feature comprising the backend `/api/admin` endpoints and the frontend administration view.
- **Admin_API**: The set of backend HTTP endpoints under the `/api/admin` prefix that serve Admin_Panel data.
- **Admin_View**: The frontend React page(s) that render Admin_Panel data.
- **Administrator**: An authenticated User whose `is_admin` field is `true`.
- **Non_Administrator**: An authenticated User whose `is_admin` field is `false`.
- **User_Account**: A record in the `users` table, having `id`, `email`, `is_admin`, `telegram_chat_id`, `timezone`, `show_calories`, `created_at`, and `updated_at`.
- **Telegram_Linked_State**: A boolean derived value that is `true` when a User_Account has a non-null `telegram_chat_id`, and `false` otherwise.
- **System_Overview**: The aggregate usage statistics computed across all User_Accounts.
- **User_Usage_Summary**: The per-user usage record containing the user's `email`, `Telegram_Linked_State`, `created_at`, and counts of that user's activities, goals, reminders, and challenges.
- **User_Usage_Detail**: The extended usage record for a single User_Account, adding recent activity counts and the timestamp of that user's most recent activity.
- **Active_User**: A User_Account that owns at least one Activity whose `timestamp` falls within a given trailing time window (7 or 30 days).
- **Get_Current_Admin**: The existing FastAPI dependency that resolves the authenticated User and rejects the request with HTTP 403 when the User is not an Administrator.

## Requirements

### Requirement 1: Restrict Admin API access to administrators

**User Story:** As an administrator, I want the admin endpoints to reject non-administrators, so that user usage data is only visible to authorized administrators.

#### Acceptance Criteria

1. WHEN a request to any Admin_API endpoint is received from an authenticated Administrator, THE Admin_API SHALL process the request and return the requested data with HTTP status 200.
2. IF a request to any Admin_API endpoint is received from an authenticated Non_Administrator, THEN THE Admin_API SHALL reject the request with HTTP status 403.
3. IF a request to any Admin_API endpoint is received without a valid authentication token, THEN THE Admin_API SHALL reject the request with HTTP status 401.
4. THE Admin_API SHALL enforce authorization for every `/api/admin` endpoint using the Get_Current_Admin dependency.

### Requirement 2: Provide a system-wide usage overview

**User Story:** As an administrator, I want to see aggregate usage totals across all users, so that I can gauge overall adoption of the application.

#### Acceptance Criteria

1. WHEN an Administrator requests the System_Overview, THE Admin_API SHALL return the total count of User_Accounts.
2. WHEN an Administrator requests the System_Overview, THE Admin_API SHALL return the count of User_Accounts whose Telegram_Linked_State is `true`.
3. WHEN an Administrator requests the System_Overview, THE Admin_API SHALL return the total count of activities across all User_Accounts.
4. WHEN an Administrator requests the System_Overview, THE Admin_API SHALL return the total count of goals across all User_Accounts.
5. WHEN an Administrator requests the System_Overview, THE Admin_API SHALL return the total count of reminders across all User_Accounts.
6. WHEN an Administrator requests the System_Overview, THE Admin_API SHALL return the total count of challenges across all User_Accounts.
7. WHEN an Administrator requests the System_Overview, THE Admin_API SHALL return the count of Active_Users within the trailing 7-day window.
8. WHEN an Administrator requests the System_Overview, THE Admin_API SHALL return the count of Active_Users within the trailing 30-day window.

### Requirement 3: Provide a per-user usage list

**User Story:** As an administrator, I want a list of all users with their individual usage counts, so that I can see how much each user relies on the application.

#### Acceptance Criteria

1. WHEN an Administrator requests the user usage list, THE Admin_API SHALL return one User_Usage_Summary for each User_Account.
2. THE Admin_API SHALL include the `email` of the User_Account in each User_Usage_Summary.
3. THE Admin_API SHALL include the Telegram_Linked_State of the User_Account in each User_Usage_Summary.
4. THE Admin_API SHALL include the `created_at` registration timestamp of the User_Account in each User_Usage_Summary.
5. THE Admin_API SHALL include the count of that User_Account's activities in each User_Usage_Summary.
6. THE Admin_API SHALL include the count of that User_Account's goals in each User_Usage_Summary.
7. THE Admin_API SHALL include the count of that User_Account's reminders in each User_Usage_Summary.
8. THE Admin_API SHALL include the count of that User_Account's challenges in each User_Usage_Summary.
9. WHEN no User_Accounts exist other than the requesting Administrator, THE Admin_API SHALL return a list containing only the requesting Administrator's User_Usage_Summary.

### Requirement 4: Provide detail for a single user

**User Story:** As an administrator, I want to view extended usage detail for one selected user, so that I can understand that user's recent engagement.

#### Acceptance Criteria

1. WHEN an Administrator requests the User_Usage_Detail for an existing User_Account identifier, THE Admin_API SHALL return the User_Usage_Summary fields for that User_Account.
2. WHEN an Administrator requests the User_Usage_Detail for an existing User_Account identifier, THE Admin_API SHALL return the count of that User_Account's activities within the trailing 7-day window.
3. WHEN an Administrator requests the User_Usage_Detail for an existing User_Account identifier, THE Admin_API SHALL return the count of that User_Account's activities within the trailing 30-day window.
4. WHEN an Administrator requests the User_Usage_Detail for an existing User_Account that owns at least one activity, THE Admin_API SHALL return the `timestamp` of that User_Account's most recent activity.
5. WHERE the requested User_Account owns no activities, THE Admin_API SHALL return a null value for the most recent activity timestamp.
6. IF an Administrator requests the User_Usage_Detail for a User_Account identifier that does not exist, THEN THE Admin_API SHALL reject the request with HTTP status 404.

### Requirement 5: Protect user privacy in admin responses

**User Story:** As a user of the application, I want administrators to see only my usage data and not my secrets, so that my credentials and private identifiers stay protected.

#### Acceptance Criteria

1. THE Admin_API SHALL exclude the `password_hash` field from every response.
2. THE Admin_API SHALL exclude authentication tokens from every response.
3. WHERE a User_Account has a `telegram_chat_id`, THE Admin_API SHALL represent Telegram association as the Telegram_Linked_State boolean and SHALL exclude the raw `telegram_chat_id` value from every response.

### Requirement 6: Gate the Admin View in the frontend

**User Story:** As an administrator, I want the admin panel entry to appear only for administrators, so that non-administrators are not shown or able to open the panel.

#### Acceptance Criteria

1. WHILE the authenticated user's `is_admin` value is `true`, THE Admin_View SHALL display a navigation entry that opens the Admin_Panel.
2. WHILE the authenticated user's `is_admin` value is `false`, THE Admin_View SHALL hide the navigation entry that opens the Admin_Panel.
3. IF a Non_Administrator navigates directly to the Admin_Panel route, THEN THE Admin_View SHALL redirect the user away from the Admin_Panel to a non-admin route.
4. WHEN an Administrator opens the Admin_Panel, THE Admin_View SHALL render the System_Overview statistics and the per-user usage list.

### Requirement 7: Present admin data in the frontend

**User Story:** As an administrator, I want the panel to display the overview and per-user data clearly in Spanish, so that I can read usage information at a glance.

#### Acceptance Criteria

1. WHEN the Admin_View receives the System_Overview, THE Admin_View SHALL display each aggregate statistic with a Spanish-language label.
2. WHEN the Admin_View receives the user usage list, THE Admin_View SHALL display each User_Usage_Summary as a row showing email, Telegram_Linked_State, registration date, and the activity, goal, reminder, and challenge counts.
3. WHILE the Admin_API request is in progress, THE Admin_View SHALL display a loading indicator.
4. IF the Admin_API request fails, THEN THE Admin_View SHALL display a Spanish-language error message.
