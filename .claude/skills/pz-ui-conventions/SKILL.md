---
name: pz-ui-conventions
description: Use when building or changing any React screen, dialog, table or form in the Pensionz frontend (frontend/src) — staff back office, member, employer, individual or trustee portals. Lists the theme, shared components, layout and UX states every screen must follow.
---

# Pensionz frontend UI/UX conventions

Stack: React 18 + TypeScript + Vite + MUI. Theme in `frontend/src/theme.ts`; product name and colours
come from `frontend/src/brand.ts`. Pensionz is independently branded — never hard-code a client's
name, logo or colours (Old Mutual/PCL documents are reference material only). Also apply the general `frontend-ui-ux`
skill; this file is the project layer. Reuse Money Market's component designs
(`C:/moneymarket/moneymarket/frontend/src/components`) — copy, don't import across repos.

## Reuse before adding

| Need | Use |
|---|---|
| Page title + intro + primary action | `components/PageHeader.tsx` |
| Loading / error / empty table rows | `components/LoadingState.tsx`, `TableStateRow.tsx` |
| Tables (stack into cards on phones) | `components/ResponsiveTable.tsx` |
| Row actions | `components/RowActions.tsx` |
| Status chips / labels | `components/StatusChip.tsx`, `utils/labels.ts` |
| Money, units, prices, rates | `utils/format.ts` (`formatMoney`, `formatUnits`, `formatPrice`, `formatRate`) |
| Dates / periods | `utils/date.ts` (`formatDate`, `formatPeriod` → "Oct 2026") |
| Approve/reject with reason + maker/checker info | `components/ApprovalPanel.tsx` |
| Before/after of a change request | `components/DiffView.tsx` |
| File uploads (KYC docs, schedules) | `components/FileDropzone.tsx` (type, size, preview) |
| Success messages | `useFeedback().success(...)` |

No hex literals in components — theme tokens only.

## Every screen must have

- **Four states**: loading, empty (what will appear + how to create it), error (API `detail`),
  populated.
- **Feedback after actions**: success message, busy-disabled button, list refreshes.
- **Money** right-aligned, tabular numerals, `MWK 1,250,000.00`. Units `12,150.000996`,
  prices `12.345678`, rates `8.00%`.
- **Status chips** with human labels (`pending_checker` → "Awaiting approval").
- **Confirmation** for anything irreversible or money-moving, restating amounts and member count.
- **Forms**: labels, helper text, inline validation, required marking. Long forms (KYC, member
  application) are **steppers** with save-draft, mirroring the legacy tabs (Main, Member,
  Company, KYC, Regulatory) but grouped by what the user is doing.
- **Batch screens** (schedules, bonus run, payroll): summary totals, exception list with
  per-row reasons, download of exceptions, then submit.

## Layout

- Staff back office: dense, keyboard-friendly, 1366–1920px, fund switcher always visible.
- Member/individual portals: phone-first (390px), touch targets ≥ 44px.
- Principal officer portal: laptop-first, works on tablet.
- No developer copy, raw enum values or role ids reaching users.

Verify visually with `pz-verify` — tsc passing is not evidence a screen looks right.
