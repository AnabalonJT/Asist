# Implementation Plan: Admin Panel

## Overview

This plan builds the Admin Panel incrementally, backend first, then tests, then the frontend, and finishes with a verification pass. The backend introduces a single new router (`app/routes/admin.py`) with three read-only aggregate endpoints protected by the existing `get_current_admin` dependency, wired into `app/main.py`. Property-based tests (Hypothesis) cover the aggregation and privacy logic (Properties 1-9); example/integration pytest cover the fixed auth matrix and edge cases. The frontend adds typed API models, an admin route guard, the admin page (Spanish UI), the route wiring, and the conditional Navbar tab. No new tables or columns are added — the feature reads existing ORM models only.

Each task builds on the previous ones and ends by wiring the new code into the running app, so there is no orphaned code.

## Tasks

- [x] 1. Create the backend admin router with Pydantic models and the three endpoints
  - [x] 1.1 Create `app/routes/admin.py` with response models and the overview endpoint
    - Create the file mirroring the thin-controller style of `app/routes/dashboard.py`: `APIRouter()`, `BaseModel` response models, async `select`/`func.count` queries, `Depends(get_db)`.
    - Define `AdminOverview`, `AdminUserSummary`, and `AdminUserDetail(AdminUserSummary)` exactly as in the design's Data Models section (no `password_hash`, token, or `telegram_chat_id` fields — privacy by construction).
    - Implement `GET /overview` returning `AdminOverview`, depending on `get_current_admin` from `app.middleware.middleware`. Compute `total_users`, `telegram_linked_users` (`User.telegram_chat_id.is_not(None)`), the four entity totals via `select(func.count()).select_from(<Entity>)`, and `active_users_7d`/`active_users_30d` via `select(func.count(func.distinct(Activity.user_id))).where(Activity.timestamp >= utcnow() - timedelta(days=N))`.
    - Import ORM models `User`, `Activity`, `Goal`, `Reminder`, `Challenge`.
    - _Requirements: 1.1, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 5.1, 5.2, 5.3_

  - [x] 1.2 Implement the per-user list endpoint (`GET /users`) with the no-N+1 grouped-count approach
    - Load all users once, then build one grouped-count map per entity: `select(model.user_id, func.count()).group_by(model.user_id)` for `Activity`, `Goal`, `Reminder`, `Challenge`.
    - Merge in Python into one `AdminUserSummary` per user, defaulting missing counts to `0` via `.get(u.id, 0)`; set `telegram_linked = u.telegram_chat_id is not None` and `created_at = u.created_at.isoformat() if u.created_at else ""`.
    - Return `list[AdminUserSummary]` (fixed number of queries regardless of user count).
    - _Requirements: 1.1, 1.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 5.1, 5.2, 5.3_

  - [x] 1.3 Implement the single-user detail endpoint (`GET /users/{user_id}`)
    - Load the user by id; if `None`, raise `HTTPException(status_code=404, detail="User not found")`.
    - Compute the shared summary counts (scoped `func.count()` `where(<Entity>.user_id == user_id)`), `activities_7d`/`activities_30d` (`Activity.user_id == user_id` and `timestamp >= cutoff`), and `last_activity_at = select(func.max(Activity.timestamp)).where(Activity.user_id == user_id)` (serializes to `null` when the user has no activities).
    - Return `AdminUserDetail`.
    - _Requirements: 1.1, 1.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3_

  - [x] 1.4 Register the admin router in `app/main.py`
    - Add `admin` to the plain route import line (`from app.routes import auth, telegram, dashboard, activities, reminders, goals, challenges, admin`), keeping `from app.routes import settings as settings_routes` unchanged (do NOT reintroduce a bare `settings` import that would shadow `app.config.settings`).
    - Add `app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])` alongside the other `include_router` calls.
    - _Requirements: 1.4_

- [x] 2. Checkpoint - backend endpoints wired
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Backend property-based tests (Hypothesis) for the aggregation and privacy logic
  - Tests live in `tests/` per `pytest.ini`. Configure each property test with `@settings(max_examples=100)` (or more). If DB seeding cost is prohibitive, mock the session layer so the pure aggregation/merge logic still runs 100+ examples. Tag each test with a comment `# Feature: admin-panel, Property N: <title>`. Generators produce users with random `email`, random `telegram_chat_id` present/absent, and `created_at`; activities with `timestamp` values spread around the 7-day and 30-day cutoffs; and random per-user goal/reminder/challenge rows.
  - [ ]* 3.1 Write property test for overview totals
    - **Property 1: Overview totals equal row counts**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

  - [ ]* 3.2 Write property test for active-user window counts
    - **Property 2: Active-user window counts are correct**
    - **Validates: Requirements 2.7, 2.8**

  - [ ]* 3.3 Write property test for the user-list bijection
    - **Property 3: The user list is a bijection over users**
    - **Validates: Requirements 3.1, 3.9**

  - [ ]* 3.4 Write property test for per-user summary field passthrough/derivation
    - **Property 4: Per-user summary fields match their source**
    - **Validates: Requirements 3.2, 3.3, 3.4**

  - [ ]* 3.5 Write property test for per-user entity counts (incl. zero default)
    - **Property 5: Per-user entity counts equal that user's rows**
    - **Validates: Requirements 3.5, 3.6, 3.7, 3.8**

  - [ ]* 3.6 Write property test for detail/list summary consistency
    - **Property 6: Detail summary is consistent with the list summary**
    - **Validates: Requirements 4.1**

  - [ ]* 3.7 Write property test for detail windowed activity counts
    - **Property 7: Detail windowed activity counts are correct**
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 3.8 Write property test for last-activity max/null
    - **Property 8: Last activity timestamp is the max, or null when none**
    - **Validates: Requirements 4.4, 4.5**

  - [ ]* 3.9 Write property test asserting no secret fields in any admin response
    - **Property 9: No secret fields appear in any admin response** (assert no `password_hash`, token, or raw `telegram_chat_id` key at any level of the serialized JSON for `overview`, `users`, `users/{id}`)
    - **Validates: Requirements 5.1, 5.2, 5.3**

- [ ] 4. Backend example / integration tests (pytest)
  - [ ]* 4.1 Write the auth matrix integration tests across all three endpoints
    - Parameterize over `/api/admin/overview`, `/api/admin/users`, `/api/admin/users/{id}`: admin JWT -> `200`, non-admin JWT -> `403`, no token and garbage token -> `401`.
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 4.2 Write the single-user, 404, and null-last-activity example tests
    - Single-user scenario: seed only the admin, assert `/users` returns exactly one summary with correct counts (Req 3.9).
    - 404: request `/users/{id}` for a non-existent id, assert `404` (Req 4.6).
    - Null last activity: seed a user with no activities, assert `last_activity_at is None` (Req 4.5).
    - _Requirements: 3.9, 4.5, 4.6_

- [x] 5. Checkpoint - backend fully tested
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Frontend types and API module
  - [x] 6.1 Add admin interfaces and `adminApi` module to `src/lib/api.ts`
    - Add `AdminOverview`, `AdminUserSummary`, and `AdminUserDetail extends AdminUserSummary` interfaces matching the backend models.
    - Add the `adminApi` module: `overview()` -> `GET /admin/overview`, `users()` -> `GET /admin/users`, `userDetail(id)` -> `GET /admin/users/${id}`, following the existing typed-module pattern (reuses the shared `api` axios instance and interceptors).
    - _Requirements: 6.4, 7.1, 7.2_

- [x] 7. Frontend admin gating and page
  - [x] 7.1 Create the `AdminRoute` guard component
    - Create `src/components/AdminRoute.tsx` mirroring `ProtectedRoute.tsx`: read `{ user, loading }` from `useAuth`; while loading render the shared spinner (`border-2 border-accent border-t-transparent animate-spin`); if no user redirect to `/login`; if `user.is_admin` render children else `<Navigate to="/dashboard" replace />`.
    - _Requirements: 6.3_

  - [x] 7.2 Create the `AdminPage` with Spanish overview cards and per-user table
    - Create `src/pages/AdminPage.tsx`. On mount, `Promise.all([adminApi.overview(), adminApi.users()])` inside a `useEffect`.
    - Loading: render the shared spinner while requests are in flight (Req 7.3).
    - Error: on rejection, render a Spanish error message, e.g. "No se pudieron cargar los datos de administración." (Req 7.4).
    - Overview: grid of `.card` stat cards with Spanish labels (Usuarios totales, Con Telegram, Actividades, Metas, Recordatorios, Retos, Activos (7 días), Activos (30 días)) (Req 7.1).
    - User list: a table/list of rows showing email, Telegram linked state (✓ Conectado / No conectado, matching `SettingsPage`), formatted registration date, and the four counts (Req 7.2).
    - _Requirements: 6.4, 7.1, 7.2, 7.3, 7.4_

  - [ ]* 7.3 Add optional per-user detail drill-down UI to `AdminPage`
    - Optional nice-to-have: on selecting a user row, call `adminApi.userDetail(id)` and render `activities_7d`, `activities_30d`, and `last_activity_at` (showing a placeholder when `null`).
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 8. Frontend routing and navigation wiring
  - [x] 8.1 Wire the `/admin` route into the protected block in `src/main.tsx`
    - Import `AdminPage` and `AdminRoute`; inside the existing `<Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>` block add `<Route path="/admin" element={<AdminRoute><AdminPage /></AdminRoute>} />`.
    - _Requirements: 6.3, 6.4_

  - [x] 8.2 Add the conditional Admin tab to `src/components/Navbar.tsx`
    - Read `user` from `useAuth` and append `{ to: '/admin', icon: '🛡️', label: 'Admin' }` to `links` only when `user?.is_admin` is true.
    - _Requirements: 6.1, 6.2_

- [x] 9. Final verification
  - [x] 9.1 Run backend tests and frontend build
    - Run `pytest tests/` and confirm the admin property, integration, and example tests pass.
    - Run `cd src && npm run build` and confirm the frontend compiles with no type errors.
    - Fix any failures surfaced by either step.
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1_

## Notes

- Tasks marked with `*` are optional (test sub-tasks and the detail drill-down UI in 7.3) and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references specific requirement clauses (and property numbers for PBT tasks) for traceability.
- Checkpoints (tasks 2 and 5) ensure incremental validation between phases.
- Property tests validate the universal backend correctness properties (1-9); example/integration tests cover fixed auth outcomes and edge cases; frontend concerns are validated via the build/type-check and manual review.
- The backend router is wired into `app/main.py` in task 1.4 so no code is left orphaned; the frontend is wired into routing and navigation in task 8.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "6.1"] },
    { "id": 3, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9", "4.1", "4.2", "7.1", "8.2"] },
    { "id": 4, "tasks": ["7.2"] },
    { "id": 5, "tasks": ["7.3", "8.1"] },
    { "id": 6, "tasks": ["9.1"] }
  ]
}
```
