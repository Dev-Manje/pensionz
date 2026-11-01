---
name: pz-backend-feature
description: Use when adding or changing a Pensionz backend feature in backend/app — a new endpoint, model/column, migration, service function, approval workflow, ledger posting, bonus/unit transaction, notification or PDF/Excel export/import. Encodes the access-control, maker-checker, ledger, period and migration rules the codebase relies on.
---

# Backend feature conventions (FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2)

Same stack and conventions as the sibling Money Market platform
(`C:/moneymarket/moneymarket/backend`) — look there for proven patterns before inventing one.

## Where things go

| Layer | Path | Notes |
|---|---|---|
| Model | `backend/app/models/<area>.py` | export in `models/__init__.py` |
| Schema | `backend/app/schemas/<area>.py` | `XCreate` / `XUpdate` (all optional) / `XOut` with `model_config = {"from_attributes": True}` |
| Endpoint | `backend/app/api/v1/<area>.py` | thin: auth, load, call service, return; register in `api/v1/router.py` |
| Logic | `backend/app/services/<area>.py` | all business rules, money and unit movement |
| Migration | `backend/alembic/versions/` | hand-written, one per change |
| Imports/exports | `backend/app/services/io/<area>.py` | Excel/CSV templates (bulk members, contribution schedules), PDF statements |

Areas: `funds`, `schemes`, `members`, `kyc`, `contributions`, `bonus`, `units`, `claims`,
`payments`, `payroll`, `ledger`, `periods`, `reports`, `portal`, `migration`.

## Access control — both checks, every time

1. Role gate: `Depends(require_roles(UserRole.x, ...))`; users hold several roles ("has any of").
2. Row-level gate: `require_member_access(db, member, user)` / `require_employer_access(...)` /
   `require_fund_access(...)` — staff limited to the funds they administer, employer users to
   their employer's members, members to themselves, trustees to their funds.
3. Sensitive fields (ID numbers, bank details, medical evidence, beneficiary details) only in
   responses for roles that need them — separate `XSensitiveOut` schemas.

## Maker-checker

- Money, member data affecting money, bank details, config, bonus rates, unit prices,
  claims, payments and reversals are **requests** in a `pending_*` status; approval by a
  different user (`if user.id == req.initiated_by_user_id: 400`).
- Queue pattern: `GET /<area>/pending` + `POST /<area>/{id}/approve` / `reject` (reason required).
- Claims and payments may need **two** approval levels by amount (configurable thresholds).

## Money, units & periods

- Every balance change posts balanced entries via `ledger.post(db, fund_id, ...)`; member
  transactions are rows with a configured **transaction type** (code, effect Dr/Cr, reversal
  type). Never update a stored balance without the matching transaction + ledger post.
- **Reversals** create the paired reversal type referencing the original; never edit/delete.
- **Processing month:** a posting's period must be the fund's open period
  (`periods.require_open(db, fund_id, date)`); closed periods reject with 409.
- Amounts `Numeric(18,2)`, rates `Numeric(9,6)`, prices `Numeric(18,6)`, units `Numeric(20,6)`;
  round half-up at posting time.

## Migrations

- `revision` = short random hex, `down_revision` = `alembic current` output.
- New columns nullable or server-defaulted. Enums are VARCHAR via `models/mixins.str_enum`
  (no Postgres enum types), so adding a value needs no migration; never remove or rename a
  value that stored rows use.
- Maker-checker: register an `ApprovalKind` in the domain service and call
  `approvals.submit(...)`; approval runs its `apply` (see `services/users.py` for the pattern).
- Apply: `docker compose exec backend alembic upgrade head`.

## Side effects

- Notifications via `services/notifications.py` (`pz-notifications`), written before commit.
- Generated documents (statements, payment vouchers, benefit quotes, tax certificates) →
  `GeneratedDocument` + MinIO; PDF/Excel helpers in `services/reports_export.py`.

## Done means

Seed updated if useful, as-built doc updated (`docs/design/implementation-status.md`), and
`pz-verify` run including negative access tests (wrong role → 403, other employer's member →
403, closed period → 409).
