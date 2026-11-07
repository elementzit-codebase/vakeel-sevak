# Architecture (foundation)

- `apps/api`: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL. Settings come from environment (`.env`).
  `PRODUCT_NAME` is the one place the product name is set; web and mobile read it from `GET /api/config`.
- `apps/web`: React, Vite, TypeScript. `apps/mobile`: React Native (Expo), TypeScript.
- `packages/tokens`: one `tokens.json`; `node packages/tokens/sync.mjs` writes CSS variables and a TS module
  into both apps. Edit tokens only there.
- Components (Button, Input, StatusTag, AIDraft, Card, TabBar, DataTable) exist on web and mobile with the same
  names and props, matching the Design System. Rules built into them: status is icon plus word, AI output shows
  an AI badge and a dashed Draft tag until approved, touch targets are at least 44 px.
- Languages: English and Malayalam. Add one by adding a file in `src/i18n` and its code to `LANGUAGES`.
  Malayalam strings in the foundation are starters and need a native reader's review.
- Roles: director, advocate, junior, clerk, accountant, helper, client (read-only). Enforced from Feature 1.
- Tables so far: offices, users, clients, cases, hearings, tasks. Sample data lives in `app/sample_data.py`
  (fictional) and loads with `make seed`.
- AI runs in the backend. Where the model is hosted is still open (SRS O-7), so Feature 7 and later put the
  model behind one interface in the API.

## Sign-in, roles and audit (Feature 1)

- **Sign-in:** email and password for every role, including the read-only Client. Passwords are Argon2 hashed.
  Five wrong tries lock the account for 15 minutes. Errors never say whether the email exists.
- **Sessions:** each sign-in creates a row in `auth_sessions`; the token only points to it. Every request checks the
  session, the user's active flag and idle time, so deactivating a user ends their access at once (AUT-02).
  Web idle limit is 30 minutes (`WEB_IDLE_MINUTES`); mobile sessions last up to 30 days and are protected by
  biometric or PIN unlock on the device (AUT-05). The web app also signs out by itself when idle.
- **Two-factor (TOTP):** off for everyone until a Director chooses roles under Team and access, Security
  (`PUT /api/settings/security/mfa-roles`). A user in a chosen role who has not enrolled gets a limited session
  that can only set up two-factor. Mobile asks the user to finish set-up on web.
- **Permissions:** `app/permissions.py` maps each role to permissions; `require()` and `require_any()` enforce
  them on the server (403). `visible_cases_query()` is the one rule for which cases a user may see: the Director
  sees all, assigned staff see their cases, and an unassigned case answers 404 and is left out of counts (AUT-04).
  The Client role uses `/api/portal/cases` (own cases, next date, no notes).
- **Audit log:** `audit_log` is append-only. The application refuses updates and deletes, and migration 0002 adds
  a PostgreSQL trigger that does the same in the database. Entries carry action, user, case and IP, never case
  content. Director-only viewing and filtering: `GET /api/audit`.
- **Password reset:** single-use link, 30 minutes, ends all sessions. Email sending is a stub that logs the link
  (`app/services/mailer.py`) until a mail provider is chosen.
- **Sample logins:** every sample user has the password `ChangeMe#2026` (development only), for example
  `menon@example.in` (Director), `iyer@example.in` (Advocate), `meera@example.in` (Junior),
  `suresh@example.in` (Clerk), `anita@example.in` (Accountant), `ramesh@example.in` (Helper) and
  `a.sharma@example.in` (Client).
- **Production:** with `APP_ENV=production` the API refuses to start unless `SECRET_KEY` is set to 32 or more
  characters.

## Providers

AI, speech, OCR, email, push and file storage each sit behind a small interface in `apps/api/app/services/`.
The default for every one is a fake that needs no keys, so the whole app runs and the tests pass offline.
Set the provider names and keys in `.env` (see `.env.example`) to go live. Switching AI vendor means writing one class in `ai.py`.

AI output is never final. Document summaries, hearing records, consultations, client messages and day summaries are stored as
drafts; a person with the right permission approves them. For hearing records the AI draft is kept unchanged beside the approved version.

## Client communication

Off for everyone until a Director turns it on (Team and access, Firm settings). While off, nothing reaches a client: no
reminder email, message, status link or chat. Sending a message needs approval by a Director or Advocate.
