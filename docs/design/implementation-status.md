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

### Setup lists: account & transaction types, reference data (FR-CFG-005, 006, 010) — 2026-11-01

Migration `c3f9a7d25e81`: `account_type`, `transaction_type`, `district`, `traditional_authority`,
`village`, `country`, `reference_item` (relationships / ID types / permit types / salutations), plus the
existing `bank` / `bank_branch`. **`services/system_lists.py`** registers each list once (`SystemList`:
model, `Field`s, unique keys, parent filter, fixed columns, validate / after-apply hooks); every list gets
approval kind `list_<name>` (scheme setup checker), case-insensitive uniqueness incl. pending requests,
fields that lock once set, and retire-not-delete via `active`. `describe()` serves the field metadata.
Transaction types: code/effect fixed; reversal must exist with the opposite effect and is paired both
ways on approval; pairing can't change. API: `GET /setup/lists`, `GET /setup/lists/{name}?parent=`,
`POST /setup/lists/{name}`, `PUT /setup/lists/{name}/{id}`. Frontend: sidebar "Setup" — one generic page
(group menu / phone select, parent filter, search, table, form dialog built from the metadata).
Country data: `app/data/countries.py` (generated from the Windows region database).

### Fee rules (FR-CFG-008) — 2026-11-01

Migration `d4a8b2c61f93`: `fee_rule` (fund, optional scheme, code unique per fund, fee type, basis
pct_contributions / pct_assets (per year) / flat_per_member, rate, payer fund / employer / member,
frequency per_contribution / monthly / quarterly / annually, effective_from / optional effective_to).
`services/fee_rules.py` on `FundConfig` (kind `fee_rule`; `FundConfig` gained a `readable` hook so the
checker sees "CTE01 — …" / "Whole fund"). Rules: % of contributions ⇔ per contribution; % of assets ≤ 10%
a year; employer must belong to the fund; same type + scope may not overlap in time.
`rules_in_force(db, fund_id, scheme_id, as_of)`: an employer's own rule replaces the fund-wide rule of the
same type. Frontend: fund tab "Fees" (table + dialog). Seed (invented): UMB01 ADM 1.5% (member),
ADM-CTE 1.25% (employer, CTE01), IMF 0.75% p.a. of assets (fund).

## Phase 2 — Onboarding & KYC (FR-ONB) — 2026-11-02

Migration `e7b3c9a14d52`: `declaration_version`, `party`, `kyc_application`, `kyc_document`, sequence
`kyc_reference_seq`; KYC products seeded as Setup list `kyc_products`.
- **Rules** (`services/kyc_forms.py`): document requirements per client type from the source form, with
  per-person slots (`director_id:<i>`, `signatory_address:<i>`) and foreign-resident permits; required
  fields and conditional checks; `problems()` lists everything still missing; `risk()` rates high for any
  PEP (entity, director, signatory, self, related), medium for unregistered groups, foreign nationals and
  business income — with reasons.
- **Workflow** (`services/kyc.py`): staff capture (compliance, relationship manager, member admin) or portal
  applicants (principal officer / individual) own drafts; submit needs zero problems and acceptance of the
  current declaration version (name, time, IP stored); compliance (not the capturer) starts review, accepts or
  rejects each document (reason required), returns (applicant fixes; resubmission goes back to the same
  reviewer), rejects or approves (all documents accepted; risk override needs a note); high risk →
  `awaiting_senior_approval` → an administrator who took no part decides. Approval creates/refreshes `party`
  with `kyc_review_due` = today + `kyc_review_years_<rating>` (regulatory parameters, KYC group).
- **Documents**: MinIO bucket created at API start-up (`app/main.py` lifespan); type sniffed from content,
  10 MB max, re-upload supersedes; downloads stream through the API with an audit event per view.
- **Expiry** (`services/kyc_expiry.py`, job `kyc_expiry_reminders` 07:00): reviews due and approved
  ID/permit expiry within 31 days → reminders 30/7/0 days before and weekly when overdue; `GET /kyc/expiring`.
- API `/api/v1/kyc/…`: options, declarations, applications (list/create/get/save), documents
  (upload/remove/file), submit, start-review, document review, return, approve, reject, senior-decision,
  expiring, parties.
- Frontend: sidebar "KYC" (queue tabs: To review / Drafts & returned / Senior approval / Expiring / All),
  capture dialog, one stepper for all client types driven by `routes/staff/kyc/kycSchema.ts`
  (phone: step picker), document cards (upload / replace / view / accept / reject), declaration step with
  the outstanding-items list, review page (risk, declaration, duplicates, answers, sticky actions).
- Robustness fixes: `tzdata` pinned (zoneinfo had no Africa/Blantyre on Windows); the app keeps the session
  and retries when the server is briefly unreachable instead of signing the user out.

## Phase 3 — Membership (FR-MEM)

### Member record, lifecycle, duplicates, KYC link (FR-MEM-001…005, 011, FR-ONB-105) — 2026-11-02

Migration `a1c4e8f27b93`: `member` (fund, optional scheme + category, optional KYC `party`; account code unique
per fund from sequence `member_number_seq` → `<fund code><6 digits>` unless given; legacy identifiers, names,
ID with normalised `id_number_key`, civil statuses, places by Setup-list id, contact, bank, next of kin, join
dates, status + effective date, exit date, date of death, `regulatory_data` JSONB), `member_status_change`,
`member_assignment` (employer/category periods), `scheme.party_id`.
`services/members.py`:
- approval kinds `member_new`, `member_update` (data correction), `member_status` — checker `member_checker`,
  fund-scoped; payload shows readable values (names, labels, dates) with raw values under `_values`;
- rules: fund active; employer active and in the fund, category active and of that employer with terms in force on
  the join date, entry ages; personal pension / minors' trust have no employer and personal pensions need an
  individual KYC client; DOB past, join not future; TA/village/branch consistency; group accounts in the same fund;
  same ID in the same fund or a pending request → 409;
- `find_duplicates` across funds (ID or name + DOB) — `GET /members/duplicates`, shown live and to the checker;
- `TRANSITIONS`, `ACTIVITIES` / `allows()`; leaving statuses set the exit date, deceased the date of death;
- `kyc_status` / `payment_block` (none, review overdue, accepted document expired), `prefill_from_party`,
  `company_info` (employer, corporate form from its KYC, TPIN, fund);
- `funds.fund_has_members` now real (fund code/type lock).
API: `GET /members` (paged, search name/code/employee/old no./ID, fund/employer/status/group filters),
`POST /funds/{id}/members`, `GET|PUT /members/{id}`, `POST /members/{id}/status`, `GET /members/kyc-prefill/{party}`;
`GET /kyc/parties?client_type=` now open to setup and member staff. ID and bank numbers masked outside
`SENSITIVE_ROLES`.
Frontend: sidebar "Members" — list (filters in the URL, paging), `/members/new` 6-step stepper reusing the KYC field
renderer (draft kept in localStorage), `/members/<id>` tabs Main information / Member information / Company info /
KYC / Regulatory Authority Data / History, "Correct details", "Change status" dialog. Employer form: KYC client
picker; employer page shows KYC standing and member count. `StatusChip` takes an optional `label`.
Seed: nine invented members across CTE01, NBL01, LSC01, MET01 (one deferred, one inactive).

### Beneficiaries, salary and service history (FR-MEM-008, 009) — 2026-11-02

Migration `b7d2f5a39c16`: `beneficiary_nomination` (member, version, signed date, `is_current`, note, who requested /
approved) with `beneficiary` rows (name, relationship code, DOB, ID, contact, address, share %, guardian details);
`member_salary` (from date, monthly basic and pensionable, unique per member + date); `member_service_period`
(start, optional end, part-time factor, note). `services/member_records.py`, all checked by the member checker:
- `beneficiary_nomination`: shares total exactly 100.00%, relationships from the Setup list, no name twice, under-18s
  (on today's date) need guardian name, relationship and phone; approval makes it version n+1 and the old one history;
- `member_salary`: from ≥ the earlier join date, ≤ a year ahead, active/inactive members only; same date corrects;
  `salary_on(member, date)`;
- `member_service`: the whole list replaces the old (audit keeps the before lines); no overlaps, only the latest open,
  nothing in the future; `period_years` / `service_years(periods, as_of)` (known answers in tests).
API: `GET|POST /members/{id}/beneficiaries`, `GET /members/{id}/employment`, `POST /members/{id}/salaries`,
`PUT /members/{id}/service`. Beneficiary phone/email/address hidden and ID numbers masked outside `SENSITIVE_ROLES`.
Frontend: member tabs "Beneficiaries" (current table with Minor chips, earlier versions, nomination dialog with live share
total and guardian fields for minors) and "Salary & service" (now card, salary history + record dialog, service periods
+ editor, total pensionable service).

### Category moves and employer transfers (FR-MEM-010) — 2026-11-02

Approval kind `member_move` (`services/members.propose_move`, `POST /members/{id}/move`): active or inactive members;
target employer active and in the fund (a different employer only in an umbrella fund → `employer_transfer`, otherwise
`category_move`); target category active with terms in force on the effective date; effective date after the current
assignment's start and not in the future. Approval closes the open `member_assignment` the day before, opens the new
one with the reason, updates the member (and for transfers the employer join date and optional new employee number).
Data corrections remain `member_update`. Frontend: "Move / transfer" (umbrella) or "Move category" dialog on the member page.

### Bulk member upload and application form (FR-MEM-006, 007) — 2026-11-02

Migration `c9e4a1d7f205`: `member_import` (fund, employer, file name, status validated / pending_approval / imported /
rejected / cancelled, `rows` JSONB with raw values, converted values, errors, warnings and the created member, counts).
`services/io/member_import.py`:
- `COLUMNS` defines the template (labels are the file's contract; required marked *); `template()` adds list drop-downs and a
  Guide sheet (column help, the employer's active categories, titles, ID types, relationships, banks + branches);
- reading: .xlsx ("Members" sheet or the first) or .csv, header match by label, blank rows skipped, ≤ 2,000 rows, ≤ 5 MB;
  values accept codes or names (title, ID type, relationship, nationality, bank/branch), F/M, Excel dates or YYYY-MM-DD /
  DD/MM/YYYY, amounts with commas;
- each row: `MemberCreateIn` + `members._check_details` / `_check_employment` / account code / pending requests, then
  in-file duplicates (same ID or name + DOB → error on the later row); cross-fund duplicates → warnings;
- a new upload for the same employer by the same maker cancels an unsubmitted earlier one; `errors_workbook()`;
- `submit` (uploader only) → approval kind `member_import` (member checker; payload lists up to 25 members);
  approval re-checks each row, creates it via `members.create_member` (+ `member_salary` from the join date when a salary
  was given) or marks it "Not imported: …"; reject/withdraw → rejected/cancelled.
`services/io/member_forms.py`: reportlab A4 application form in capture order (employer/fund with category tick boxes when
an employer is given, personal, address, bank, next of kin, 5-row beneficiary table, declaration, signatures, office use).
API (registered before `/members/{id}`): `GET /members/import-template?scheme_id=`, `GET /members/application-form[?scheme_id=]`,
`POST /members/imports` (multipart), `GET /members/imports`, `GET /members/imports/{id}`, `GET …/errors`, `POST …/submit`,
`POST …/cancel`. `services/members.create_member` is shared by single and bulk creation.
Frontend: `/members/import` (fund + employer, template / form / upload, results with counts, problem filter, error download,
submit / withdraw, recent uploads); "Bulk upload" button on the members list.

## Phase 4 — Ledger & contributions (FR-ACC core, FR-CON)

### Fund ledgers and member transactions (FR-ACC-001…003) — 2026-11-02

Migration `d2a7c4e9b318_ledger.py`; `models/ledger.py`, `services/ledger.py`, `api/v1/ledger.py`.
- `gl_account` per fund (book `fund`) plus the administrator book (`fund_id` NULL: 1500/1510/4500). The **proposed** chart
  (pz-accounting, + 2800 Refunds Payable to Employers) is created for a fund on approval of the fund and lazily by
  `ledger.ensure_chart` — finance still to confirm (open decision).
- `journal_entry` (running number per book+fund → "JE-000123", entry date, processing month, business event
  `entity_type`/`entity_id`, `reverses_entry_id` unique) + `ledger_line` (one side only, `member_id`/`scheme_id`/`component`
  analysis). `member_transaction`: member, transaction type code/name/effect copied at posting, component (employee,
  employer, voluntary, severance, transfer_in), amount > 0, contribution month, reference, journal entry, `reverses_transaction_id`.
- Database triggers refuse UPDATE/DELETE on all three tables (FR-ACC-003).
- `ledger.post(...)`: rounds half-up per line, Σdr = Σcr per fund (500 otherwise), unknown/retired GL code 409, date must be
  in the fund's open processing month (409). `post_member_transactions(...)` derives each member line pair from the
  transaction type's GL codes (type 1: Dr 2100 / Cr 2000) and accepts extra lines (fees). `reverse(...)` mirrors every line
  into the open month and adds the paired reversal type per member transaction; a reversal can't be reversed and an entry is
  reversed once (409).
- Balances are always summed: `account_balances`, `member_balance`, `member_balances_by_component`, `tie_out`
  (Σdr = Σcr and Σ member accounts = GL 2000). `periods.has_postings` now uses the ledger; the month-end check
  "Fund ledger balanced and ties to member accounts" is live.
- API (staff with fund access): `GET /funds/{id}/ledger/accounts[?period=]` (trial balance + tie-out),
  `GET /funds/{id}/ledger/entries?period=&entity_type=&account=&page=`, `GET /members/{id}/transactions`.
- Frontend: fund **Ledger** tab (`FundLedgerTab.tsx`: proposed-chart notice, tie-out banner, trial balance, journal with
  expandable lines, filter by account); member **Transactions** tab (`MemberTransactionsTab.tsx`: balance, per-component
  contributions/bonus/withdrawals, transactions with reversed markers).

### Receipts and unallocated suspense (FR-CON-004) — 2026-11-02

Migration `e3b8d5f1a274_receipts.py`; `models/contribution.py` (`contribution_receipt`), `services/receipts.py`,
`api/v1/receipts.py`. Decided with the user: two stages, no posting before the money is confirmed.
- **Payment notice** (`submit_notice`, principal officer of that scheme only; portal screen in Phase 5): status `notified`,
  number `<FUND>-N000001`, notified amount, payment date/method, payer reference, month; contributions officers get an
  in-app notice. Staff **confirm** it (`POST /receipts/{id}/confirm`: actual amount, value date, fund bank account, bank
  reference) or **decline** it (`/decline`, reason ≥ 5 chars → officer notified).
- **Staff capture** (`POST /funds/{id}/receipts`) for money without a notice; employer optional (= unidentified).
- Both submit approval kind `receipt_confirm` (contributions checker, fund-scoped). Proposed values are shown on the receipt
  while pending. Apply: receipt number `<FUND>-R000001`, posts **Dr 1000 / Cr 2100** (scheme analysis) dated the value date
  if it is in the open month, else the first day of the open month (future value date 400; after the open month 409);
  principal officers of the employer notified. Rejecting a notice's confirmation returns it to `notified`; a rejected staff
  capture is `rejected`, a withdrawn one `cancelled`.
- **Unidentified money**: `POST /receipts/{id}/identify` → kind `receipt_identify` → reclass Dr 2100 / Cr 2100 (scheme).
- Proof of payment: `POST/GET /receipts/{id}/proof` (PDF/image ≤ 10 MB, MinIO `receipts/<id>`, views audited).
- `GET /funds/{id}/receipts?status=&unidentified=&unallocated=&q=` with `unallocated_ageing` (0–30/31–60/61–90/90+ days
  from value date) and `notices_waiting`. `allocated_amount` is maintained by allocation (next task).
- Frontend: **Contributions** menu (`/contributions?fund=`), "Money received" tab (notice banner, suspense ageing tiles,
  filters, list), record dialog; receipt page `/contributions/receipts/:id` (confirm / not received / identify, proof).
