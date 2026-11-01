---
name: pz-backend-architecture
description: Use when making structural backend decisions in Pensionz — layering, DB transaction/commit ownership, error handling, configuration, logging, audit trail, background jobs and scheduled tasks (bonus runs, unit pricing, contribution due/arrears, pensioner payroll, KYC expiry, statement generation, month-end close), bulk imports, idempotency, or adding infrastructure (worker, queue, cache). Complements pz-backend-feature.
---

# Backend architecture

## Shape (target — mirror Money Market, which already works this way)

- One FastAPI app (`backend/app/main.py`), routers under `api/v1`, sync SQLAlchemy 2.0
  sessions (`core/database.py` → `get_db`), Postgres, MinIO for documents, Mailpit in dev.
- **Worker** (`app/worker.py`, compose service `worker`, same image): polling loop over a
  job registry (`app/jobs/__init__.py`); `jobs/runner.py` claims `(job, as_of_date, fund_id)`
  in `job_run` so each succeeds once, retries failures and catches up missed days.
- Notifications via a transactional `notification_outbox` delivered by the worker.

Ports (chosen so it runs beside Money Market): frontend **5178**, API **8002** (`/api/v1`),
Postgres **5433**, MinIO **9002/9003**, Mailpit **8026** (SMTP 1026), Redis **6380** (if used).

## Layering (strict)

```
api/v1/*.py     HTTP only: auth deps, parse, call service, map to schema
services/*.py   business rules, state transitions, ledger posts, notifications
models/*.py     tables + enums
schemas/*.py    request/response shapes
core/*.py       config, db, security, storage, email, sms — infrastructure adapters
jobs/*.py       scheduled work: run(db, as_of, fund_id=None)
```

- One service function = one business operation = one commit, owned by the service.
- A state change, its ledger post and its outbox row commit **together** or not at all.

## Long-running & bulk operations

Bonus runs, unit-price application, contribution allocation for a 5,000-member employer, payroll
runs and data-migration loads are **batch jobs**, not request handlers:

- Request creates a `batch` row (`pending`) and returns 202 with its id; worker processes it.
- Process in chunks with a commit per chunk **plus** a batch-level status, so a failed run is
  resumable and never half-applied silently: either (a) stage results in a `batch_line` table,
  approve, then post atomically per member, or (b) make every line idempotent by
  `(batch_id, member_id)` unique key.
- Every batch has a preview (dry-run) mode for the checker: totals, member count, exceptions.

## Errors

- Domain violations → `HTTPException(400/403/404/409, detail="<plain English>")`; 409 for
  state conflicts (already approved, period closed).
- Never leak stack traces or SQL; log unexpected errors with context.

## Configuration

All settings in `core/config.py` (pydantic-settings, `.env`). New secrets get a dev-safe
default and a line in `.env.example`. Business parameters (rates, thresholds) are **data**,
not settings — see `pz-scheme-config`.

## Logging & audit

- Structured INFO logging configured in `main.py` from day one.
- Business audit in data: `*_by_user_id`, `*_at` columns and an `audit_event` table (who, what
  entity, before/after JSON, IP) for every change to member, bank, config and money data, and
  every view of sensitive documents.

## Scheduled jobs (planned)

| Job | When |
|---|---|
| `contributions_due` — bill expected schedules, flag arrears, late-payment interest | daily |
| `bonus_run` / `unit_price_apply` | per declared period / per approved price |
| `pensioner_payroll` | monthly, then approval |
| `kyc_expiry_reminders`, `life_certificate_reminders` | daily |
| `retirement_reminders` (NRA − 6 months) | daily |
| `statements` (annual/semi-annual member statements) | per fund schedule |
| `notification_delivery` | every 5s |

Jobs are idempotent and re-runnable for a past date.

## Idempotency & concurrency

- Money-moving POSTs check status inside the transaction and lock rows (`with_for_update()`).
- Use `SELECT ... FOR UPDATE SKIP LOCKED` when several workers could pick the same row.

## Before adding infrastructure

Prefer Postgres-backed solutions (outbox, job_run, batch tables). Celery/RabbitMQ etc. need a
stated reason and a `TASKS.md` entry.
