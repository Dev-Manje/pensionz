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

### Processing month per fund (FR-CFG-002) — 2026-11-01

Migration `d81f6b2c9a40_fund_periods.py`: `fund_period` (fund, first-of-month `period`, open/closed,
who/when opened and closed); a partial unique index allows **one open month per fund**.
`services/periods.py`:
- `require_open(db, fund_id, date)` — the guard every posting must call (409 when the date isn't in
  the open month or no month is open). `has_postings` returns False until the ledger exists (Phase 4).
- Finance opens the first month (`POST /funds/{id}/periods/open`), then closes months one at a time
  (`POST .../close` with the month on screen; stale → 409). Close runs `checklist()` — five month-end
  checks, all `not_available` until their areas are built; any `failed` check blocks the close — then
  opens the next month.
- Re-open: `POST .../{period_id}/reopen` with a reason → approval kind `period_reopen` (finance checker,
  fund-scoped). Only the latest closed month; on approval the auto-opened following month is removed
  (audited) unless it has postings (409).
- `GET /funds/{id}/periods` returns the open month, checklist, history and what the viewer may do;
  fund list/detail carry `current_period`.
Frontend: fund page tab "Processing months" (open-first form, open month card with checks and
"Close <month>" confirmation, history with "Request re-open"); funds list "Processing month" column.
Seed: Nov 2026 open for UMB01, LSS01, MTDB1; PPF01 left unopened.

### Participating employers / schemes (FR-CFG-003) — 2026-11-01

Migration `e5a3c7d10b62_schemes.py`: `scheme` (fund, code unique per fund, name, status active /
suspended / exited, registration no., TPIN, join/exit dates, `contribution_day` 1–28 = due by that day
of the month after the contributions month, billing frequency monthly/quarterly/annually, address,
contact) and `scheme_officer` (scheme ↔ principal-officer user, many-to-many).
`services/schemes.py`: approval kind `scheme_setup` (scheme setup checker, fund-scoped) applies the whole
snapshot — details plus `principal_officers` (only active users holding the principal officer role).
New employers only in **active** funds; exited needs an exit date. API: `GET/POST /funds/{id}/schemes`,
`GET/PUT /schemes/{id}`, `GET /schemes/officer-candidates` (scheme setup roles + admin).
Frontend: fund page tab "Employers", `/funds/<id>/employers/<schemeId>` (Details / Principal officers),
sectioned create/edit form with an officer picker. Shared form/detail building blocks now live in
`components/form/FormLayout.tsx` and `components/DetailSection.tsx`. Fund tabs scroll only on narrow
screens. Seed: CTE01 + NBL01 (UMB01), LSC01 (LSS01), MET01 (MTDB1); po@pensionz.dev linked to CTE01 and LSC01.

### Regulatory parameters & tax tables (FR-CFG-009) — 2026-11-01

Migration `f2b8d4e61c07_regulatory.py`: `regulatory_parameter_version` (key, value, effective_from,
source; unique per key+date), `tax_table` (kind paye_monthly / lump_sum, effective_from, source) with
`tax_band` (lower bound + rate; the next band's lower bound is the upper). **No figures in migrations.**
- `services/regulatory.py` lists the ten known parameters (label, unit, allowed range, help, group):
  minimum EE/ER contribution %, late-payment interest %, earliest/latest retirement age, maximum lump
  sum %, small-balance threshold, unemployment access wait (months), pre-retirement access window
  (years) and limit %. A change is a new version from a date → approval kind `regulatory_parameter`
  (scheme setup maker → checker); same key+date twice → 409; whole units for ages/months/years;
  back-dated versions are marked in the summary. New tax table versions → kind `tax_table` (bands
  must start at 0, ascend, rates 0–100%).
- `services/config_resolver.py` — the single resolver: `regulatory(db, key, as_of)`,
  `tax_table(db, kind, as_of)`, `tax_on(table, amount)` (progressive, half-up per band).
- API: `GET /regulatory/parameters`, `POST /regulatory/parameters/{key}/versions`,
  `GET|POST /regulatory/tax-tables/{kind}`, `GET /regulatory/tax-tables/{kind}/calculate?amount=&as_of=`.
- Frontend: sidebar "Regulatory" (all staff) with Parameters (grouped, in force / scheduled / history,
  change dialog with back-dating warning) and Tax tables (bands, calculator, new-version band editor).
  Payload keys starting with `_` are hidden from the approval diff. Tabs no longer show scroll arrows
  (theme default `scrollButtons: false`).
- Dev seed: working defaults from 1 Jan 2023 and a PAYE table from 1 Apr 2024, both marked "to confirm".

### Investment options (FR-CFG-007) — 2026-11-01

Migration `a93e1f5b7c28`: `investment_option` (fund, code unique per fund, name, pricing method
declared_rate / unit_price, status active / closed, launch date, description). Built on
**`services/config_changes.FundConfig`** — the shared maker-checker for simple per-fund records (snapshot
of declared fields, code unique per fund incl. pending requests, fund-scoped scheme-setup checker,
audit). Rules: new options start active; pricing method can't change after creation; DB funds have
none. API `GET|POST /funds/{id}/investment-options`, `PUT …/{option_id}`. Frontend: fund tab
"Investment options" (table + create/change dialog). Seed: GEN + MMK (UMB01), GEN (LSS01, PPF01).

### Benefit categories (FR-CFG-004) — 2026-11-01

Migration `b6d2e8f40a19`: `benefit_category` (scheme, fund copy for scoping, code unique per scheme,
name, status active/closed) and `benefit_category_terms` (versions from `effective_from`: design dc/db,
EE/ER rate type percent|fixed + rate, salary basis, NRA, entry ages, waiting months, vesting scale JSON,
default investment option, member choice, AVC allowed, group life multiple, DB accrual denominator and
final-salary months). `services/categories.py`, approval kind `benefit_category`:
- create = category + first terms; change = rename/close and/or new terms **after** the latest terms;
- terms validated on their effective date: % rates ≥ regulatory minimums (fixed MWK rates not compared),
  NRA within the retirement band; DC → employer rate + active default option of the same fund, no DB
  fields; DB → accrual + averaging, employer rate = balance of cost, no options;
- payload shows readable lines (rates, vesting, cover) with raw terms under `_terms`;
- `config_resolver.category_terms(db, category_id, as_of)`;
- proposing a higher regulatory minimum adds `categories_below_new_minimum` for the checker.
API: `GET|POST /schemes/{id}/categories`, `GET|PUT /categories/{id}`. Frontend: employer tab "Benefit
categories", category page (terms in force, scheduled, history) and create/change form with terms editor
(vesting steps, DB formula section for DB funds). Seed: MGT/STF (CTE01), ALL (NBL01), STF (LSC01), TCH (MET01, DB).
