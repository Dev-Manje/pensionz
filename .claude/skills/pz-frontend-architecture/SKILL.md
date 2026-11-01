---
name: pz-frontend-architecture
description: Use when making structural frontend decisions in the Pensionz React app — routing/URLs, portals vs staff areas, data fetching and caching, state, the API layer, auth/session handling, file uploads (schedules, KYC documents), error boundaries, code organisation, performance/bundle size. Complements pz-ui-conventions (how screens look) and pz-cross-device (where they run).
---

# Frontend architecture (React 18 + TS + Vite + MUI)

Mirror Money Market's finished patterns (`C:/moneymarket/moneymarket/frontend/src`:
`api/client.ts`, `routes/RoleRouter.tsx`, `hooks/useUrlState.ts`, `queries/`) from the start
instead of migrating later.

## Structure

```
src/
  api/          client.ts (fetch, base URL, tokens, refresh, ApiError) + one file per area
  api/types.ts  DTO types mirroring backend schemas
  queries/      react-query hooks per area: useMember(id), useApproveClaim()...
  routes/
    staff/      funds/, employers/, members/, contributions/, bonus/, claims/, payments/,
                payroll/, accounting/, reports/, approvals/, admin/
    member/     member portal       po/        principal officer portal
    individual/ personal pensions   trustee/   trustee portal
    RoleRouter.tsx  SECTIONS table → sidebar + role guard (one source)
  components/   shared UI (PageHeader, ResponsiveTable, StatusChip, MoneyText, ConfirmDialog,
                FileDropzone, ApprovalPanel, DiffView)
  hooks/ utils/ auth/ theme.ts
```

## Routing (react-router v6)

- URL per screen and entity: `/funds/:fundId`, `/employers/:employerId/:tab?`,
  `/members/:memberId/:tab?`, `/contributions/schedules/:id`, `/claims/:id`,
  `/approvals/:queue`, `/member/<tab>`, `/po/<tab>`.
- Staff work is fund-scoped: a fund switcher in the app bar; selected fund in the URL
  (`?fund=`) so links are shareable.
- Tabs and filters in the URL. Lazy-load each staff area and each portal so portal users never
  download staff code.

## Data fetching

- react-query everywhere from day one; keys like `["member", id]`,
  `["member", id, "transactions", period]`, `["approvals", queue]`.
- Mutations invalidate exactly what they change.
- Batch jobs (bonus run, schedule allocation, payroll) return a batch id → poll
  `["batch", id]` until done; show progress and the exception list.

## API layer

Only `api/client.ts` knows fetch/tokens/refresh; throws `ApiError(status, message)`; screens
show the backend's `detail`. Uploads use `FormData` through the same client.

## State

Server data → react-query · URL state → router · form state → local state / react-hook-form
for big forms (KYC, member application) · snackbar & confirm dialog → small providers.

## Resilience & size

ErrorBoundary per route; global feedback provider. Route files > ~500 lines split into tab
files; check `npx vite build` chunk sizes after big additions.
