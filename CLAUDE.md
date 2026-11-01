# Pensionz — pension management system

Independent pension administration product: DC employer & umbrella funds, personal pensions, DB
schemes and minors' trust accounts, replacing legacy desktop systems such as PFS. Old Mutual
Malawi and PCL material in the repo root is **reference only** — don't brand the product with it;
branding lives in `frontend/src/brand.ts` + `BRAND_*` backend settings (decided 2026-11-01).
Stack (same as `C:/moneymarket/moneymarket`): FastAPI + SQLAlchemy 2.0 + Alembic + Postgres
(`backend/app`), React + TypeScript + Vite + MUI (`frontend/src`), MinIO, Docker Compose
(frontend :5178, API :8002/api/v1, Mailpit :8026).

## How we work

- **`docs/REQUIREMENTS.md`** is the requirements spec (stable FR-/NFR- IDs). §10 lists open
  questions — ask the user before building anything that depends on one.
- **Source documents** in the repo root: `kyc Requirements.docx` (KYC forms) and
  `Pension Funds.docx` (legacy system screens + scope notes).
- **`TASKS.md`** (created during planning) is the master task list; the `pz-task` skill drives
  pick → build → verify → tick and loads the other `pz-*` skills in `.claude/skills/`.
- Tick a task only after verifying it with `pz-verify` (including looking at screenshots).
- Regulatory figures are effective-dated configuration, never constants.
