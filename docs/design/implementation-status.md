# Implementation status (as built)

Update this whenever behaviour changes (pz-task step 7).

## Phase 0 — Foundation

**Stack.** `docker-compose.yml`: db (Postgres 15, host :5433), minio (:9002/:9003), mailpit
(:8026), backend (FastAPI, :8002), worker (same image, `python -m app.worker`), frontend (Vite,
:5178). `start-servers.bat` / `stop-servers.bat`.
**Local dev (2026-11-01): runs on the host** — only db/minio/mailpit in Docker. Backend:
`backend/.venv` (`pip install -r requirements-dev.txt`), `backend/.env` points at localhost:5433 /
:9002 / Mailpit SMTP :1026; run `alembic upgrade head`, `uvicorn app.main:app --port 8002 --reload`,
`python -m app.worker`, `pytest -q` from `backend/`. Frontend: `frontend/.env` (`VITE_API_BASE_URL`),
`npm run dev -- --port 5178`. `tests/conftest.py` derives `pensionz_test` from the resolved settings.
Initial migration: `alembic/versions/b1e58cad77d5_initial.py`.

**Branding.** Independent product "Pensionz": `frontend/src/brand.ts` (name, administrator
wording, colours → `theme.ts`) and `BRAND_*` settings in `backend/app/core/config.py` (emails).

**Backend.**
- Enums are stored as VARCHAR (`models/mixins.str_enum`) — adding a value needs no migration.
- Identity: `User` (multi-role via `UserRoleAssignment`), 20 roles (`models/identity.UserRole`),
  `STAFF_ROLES` / `PORTAL_ROLES`. JWT access/refresh; tokens issued before
  `password_changed_at` are refused. Lockout after `max_failed_logins` (5) for `lockout_minutes`
  (15). No self-registration; invitations by email (7-day single-use link).
- Audit: `audit_event` (actor, entity, action, before/after JSON, IP, fund_id) via
  `services/audit.record` — sign-in, lockout, password events, user changes, approvals.
- Maker-checker engine: `approval_request` + `services/approvals.py` (register an
  `ApprovalKind` with checker roles and an `apply` function; `submit` → checkers notified;
  approve/reject/cancel with row lock, initiator ≠ checker, 409 when already decided, reject needs
  a reason). Generic API `/api/v1/approvals`. First kind: `user_access` (create user, change
  name/phone/roles/status — checker: another admin).
- Notifications: `user_notification` (bell) + `notification_outbox` (email) written in the same
  commit; worker delivers every 5s with SKIP LOCKED and retries 1m/5m/30m/2h. API
  `/api/v1/me/notifications` (paged), `/unread-count`, `/{id}/read`, `/read-all`.
- Worker + `job_run` runner (one success per job per business date); first job
  `purge_expired_links`.
- Seed: `python -m app.seed` → one user per role (`TEST_USERS.md`); seeded users have
  `password_changed_at` set, so they show as Active rather than "Invitation sent".

**Frontend.** React 18 + TS + Vite + MUI, react-query. Login / forgot / reset password,
`RoleRouter` (sections: My pension `/member`, My schemes `/po`, Home, Approvals, Users),
notifications bell + page, change password, Users admin (propose create/change, send
invitation/reset link), Approvals queue (to review / my requests / history, diff view,
approve/reject/withdraw, deep link `/approvals/<id>`).

**Not yet:** fund-scoped staff access (needs funds — Phase 1), OTP/MFA (FR-SEC-004, planned with
portal access in Phase 5), SMS channel.
