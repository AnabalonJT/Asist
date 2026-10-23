# Implementation Plan: password-recovery-telegram

## Overview

Incremental implementation of Telegram-delivered password recovery. Work proceeds backend-first (model → migration → service logic → endpoints), then frontend (api client → login link → recovery page → route), with property-based and example tests placed close to the code they validate. Each step builds on the previous and ends wired into the running application.

Languages: Python (FastAPI backend) and TypeScript/React (frontend), per the design document. Property tests use Hypothesis (min 100 iterations each); frontend tests use component tests.

## Tasks

- [ ] 1. Create the PasswordResetToken model and register it
  - [ ] 1.1 Create `app/models/password_reset_token.py`
    - Define `PasswordResetToken(Base)` with `__tablename__ = "password_reset_tokens"` following the `LinkingToken` pattern
    - Columns: `id` (PK), `user_id` (FK → `users.id`, indexed), `code_hash` (`String(255)`, indexed — bcrypt hash of the 6-digit code), `used` (`Boolean`, default `False`, indexed), `created_at` (default `func.now()`), `expires_at` (`DateTime`)
    - Add `user: Mapped["User"] = relationship(back_populates="password_reset_tokens")`
    - _Requirements: 1.2_

  - [ ] 1.2 Add the `password_reset_tokens` relationship to the User model
    - In `app/models/user.py`, add `password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")` mirroring `linking_tokens`
    - _Requirements: 1.2_

  - [ ] 1.3 Register the model for metadata and startup table creation
    - Add `from app.models.password_reset_token import PasswordResetToken` and `"PasswordResetToken"` to `__all__` in `app/models/__init__.py`
    - Add `password_reset_token` to the model import list inside `init_db()` in `app/database.py` so `Base.metadata.create_all` registers the table (runtime safety net)
    - _Requirements: 1.2_

- [ ] 2. Add the Alembic migration for the new table
  - [ ] 2.1 Create an Alembic revision that creates `password_reset_tokens`
    - Add a new revision file under `alembic/versions/` following the existing revision format (`revision`, `down_revision` pointing at the latest revision)
    - `upgrade()` creates the `password_reset_tokens` table with columns `id`, `user_id`, `code_hash`, `used`, `created_at` (server_default `now()`), `expires_at`, a FK constraint to `users.id`, and indexes on `user_id`, `code_hash`, and `used`
    - `downgrade()` drops the indexes and the table
    - Note: `create_all` in `init_db()` also creates this table as a runtime safety net
    - _Requirements: 1.2_

- [ ] 3. Extend AuthService with recovery logic
  - [ ] 3.1 Add recovery constants and the Telegram send helpers to `app/services/auth_service.py`
    - Add module/service constants: `RESET_CODE_EXPIRY_MINUTES = 15`, `MIN_PASSWORD_LENGTH = 6`, `MAX_PASSWORD_LENGTH = 128`, `RESET_RATE_LIMIT_WINDOW_MINUTES = 15`, `RESET_MAX_REQUESTS_PER_WINDOW = 3`
    - Add pure function `build_recovery_message(code: str) -> str` returning a Spanish message that contains the code and its validity in minutes
    - Add async `send_recovery_code(chat_id: int, code: str) -> None` doing an `httpx` POST to the Bot API `sendMessage` (mirroring `_send` in `telegram.py`), wrapped in `try/except` that logs a warning and swallows failures
    - _Requirements: 6.1, 6.2_

  - [ ]* 3.2 Write property test for the recovery message
    - **Property 12: Recovery message contains the code and validity minutes**
    - **Validates: Requirements 6.1**
    - Tag: `# Feature: password-recovery-telegram, Property 12: ...`; generate 6-digit codes, assert the message contains the code and the minutes

  - [ ] 3.3 Implement `create_password_reset_token`
    - `async def create_password_reset_token(self, db, user) -> str`
    - Mark all of the user's prior tokens with `used == False AND expires_at >= utcnow()` as `used = True` before inserting the new one
    - Generate a 6-digit code with `f"{secrets.randbelow(1_000_000):06d}"`, persist `PasswordResetToken` with `code_hash = self.hash_password(code)`, `used = False`, `expires_at = utcnow() + RESET_CODE_EXPIRY_MINUTES`
    - Return the plaintext code (used once to send via Telegram)
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3_

  - [ ]* 3.4 Write property test for generated code format, expiry, and persisted fields
    - **Property 1: Generated code format, expiry, and persisted fields**
    - **Validates: Requirements 1.1, 1.2**
    - Tag comment referencing the property; assert code matches `^\d{6}$`, and persisted token has matching `user_id`, `used == False`, `expires_at == created_at + 15 min`

  - [ ]* 3.5 Write property test for prior-token invalidation
    - **Property 2: Only the most recent token is valid**
    - **Validates: Requirements 2.1, 2.2, 2.3**
    - Generate a user and `k >= 1` sequential `create_password_reset_token` calls; assert exactly one non-used non-expired token (the most recent) remains and all previous are `used == True`

  - [ ] 3.6 Implement `validate_and_consume_reset`
    - `async def validate_and_consume_reset(self, db, email, code, new_password) -> None`
    - Resolve user by email; if no user (or no candidate tokens), run a dummy `verify_password` against a constant bcrypt hash (anti-timing) then raise `AuthError("invalid")`
    - Load the user's candidate tokens ordered by `created_at DESC, id DESC`; find the token whose `code_hash` verifies against `code`
    - Apply deterministic rejection precedence, stopping at the first that applies: (1) no match → `AuthError("invalid")`, (2) matched token used → `AuthError("invalid")`, (3) matched token expired → `AuthError("invalid")`, (4) `new_password` length outside `[6, 128]` → `AuthError("length")`
    - On the length rule, do NOT mark the token used and do NOT change the password
    - On success, set `user.password_hash = self.hash_password(new_password)` and mark the matched token `used = True`
    - _Requirements: 3.1, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.2_

  - [ ]* 3.7 Write property test for single-use token consumption
    - **Property 5: Single-use token consumption**
    - **Validates: Requirements 3.3**
    - Perform a valid reset; assert token `used == True` and a second reset with the same code is rejected

  - [ ]* 3.8 Write property test for expired-token rejection
    - **Property 6: Expired tokens are rejected without changing the password**
    - **Validates: Requirements 3.7**
    - Generate tokens with past `expires_at`; assert rejection and unchanged `password_hash`

  - [ ]* 3.9 Write property test for out-of-range password length
    - **Property 7: Out-of-range password length is rejected without consuming the token**
    - **Validates: Requirements 3.8**
    - Generate passwords of length `< 6` or `> 128`; assert rejection, token remains `used == False`, `password_hash` unchanged

  - [ ]* 3.10 Write property test for hashing correctness after reset
    - **Property 8: Hashing correctness after reset**
    - **Validates: Requirements 3.1, 3.9**
    - Generate distinct old/new password pairs; after a successful reset assert `verify_password(new_password, hash)` is `True` and `verify_password(old_password, hash)` is `False`

  - [ ]* 3.11 Write property test for deterministic rejection precedence
    - **Property 9: Deterministic rejection precedence**
    - **Validates: Requirements 3.4**
    - Generate combined failing states (match/used/expired/length); assert the reported rejection matches the first failing condition in fixed order

  - [ ] 3.12 Implement `is_rate_limited`
    - `async def is_rate_limited(self, db, user) -> bool`
    - Return `True` when the user has `>= RESET_MAX_REQUESTS_PER_WINDOW` reset tokens with `created_at` within the last `RESET_RATE_LIMIT_WINDOW_MINUTES`; return `False` when `user is None`
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 4. Add the recovery endpoints to `app/routes/auth.py`
  - [ ] 4.1 Add request/response schemas and the `POST /forgot-password` endpoint
    - Add `ForgotPasswordRequest(email: EmailStr)`, `ResetPasswordRequest(email: EmailStr, code: str, new_password: str)`, and `GenericResponse(message: str)`
    - `POST /forgot-password` (`response_model=GenericResponse`): resolve user by email (may be `None`); if `is_rate_limited` → raise `429` with Spanish message; if the user is a `Linked_User` (`telegram_chat_id` not null) create a token via `create_password_reset_token` and call `send_recovery_code`; otherwise do nothing; always return the identical `GenericResponse` with `200`
    - Invalid email format yields `422` automatically via `EmailStr` (no manual handling)
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7, 4.1, 5.1, 5.2, 6.3_

  - [ ]* 4.2 Write property test for identical generic forgot-password response
    - **Property 3: Identical generic response for all forgot-password categories**
    - **Validates: Requirements 1.3, 4.1**
    - Generate emails across linked/unlinked/nonexistent categories (Telegram send mocked); assert identical response body and HTTP status

  - [ ]* 4.3 Write property test for no side effects on nonexistent/unlinked emails
    - **Property 4: No side effects for nonexistent or unlinked emails**
    - **Validates: Requirements 1.4, 1.5, 6.3**
    - Generate nonexistent/unlinked emails; assert zero token rows created and the Telegram send mock is not called

  - [ ]* 4.4 Write property test for rate limiting and window reset
    - **Property 11: Rate limiting after three requests with no side effects, then window reset**
    - **Validates: Requirements 5.1, 5.2, 5.3**
    - Drive requests with a controlled clock / `created_at`; assert `200` for the first 3, `429` afterwards with no token created and no Telegram send, and acceptance again after the window elapses

  - [ ] 4.5 Add the `POST /reset-password` endpoint
    - `POST /reset-password` (`response_model=GenericResponse`): call `auth_service.validate_and_consume_reset(db, email, code, new_password)`; on success return `200` with `"Contraseña actualizada correctamente."`
    - Map `AuthError`: category `"length"` → `400` `"La contraseña debe tener entre 6 y 128 caracteres."`; otherwise → `400` `"Código inválido o expirado."`
    - _Requirements: 3.2, 3.5, 3.6, 3.7, 3.8, 4.2_

  - [ ]* 4.6 Write property test for identical generic error on enumeration-sensitive reset rejections
    - **Property 10: Identical generic error for enumeration-sensitive reset rejections**
    - **Validates: Requirements 4.2**
    - Generate the four enumeration-sensitive rejection categories (no user, no match, used, expired); assert identical error body and HTTP status

  - [ ]* 4.7 Write example tests for Telegram failure, invalid email, and reset success
    - Telegram send fails → `forgot-password` still returns identical `200` and the token row remains (Req 1.6, 6.2)
    - Malformed email → `422`, no token created, no Telegram send (Req 1.7)
    - Happy-path reset → `200` with the Spanish success message (Req 3.2)
    - _Requirements: 1.6, 1.7, 3.2, 6.2_

- [ ] 5. Checkpoint - backend
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Extend the frontend API client
  - [ ] 6.1 Add `forgotPassword` and `resetPassword` to `authApi` in `src/lib/api.ts`
    - Add `GenericMessageResponse { message: string }`
    - `forgotPassword(email)` → `POST /auth/forgot-password` with `{ email }`
    - `resetPassword(email, code, new_password)` → `POST /auth/reset-password` with `{ email, code, new_password }`
    - _Requirements: 7.3, 7.5_

- [ ] 7. Add the recovery link to the login screen
  - [ ] 7.1 Add the "¿Olvidaste tu contraseña?" link in `src/pages/LoginPage.tsx`
    - Add a `<Link to="/forgot-password">` with the exact text `¿Olvidaste tu contraseña?` near the "¿No tienes cuenta?" line
    - _Requirements: 7.1_

- [ ] 8. Build the two-step recovery page
  - [ ] 8.1 Create `src/pages/ForgotPasswordPage.tsx`
    - Manage `step` (`'request' | 'reset'`), `email`, `code`, `newPassword`, `error`, `success`, `loading` state
    - Step 1 (request): email input + submit; on submit set `loading`, disable the button, call `authApi.forgotPassword(email)`; on `200` advance to step 2
    - Step 2 (reset): code + new-password inputs + submit; on submit set `loading`, disable the button, call `authApi.resetPassword(email, code, newPassword)`; on `200` show a Spanish success message and `navigate('/login')` within ≤5s (e.g. `setTimeout(..., <=5000)`)
    - Error handling: on any error status show `err.response?.data?.detail ?? <fallback en español>`, stay on the current step, preserve entered fields except clear the password field
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ]* 8.2 Write component tests for the recovery flow
    - Step-1 form shown at `/forgot-password` (7.2); loading disables the submit button while pending (7.3, 7.5); step 2 shown after `200` from `forgotPassword` (7.4); success message + navigation to `/login` within 5s after `200` from `resetPassword` (7.6); backend Spanish error shown with step and fields preserved and password cleared on error (7.7); login link present (7.1)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [ ] 9. Wire the public route
  - [ ] 9.1 Add the `/forgot-password` public route in `src/main.tsx`
    - Add `<Route path="/forgot-password" element={<ForgotPasswordPage />} />` outside the `ProtectedRoute` block, alongside `/login` and `/register`
    - _Requirements: 7.2_

- [ ] 10. Final checkpoint - all tests
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (tests) and can be skipped for a faster MVP.
- Each task references specific requirement sub-clauses for traceability.
- Property tests validate the universal correctness properties from the design (each tagged `# Feature: password-recovery-telegram, Property N: ...`, min 100 iterations, Telegram Bot API mocked, test DB session).
- Unit/example tests cover Telegram failure, invalid-email `422`, and the reset success message.
- `auth.py` (backend) and `api.ts` (frontend) each contain multiple sub-tasks; they are scheduled in separate waves to avoid same-file conflicts.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1", "6.1", "7.1", "9.1"] },
    { "id": 3, "tasks": ["3.1", "8.1"] },
    { "id": 4, "tasks": ["3.3", "3.2", "8.2"] },
    { "id": 5, "tasks": ["3.6", "3.4", "3.5"] },
    { "id": 6, "tasks": ["3.12", "3.7", "3.8", "3.9", "3.10", "3.11"] },
    { "id": 7, "tasks": ["4.1"] },
    { "id": 8, "tasks": ["4.5", "4.2", "4.3", "4.4"] },
    { "id": 9, "tasks": ["4.6", "4.7"] }
  ]
}
```
