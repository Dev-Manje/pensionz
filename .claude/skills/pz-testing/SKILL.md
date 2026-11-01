---
name: pz-testing
description: Use when writing, running or setting up automated tests for Pensionz — backend pytest (services, API, access control, ledger/unit/bonus invariants, benefit calculations, migrations, data-migration loads), frontend component tests, or end-to-end flows — and whenever a change touches money, units, benefits, approvals or permissions.
---

# Testing

Set up the foundation in the first build phase, copying Money Market's
(`C:/moneymarket/moneymarket/backend/tests/conftest.py`, `factories.py`):

- separate DB `pensionz_test` (same Postgres container) built with `alembic upgrade head`;
- `db` fixture rolled back per test; `client` = TestClient with `get_db` overridden; MinIO stubbed;
- factories: `make_user(roles)`, `make_fund(type)`, `make_employer(fund)`, `make_category(...)`,
  `make_member(employer, category)`, `make_portfolio(pricing_method)`, `auth_headers(user)`.
- Run: `docker compose exec backend pytest -q` (`--cov=app` for coverage).
- Tip: call `db.commit()` before code that may `db.rollback()` (job runner), or fixtures vanish.

Layout mirrors the app: `tests/services/test_bonus.py`, `tests/api/test_claims.py`, …

## What must be tested

| Area | Must-have tests |
|---|---|
| Ledger | Every operation balanced **per fund**; Σ member balances = GL 2000; units tie-out |
| Contributions | Schedule totals = cash; rates ≥ statutory minimum; over/under-payment rules; arrears & penalty interest known answers |
| Bonus | Known answers from `pz-pension-domain` (EE 400,000 + ER 800,000 @ 8% → 32,000 / 64,000); interim→final true-up; rerun for same period changes nothing |
| Units | Buy/sell known answers to 6 dp; forward pricing (never a price dated before good funds) |
| Benefits | Lump sum ≤ regulatory max; vesting scale; DB formula; tax from versioned table; quote → payment uses approved quote |
| Reversals | Reversal restores exact prior balances; reversing a reversal is refused |
| Periods | Posting into a closed processing month → 409 |
| Approvals | Initiator can't approve own; double-approve → 409; amount thresholds route to level 2 |
| Access | Wrong role → 403; principal officer on another scheme's member → 403; member on another member → 403; staff outside their funds → 403 |
| Privacy | Employer/member responses never contain other members' data or masked fields unmasked |
| Jobs | Idempotent for same `(job, date, fund)` |
| Data migration | Legacy extract → load → balances per member equal legacy closing balances |

Name tests after the rule: `test_principal_officer_cannot_see_other_scheme_members`.

## Frontend

Vitest + jsdom + React Testing Library (config in `vite.config.ts`, `TZ=Africa/Blantyre`),
tests beside the code; explicit imports from `vitest`; pure logic in `src/utils/` with
known-answer cases for money/unit/date formatting.

## End-to-end

A scripted lifecycle `backend/app/seed_demo_flow.py`: onboard employer (KYC) → add members →
upload & allocate schedule → declare bonus → member exit claim → approve → pay. Run it as the
regression script for big changes.

## Rules

- A bug fix comes with a test that failed before the fix.
- Don't mock the database or ledger — real Postgres.
- Tests don't depend on dev seed data or each other's order.
