# Pensionz — Task List

Master task list, built 2026-11-01 from `docs/REQUIREMENTS.md`. Each item cites the FR IDs it
delivers. Tick (`[x]`) only after verifying with `pz-verify`, with a short note/date.
Say "next task" or "work on [item]" — the `pz-task` skill drives the loop.

| Skill | Use for |
|---|---|
| `pz-task` | Pick → build → verify → tick loop over this file |
| **Domain** | |
| `pz-pension-domain` | DC/DB/umbrella/personal, bonus & units, benefits, Pension Act 2023, legacy vocabulary |
| `pz-scheme-config` | Fund/scheme/category/parameter setup — the build chain |
| `pz-accounting` | Fund ledgers, chart of accounts, posting recipes, reconciliation, period close |
| `pz-banking` | Receipts, payments, payroll, bank details/fraud, bank reconciliation |
| `pz-kyc-compliance` | Corporate/group/individual KYC, documents, PEP/EDD, AML, data protection |
| **Backend** | `pz-backend-feature`, `pz-backend-architecture`, `pz-notifications` |
| **Frontend** | `pz-frontend-architecture`, `pz-ui-conventions`, `pz-cross-device`, `pz-portal-self-service` |
| **Quality** | `pz-testing`, `pz-verify` |

---

## Open decisions

Answered:
- [x] **Stack** — 2026-11-01: same as Money Market (FastAPI/SQLAlchemy/Alembic/Postgres,
      React/TS/Vite/MUI, Docker Compose). Ports 5178 / 8002 / 8026.
- [x] **Scope** — 2026-11-01: DC employer, umbrella, personal pensions, DB (+ minors' trust from legacy).
- [x] **Portals at go-live** — 2026-11-01: **member portal** and **principal officer portal**
      (the scheme/fund officer who remits contributions) are both must-have.
- [x] **Branding** — 2026-11-01: Pensionz is an **independent product**; Old Mutual/PCL documents are
      reference only. Neutral brand in `frontend/src/brand.ts` + `BRAND_*` settings, re-themeable later.
- [x] **Fund setup details** — 2026-11-01: fund code free text ≤ 10 chars (legacy codes kept);
      bank/branch picked from a seeded Malawi bank list (pulled forward from FR-CFG-010); trustees are
      a list (no logins until the trustee portal); optional financial year-end month on the fund;
      fund logo deferred to statements (Phase 7).
- [x] **Local dev runs outside Docker** — 2026-11-01: API, worker and Vite run on the host
      (`backend/.venv`, `backend/.env`, `frontend/.env`); only Postgres :5433, MinIO and Mailpit
      stay in Docker. Full Docker build revisited later (network too slow for image builds).

Open — the default in *italics* is what we build to until answered (from REQUIREMENTS §10):
- [ ] **Legacy system & extract** — PFS on Oracle XE identified 2026-11-01 (`docs/legacy/PFS-analysis.md`);
      still need DB access/export, volumes, history depth. Needed by Phase 11.
- [ ] **Bonus calculation method** — *opening balance × rate × days/365 plus each contribution ×
      rate × days-in-period-from-allocation/365; applies to EE+ER+AVC+transfer-in; interim rate for
      mid-period exits with final true-up; 2 dp half-up per member per component.* Needed by Phase 6.
- [ ] **Ageing buckets** on member screen — *age of employer contributions receivable (arrears).*
- [ ] **UPID / BI UPID, Regulatory Authority Data tab, KYC 1–4 tabs, "Share" account type** —
      *store UPID/BI UPID as optional text fields; regulatory tab = free key/value fields until the
      field list is known; "Share" account type seeded but unused.*
- [ ] **Individual KYC items 28–32** — *next of kin.*
- [ ] **Regulatory figures** — *EE 5% / ER 10% minimums, lump sum max 50%, retirement 50–70,
      unemployment access after 3 months, 50% access within 5 years of NRA; all editable
      effective-dated parameters.*
- [ ] **Chart of accounts & posting recipes** (`pz-accounting`) — *build as proposed; finance to
      confirm.* Needed by Phase 4.
- [ ] **Banks, payment file formats, mobile money** — *cheque + generic EFT CSV export.* Phase 9.
- [ ] **Minors' trust payout rules** — *instalments on approved request; balance at 18.* Phase 8.
- [ ] **Hosting, staff SSO, OTP channel** — *local accounts + email OTP; SSO later.*


---

## Phase 0 — Foundation

- [ ] Repo scaffold: `docker-compose.yml` (db :5433, minio :9002/9003, mailpit :8026, backend :8002,
      worker, frontend :5178), `.env.example`, `start-servers.bat` / `stop-servers.bat`, `.gitignore`.
      — 2026-11-01: db/minio/mailpit containers verified; backend/worker/frontend **images not yet
      built** (network too slow) and start/stop scripts still Docker-only → add host-mode scripts.
- [x] Backend skeleton: FastAPI app, config, DB session, Alembic, structured logging, health endpoint,
      error handling. — done 2026-11-01 (host-run): initial migration `b1e58cad77d5` reviewed + applied,
      `/health` ok.
- [x] Auth: users, roles (all §3 roles, multi-role), JWT access/refresh, password reset, lockout;
      `require_roles`. FR-SEC-004 — done 2026-11-01: pytest + curl (401 no token, 403 wrong role,
      423 after 5 bad passwords). `user_fund_access` scoping (FR-SEC-001) **moved to Phase 1 fund setup**.
- [x] Audit trail (`audit_event`, before/after JSON) + maker-checker base (`ApprovalRequest` engine,
      approver ≠ initiator). FR-SEC-002, FR-SEC-003 — done 2026-11-01: own approval 400, non-checker
      403, double approve 409, second admin approves 200.
- [x] Worker + `job_run` runner + `notification_outbox` delivery (email via Mailpit). FR-NOT-001
      — done 2026-11-01: invite email delivered to Mailpit by the host-run worker.
- [x] Frontend skeleton: Vite/React/TS/MUI, theme, `api/client.ts`, auth context + login, `RoleRouter`
      SECTIONS (staff / member `/member` / principal officer `/po`), shared components
      (PageHeader, ResponsiveTable, StatusChip, TableStateRow, FeedbackProvider, ConfirmDialog).
      — done 2026-11-01: `tsc -b` clean, screenshots of login, home, approvals, users, `/po`,
      `/member` at 1440 + 390 viewed, no JS exceptions.
- [x] Test harness: pytest (`pensionz_test` DB, rollback fixture, factories), Vitest; `TEST_USERS.md`;
      seed script with one user per role. — done 2026-11-01: pytest 26/26, vitest 31/31; seed now
      marks seeded users' passwords as set (they showed "Invitation sent").
- [x] Admin: user management screen (create/invite, roles, deactivate). — done 2026-11-01: list +
      Add user dialog screenshotted at both widths; create → approve → invite verified via API.
      Fund-access assignment comes with `user_fund_access` in Phase 1 fund setup.

## Phase 1 — Setup & reference data (FR-CFG)

- [x] Fund/company setup: code, name, address 1–5, phone, fax, TPIN, email, website, contact
      person (name, email, phone, alt phone), fund type, registration no., trustees, bank
      accounts; maker-checker. FR-CFG-001 — done 2026-11-01, see `services/funds.py`,
      `routes/staff/funds/`, migration `c47e2a91f0d3`:
  - [x] Banks & branches reference table + seeded Malawi banks (part of FR-CFG-010) — 8 banks × 4
        main-town branches (starter list, no SWIFT/branch codes); `GET /reference/banks`.
  - [x] `fund` (+ status, financial year-end month), `fund_trustee`, `fund_bank_account` models +
        hand-written migration (`alembic check` clean).
  - [x] `user_fund_access` scoping: admin/auditor see all, other staff assigned funds only, else 404;
        maker **and checker** auto-granted on approval of a new fund (checker added so the fund's later
        edits can be approved without an admin grant); assigned in Users via `user_access` approval.
        Approval engine is fund-scoped too (visibility, notifications, deciding). FR-SEC-001
  - [x] Approval kind "Fund setup" (one snapshot incl. trustees/bank accounts); code/type lock once
        members exist (hook returns False until Phase 3); account numbers masked for roles that don't
        need them. FR-CFG-011, FR-SEC-002, FR-SEC-005
  - [x] Screens: Funds list, fund page (Details / Trustees / Bank accounts tabs), sectioned
        create/edit form; Approvals diff now shows only changed fields. Screenshots at 1440 + 390 viewed.
  - [x] Tests: `tests/test_funds.py` (17) + `DiffView.test.tsx`; API smoke 17/17 incl. 401/403/404/
        409/422; seed has four invented funds.
- [ ] Bank & branch codes / SWIFT codes for the seeded banks (needs a confirmed list) and a
      reference-data maintenance screen. FR-CFG-010
- [ ] Processing month per fund: open period, close with checklist stub, re-open with approval;
      `periods.require_open`. FR-CFG-002
- [ ] Participating employers / schemes under a fund (umbrella), with contribution day and contacts;
      link principal officers to schemes. FR-CFG-003
- [ ] Benefit categories: DC design, EE/ER rates, salary basis, NRA, eligibility, vesting scale,
      default option. FR-CFG-004
- [ ] Account types (Pension Fund, Member, Company, Reserve, Share) and transaction types
      (codes 1–6 with effect + paired reversal + GL mapping). FR-CFG-005, FR-CFG-006
- [ ] Investment options: declared-rate pools (unit-priced placeholder). FR-CFG-007
- [ ] Fee rules. FR-CFG-008
- [ ] Regulatory parameters & tax tables (effective-dated) with validation of category rates. FR-CFG-009
- [ ] Reference data: banks/branches, districts/TAs/villages, countries/nationalities, relationships,
      ID & permit types, salutations. FR-CFG-010
- [ ] Config diff view + effective dates on approval. FR-CFG-011

## Phase 2 — Onboarding & KYC (FR-ONB)

- [ ] Party model (corporate / group / individual), documents (MinIO, type, issue/expiry dates),
      declarations with versioned text. FR-ONB-001…008
- [ ] Corporate KYC form (stepper, draft/resume, uploads, directors repeatable, PEP). FR-ONB-C01…C09
- [ ] Group KYC form (unlimited signatories with ID + proof of address each). FR-ONB-G01…G05
- [ ] Individual KYC form. FR-ONB-I01…I13
- [ ] Staff capture on behalf + compliance review queue (accept/reject per document, re-upload loop),
      risk rating, EDD flag, approval → employer / member. FR-ONB-101, 103, 105
- [ ] KYC expiry dates + reminders job. FR-ONB-104

## Phase 3 — Membership (FR-MEM)

- [ ] Member record with legacy tabs: Main information, Member information, Company info, KYC,
      Regulatory Authority Data. FR-MEM-001…004
- [ ] Member status lifecycle (Active, Inactive, Deceased + Deferred, Pensioner, Exited) with
      audited transitions. FR-MEM-005
- [ ] Beneficiaries (shares = 100%, guardians for minors, history). FR-MEM-008
- [ ] Salary & service history. FR-MEM-009
- [ ] **Bulk member upload template** (design, download, validate, row errors, maker-checker
      import) + printable new-member application form. FR-MEM-006, FR-MEM-007
- [ ] Category moves, employer transfers, data corrections via change requests. FR-MEM-010
- [ ] Duplicate detection. FR-MEM-011

## Phase 4 — Ledger & contributions (FR-ACC core, FR-CON)

- [ ] GL accounts per fund (seed proposed chart), `ledger.post` balanced per fund, member
      transactions with transaction types, reversals. FR-ACC-001…003
- [ ] Receipts (bank, value date, reference, payer) + unallocated suspense. FR-CON-004
- [ ] Contribution schedules: Excel/CSV template upload + manual capture, row validation, rates ≥
      minimum. FR-CON-001, FR-CON-003
- [ ] Reconcile schedule ↔ receipt, over/under-payment rules, **Initial Allocation** posting net of
      fees, maker-checker. FR-CON-005, FR-CON-006
- [ ] Allocation reversals. FR-CON-007
- [ ] Expected schedules, arrears per employer/month, late-payment interest, ageing buckets.
      FR-CON-002, FR-CON-008, FR-MEM-012
- [ ] Contribution receipt/acknowledgement PDF. FR-CON-010

## Phase 5 — Principal officer portal (FR-PRT-001, 005, 006)

- [ ] Portal access: staff invite principal officers, OTP first login, officer ↔ scheme links
      (one officer, many schemes; many officers per scheme). FR-PRT-006
- [ ] PO dashboard: schemes, current month remittance status, arrears, recent activity.
- [ ] Organisation KYC from the portal (reuse Phase 2 forms) and change requests.
- [ ] Remit contributions: upload/capture schedule, attach proof of payment, see validation errors per
      row, submit → staff allocation queue; history with allocation status.
- [ ] Members: list (HR-level fields only), new member application + bulk upload, salary updates,
      exit notifications (start claim).
- [ ] Statements of contributions / invoices / arrears download.
- [ ] Notifications to POs: schedule due, received/rejected, arrears. FR-NOT-003

## Phase 6 — Bonus / earnings (FR-EAR)

- [ ] Bonus declarations per fund (period, rate, interim/final) with approval. FR-EAR-001
- [ ] Bonus run: preview → approve → post Bonus (type 6) per member per component; idempotent batch. FR-EAR-002, 003
- [ ] Bonus reversal (type 5) whole run / individual; interim → final true-up. FR-EAR-004

## Phase 7 — Enquiries, statements & member portal (FR-ENQ, FR-PRT-002)

- [ ] Account enquiry (main info, current-period transactions, history, statement, transaction trail,
      contributions, voluntary contributions; balance + status). FR-ENQ-001
- [ ] Comprehensive enquiry screen. FR-ENQ-002
- [ ] Member Benefit Statement PDF (single + bulk, legacy layout in `docs/legacy/PFS-analysis.md`). FR-ENQ-003
- [ ] Client Statement (aged analysis), Transaction Trail, Contributions Trail, Voluntary Contributions Trail. FR-ENQ-008
- [ ] Member portal access: invite or self-register (member no. + ID + DOB + OTP). FR-PRT-006
- [ ] Member portal: balances by component, transactions, statements, beneficiaries, contact/bank
      change requests, KYC document updates. FR-PRT-002
- [ ] Notifications to members (joined, statement ready, bank details changed). FR-NOT-003

## Phase 8 — Benefits & claims (FR-BEN)

- [ ] Claim types, intake (staff, PO exit notification, member portal), document checklists. FR-BEN-001, 002
- [ ] Benefit quote (balances, vesting, interim bonus, lump sum/residual split, tax). FR-BEN-003, 010
- [ ] Elections (lump sum + annuity / programmed withdrawal, small-balance rule). FR-BEN-004
- [ ] Approval levels by amount; Withdrawal (type 3) & reversal (type 4) postings; forfeiture to reserve.
      FR-BEN-005, 007, 008
- [ ] Death claims: trustee decision workflow, minors' shares to minors' trust accounts. FR-BEN-006
- [ ] Claim tracking in member portal + PO portal; claim notifications.

## Phase 9 — Payments (FR-PAY)

- [ ] Payment entry with multi-client allocations (legacy), payment voucher PDF. FR-PAY-001, 002
- [ ] Payee bank-detail verification, change maker-checker, cooling-off. FR-PAY-004
- [ ] Payment batches, second approval, cheque/EFT export, returns. FR-PAY-003, 005

## Phase 10 — Accounting, reconciliation & reports

- [ ] Account reconciliation (sub-ledger vs control, schedule/receipt/allocation, ageing). FR-ACC-004
- [ ] Period close checklist & enforcement. FR-ACC-006
- [ ] Bank statement import & matching. FR-ACC-005
- [ ] Trial balance, net assets statements; operational reports; Excel/PDF export.
      FR-ACC-007, FR-ENQ-004, FR-ENQ-007

## Phase 11 — Legacy data migration (FR-MIG)

- [ ] Get read access to the PFS Oracle XE database (or an export); document its tables.
- [ ] Mapping spec from legacy extract (sign flip, transaction codes, components); staging loads; keep legacy IDs. FR-MIG-001, 002, 004
- [ ] Balance reconciliation report & sign-off. FR-MIG-003

## Later phases (after go-live)

- [ ] Unit-priced portfolios, switches, life-stage. FR-EAR-005, 006
- [ ] Pensioner payroll & life certificates. FR-PAY-006, 007
- [ ] Personal pensions + individual portal. FR-CON-009, FR-PRT-003
- [ ] DB administration. FR-BEN-009, FR-CFG-012
- [ ] Trustee portal. FR-PRT-004
- [ ] Regulatory returns, trustee packs, GL export, screening, integrations. FR-ENQ-005, 006, FR-ACC-008, FR-ONB-102

---

## Session log

- 2026-11-01 — Requirements written (`docs/REQUIREMENTS.md`), 15 `pz-*` skills installed, task list
  created. Principal officer + member portals confirmed as go-live. Next: Phase 0.
- 2026-11-01 — Analysed `PFS.docx` + member benefit statement → `docs/legacy/PFS-analysis.md`;
  requirements updated (severance component, statements FR-ENQ-008, Oracle XE legacy).
- 2026-11-01 — **Phase 0 code written, NOT yet verified** (nothing ticked). Backend: config, models
  (user/roles, audit_event, approval_request, job_run, notification outbox/inbox), services (passwords
  + lockout, approvals engine, users via maker-checker, notifications + delivery), API (auth, users,
  approvals, me/notifications), worker + job runner, seed, pytest suite. Frontend: brand/theme, auth
  pages, RoleRouter, Home, Approvals, Users, member + PO portal landing pages. Branding made
  independent (`frontend/src/brand.ts`).
  **Blocked by disk space** (C: had 0.5 GB free; Docker build died, daemon hung). Backend Dockerfile
  slimmed (no apt/gcc). Frontend `.npmrc` legacy-peer-deps added (npm peer resolution failed).
  **Resume here:** start Docker → `docker compose up -d --build` → generate initial Alembic migration
  (`alembic revision --autogenerate -m initial`, review it) → `alembic upgrade head` → `python -m app.seed`
  → `pytest -q` → host/frontend `npm install` → `tsc -b --noEmit` + `npm test` → screenshots (login,
  approvals, users, /member, /po at 1440 + 390) → tick Phase 0 items.
- 2026-11-01 — Disk freed. Docker image builds too slow on this network → switched to host-run dev
  (decision above). Frontend verified: vitest 31/31, `tsc -b` clean after fixing two MUI v9 icon
  imports (`CheckCircleOutlined`, `PersonOutlined`); `npm rebuild` restored missing `.bin` shims.
  `tests/conftest.py` now derives the test DB from settings (works on host and in Docker).
  Backend venv install in progress. `user_fund_access` was not built in Phase 0 → moved into fund
  setup. Fund setup plan agreed (sub-items under Phase 1).
- 2026-11-01 — **Phase 0 verified on the host** (7 of 8 ticked; repo scaffold waits on Docker images +
  host-mode start script). Initial migration generated/applied, pytest 26/26, API smoke 19/19
  (scratchpad script), 14 screenshots viewed. Next: Phase 1 fund setup, starting with banks & branches.
- 2026-11-01 — **Phase 1 fund setup verified and ticked** (banks/branches, funds + trustees + bank
  accounts via `fund_setup` approval, `user_fund_access` scoping incl. the approval engine, masking,
  Funds screens, fund picker in Users). pytest 43/43, vitest 33/33, tsc clean, API smoke 17/17,
  screenshots of list/detail/tabs/form/approval diff/users at 1440 + 390 viewed, no JS exceptions.
  Next: processing month per fund (FR-CFG-002).
