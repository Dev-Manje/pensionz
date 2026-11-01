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

**Not yet:** OTP/MFA (FR-SEC-004, planned with
portal access in Phase 5), SMS channel.

## Phase 1 — Setup & reference data

### Fund setup (FR-CFG-001, FR-SEC-001, FR-SEC-005) — 2026-11-01

Migration `c47e2a91f0d3_funds_and_banks.py`.

- **Banks & branches** (`models/reference.py`: `bank`, `bank_branch`): the migration seeds 8 Malawi
  commercial banks, each with Blantyre/Lilongwe/Mzuzu/Zomba branches, as a starter list (no SWIFT or
  branch codes yet). `GET /api/v1/reference/banks` (any signed-in user) returns active banks + branches.
  Maintenance screen comes with FR-CFG-010.
- **Funds** (`models/fund.py`): `fund` (code ≤ 10 chars, unique case-insensitively; type standalone_dc /
  umbrella_dc / personal_pension / defined_benefit / minors_trust; status active /
  closed_to_new_members / wound_up; registration no., TPIN, financial-year-end month, address 1–5,
  phone, fax, email, website, contact person), `fund_trustee`, `fund_bank_account` (bank, optional
  branch, name, number, currency, purpose collections/payments/general). Removed trustees and bank
  accounts are set `active = false`, never deleted.
- **Maker-checker** (`services/funds.py`, approval kind `fund_setup`): `POST /funds` and
  `PUT /funds/{id}` (role `scheme_config_maker`) send the **whole fund** (details + trustees + bank
  accounts) as one snapshot → 202 with the approval request; a `scheme_config_checker` approves it.
  `previous` holds the current snapshot; the Approvals diff shows only changed fields, with one line per
  trustee/bank account. Checks: duplicate code against funds *and* pending new-fund requests (409),
  one pending change per fund (409), branch must belong to the bank, no duplicate account numbers,
  "Nothing has changed" (400). Code and fund type are locked once the fund has members
  (`fund_has_members` returns False until Phase 3 adds members).
- **Fund scoping** (`services/fund_access.py`, table `user_fund_access`): admins and auditors see every
  fund; other staff only those granted to them; anything else is 404. On approval of a new fund, both
  its maker and checker are granted it. Admins assign funds in Users (part of the `user_access`
  approval, shown by fund code). The approval engine is fund-scoped too: a request with a `fund_id`
  is visible to, notifies, and can be decided only by checkers who administer that fund.
- **Masking:** fund detail returns the full account number only to admin, scheme setup maker/checker,
  finance and finance checker; everyone gets `account_number_masked` ("•••• 4567").
- **Frontend:** sidebar "Funds" (all staff) → `/funds` list (search, status, "Change awaiting
  approval" chip), `/funds/<id>` (Details / Trustees / Bank accounts tabs, `?tab=`), `/funds/new` and
  `/funds/<id>/edit` (sectioned form with repeatable trustees and bank accounts → "Submit for
  approval"). Users screen: Funds column + fund picker for staff without all-fund access.
- **Seed:** UMB01 (umbrella DC), LSS01 (stand-alone DC), MTDB1 (DB), PPF01 (personal pension) —
  invented names, each with trustees and a collections account; every seeded fund-level staff user
  administers all four.
