---
name: pz-task
description: Use when the user asks to work on, continue, pick up, or check progress on the Pensionz (pension management system) task list (TASKS.md) — e.g. "next task", "carry on", "what's left", "do Phase 1". Drives the pick → plan → build → verify → tick loop.
---

# Working through TASKS.md

`TASKS.md` in the repo root is the master task list (created from `docs/REQUIREMENTS.md`
during planning). Every task should cite the requirement IDs it delivers (`FR-CON-004`).
Work it like this:

1. **Read `TASKS.md`.** Check "Open decisions" first — if the chosen task depends on an
   unanswered decision (or an *open question* in `docs/REQUIREMENTS.md` §10), ask the user
   (AskUserQuestion) before building anything.
2. **Pick the task.** The user's choice if they named one; otherwise the first unticked item
   in the lowest-numbered phase. State which one you're taking and the FR IDs it covers.
   **Gates:** a checkpoint section (e.g. "UAT checkpoint" before Phase 6) counts as part of the order; never start a
   phase that sits behind an unticked sign-off item — finish the checkpoint or ask the user.
3. **Load the matching skill(s)** before writing code:
   - pension rules, benefits, unitisation, DB formulas, Malawi Pension Act → `pz-pension-domain`
   - fund/scheme/category/portfolio/fee setup → `pz-scheme-config` + `pz-pension-domain`
   - anything touching the ledger, GL, contributions receivable, unit accounting, fees, tax,
     reconciliation, trustee/financial reports → `pz-accounting`
   - contribution receipts, benefit payouts, pensioner payroll, bank details, bank
     reconciliation, debit orders, mobile money → `pz-banking`
   - onboarding, KYC/CDD, PEPs, documents, AML, sanctions, data protection → `pz-kyc-compliance`
   - anything a member, employer or individual does in a portal → `pz-portal-self-service`
   - endpoints, models, migrations, approvals → `pz-backend-feature`
   - workers, scheduled jobs (unit pricing, contribution due dates, pensioner payroll),
     transactions, logging, new infra → `pz-backend-architecture`
   - emails, SMS, in-app notifications, statements, reminders → `pz-notifications`
   - routing, data fetching, file structure → `pz-frontend-architecture`
   - any screen, dialog, table or form → `pz-ui-conventions` + `pz-cross-device`
   - always → `pz-testing` (tests for money, units, benefits, approvals, access) and `pz-verify`
4. **Build** the smallest complete slice (backend + UI + seed if useful). Larger items may be
   split into sub-bullets in `TASKS.md` first.
5. **Verify** with `pz-verify` (migrations, tsc, curl incl. negative access case,
   desktop + 390px screenshots that you actually look at).
6. **Update `TASKS.md`:** tick `[x]` only verified items, with a short note/date
   (`— done 2026-11-14, see routes/staff/members/MemberDetail.tsx`). Record new gaps as new
   unticked items in the right phase. Record answered decisions under "Open decisions" and
   mirror them into `docs/REQUIREMENTS.md` (move the question to "Resolved").
7. **Update** the as-built doc (`docs/design/implementation-status.md`) if behaviour changed.
8. **Report** to the user: what was done, how it was verified, what's next. Commit only if
   the user asks.

Never tick an item that was built but not verified — leave it unticked with a note saying
what's left.
