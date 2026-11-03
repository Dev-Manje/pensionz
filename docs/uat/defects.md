# UAT defect log — Phases 0–5

One row per problem found in UAT. Severity: **High** (blocks a scenario or wrong money/data), **Medium** (works
with a workaround), **Low** (cosmetic or wording). Status: Open → Fixed (verified) → Re-tested.

| ID | Found | Scenario | Login | Steps | Expected | Actual | Severity | Status | Fix |
|---|---|---|---|---|---|---|---|---|---|
| UAT-001 | 2026-11-03 | Principal officer sign-in | po@pensionz.dev | In a browser where a staff user had been on a staff page (e.g. Contributions) and was signed out, sign in as the principal officer and enter the code | Officer's dashboard (/po) | "You don't have access to this screen." — sign-in returned to the leftover staff page (`/login?next=…`) | Medium (workaround: open /po) | Fixed — awaiting re-test | `App.tsx` + `RoleRouter.canOpen`: after sign-in, a `next` page the roles can't open is replaced by the user's home. vitest 2 new. |
