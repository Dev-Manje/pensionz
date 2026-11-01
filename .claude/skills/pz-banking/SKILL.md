---
name: pz-banking
description: Use for any Pensionz work touching money moving through banks — employer contribution receipts and payment references, personal-pension debit orders and mobile-money collections, benefit and pensioner payroll payments (EFT/RTGS/mobile money), payee bank-detail verification and fraud controls, fund collection/payment bank accounts, bank-statement import and reconciliation, value dates and cut-offs, payment files to banks, returned payments, and Malawi banking/AML regulation — or when the user asks a banking question.
---

# Banking & payments for Pensionz

Each **fund** has its own bank accounts (collections, payments) at a commercial bank; the
administrator has its own operating account. Malawi-specific facts marked *(confirm)*.

## Money in — contributions

| Source | Rail | Matching key |
|---|---|---|
| Employer monthly contributions | EFT / RTGS / cheque | **Employer scheme code** in the payment reference |
| Personal pension | Debit order *(confirm bank support)*, Airtel Money / TNM Mpamba, EFT | Member/policy number |
| Transfers in from another fund | EFT/RTGS | Transfer request reference |

- **Value date** (good funds in the fund's account) drives unit purchase date — not capture date.
  Cheques aren't good funds until cleared.
- Unidentified receipts → **Unallocated (GL 2100)** suspense with an ageing report; never
  guessed onto a member.
- Employer pays one amount; the **schedule** (member-level split) must reconcile to it:
  over/under-payment handled by configurable rules (hold, refund, carry forward, bill arrears).
- Late payment → arrears + penalty interest per the Act *(confirm rate)* + escalation to the
  employer, and eventually report to the Registrar.

## Money out — benefits & pensioner payroll

- Payments only to **verified bank/mobile-money details of the payee** (member, beneficiary,
  guardian, receiving fund, insurer). Never to details typed into the claim form without
  verification.
- Payment batches: approved claims → payment batch → second approval → bank file (bank's CSV
  format / host-to-host *(confirm bank)*) → bank confirmation → mark paid. One approved
  payment ⇒ at most one bank payment (idempotency key per payment line).
- **Pensioner payroll** (programmed withdrawal, DB pensions): monthly run on a schedule —
  calculate gross, PAYE, deductions, net; suspend for missing life certificate or death; payslip
  per pensioner; payroll approval before release.
- Cut-off times: instruct before the bank's same-day cut-off; business-day calendar for
  Malawi public holidays (configurable).
- Returns (wrong/closed account) → reversal entry, payment back to Benefits Payable, payee
  contacted, details re-verified before re-sending.

## Bank details — the main fraud risk

- Changing payee bank details = maker-checker with documentary evidence (bank letter /
  statement), **notification to the old contact details**, and a configurable cooling-off before
  any payment to new details.
- Account name must match the payee; third-party payments only for documented cases
  (guardian of a minor, estate, receiving fund, insurer).
- Mask account numbers everywhere except to finance users with need.

## Reconciliation

- Import bank statements (CSV/MT940 *(confirm bank formats)*), auto-match by amount + date +
  reference, manual match screen, unmatched both ways listed and aged.
- Daily cash position per fund account; monthly sign-off.

## Rules for building

- No money leaves a fund account without an approved, audited instruction to a verified
  destination.
- Store value dates explicitly; use the business-day calendar.
- When bank formats, cut-offs or limits are unknown, ask the user and record under
  "Open decisions".
