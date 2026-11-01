---
name: pz-accounting
description: Use for any Pensionz work touching the books — fund ledgers, chart of accounts, contributions receivable and unallocated receipts, unit/member liability accounting, investment income and unit pricing NAV, benefits payable, fees (fund vs administrator), tax payable (PAYE on pensions, lump-sum tax), reconciliation, period-end, trustee financial statements and regulatory returns — or when the user asks an accounting question about the platform.
---

# Accounting knowledge for Pensionz

Two sets of books, never mixed:

- **Each fund** has its own ledger (`ledger_entry.fund_id` is mandatory). Fund assets are held
  for members; member account balances are the fund's main liability (DC) or are covered by
  the actuarial liability (DB).
- **The administrator (OMPSC)** earns admin fees from funds/employers; its income lives in an
  administrator ledger (`fund_id = NULL`, `book = administrator`). Fund money never pays
  administrator costs.

## Non-negotiable rules

1. **Double entry, always balanced, per fund.** Use `ledger.post(db, fund_id, entity_type,
   entity_id, lines)`; it raises if Σdr ≠ Σcr **within that fund**. Cross-fund movement (a
   transfer between two OM funds) is two posts, one in each fund, via a clearing account.
2. Assets/expenses increase with debits; liabilities/equity/income with credits.
3. **Immutable books** — corrections by reversal + new entry, both referencing the original.
4. **Every post references its business event** (contribution batch, unit deal, claim,
   payroll run, fee run, price correction).
5. Money `Numeric(18,2)` round half-up per line; units `Numeric(20,6)`; prices `Numeric(18,6)`.
   Totals come from rounded lines.
6. Member unit holdings × approved price = member value; Σ member units per portfolio =
   portfolio units in issue (sub-ledger tie-out, checked daily).

## Proposed fund chart of accounts — **confirm with finance before building**

| Code | Name | Class |
|---|---|---|
| 1000 | Fund Bank — Contributions Collection | asset |
| 1010 | Fund Bank — Benefits Payment | asset |
| 1100 | Investments at Fair Value (per portfolio sub-account) | asset |
| 1200 | Contributions Receivable (billed, not yet received) | asset |
| 1300 | Investment Income Receivable | asset |
| 2000 | Member Fund Credits (DC, per portfolio) | liability |
| 2100 | Unallocated Contributions (cash received, schedule not reconciled) | liability |
| 2200 | Benefits Payable (approved claims not yet paid) | liability |
| 2300 | PAYE / Benefit Tax Payable (MRA) | liability |
| 2400 | Risk Premiums Payable (OMLAC group life/funeral) | liability |
| 2500 | Administration Fees Payable (to administrator) | liability |
| 2600 | Forfeiture / Reserve Account (non-vested employer money) | liability |
| 2700 | Pensioners Payable (programmed withdrawal / in-fund pensions) | liability |
| 3000 | DB Fund Reserve / Surplus | equity |
| 4000 | Contributions Income (DB funds) | income |
| 4100 | Investment Income | income |
| 4200 | Fair Value Gains/Losses | income |
| 4300 | Late-Payment Interest from Employers | income |
| 5000 | Benefits Paid (DB funds) | expense |
| 5100 | Administration Fees | expense |
| 5200 | Investment Management Fees | expense |
| 5300 | Statutory Levies | expense |

Administrator book: 1500 Fees Receivable from Funds, 1510 Administrator Operating Bank,
4500 Administration Fee Income.

## Proposed posting recipes (DC) — confirm

| Event | Debit | Credit |
|---|---|---|
| Employer schedule billed | 1200 | 2100 |
| Cash received from employer | 1000 | 1200 |
| Schedule reconciled & allocated (net of fees/premiums) | 2100 gross | 2000 net (per member/portfolio), 2500 admin fee, 2400 risk premium |
| Cash invested with asset manager | 1100 | 1000 |
| Investment income / fair value change (portfolio) | 1100 / 1300 | 4100 / 4200 → reflected in unit price, closed to 2000 via price |
| Unit price movement (period) | 4100/4200 | 2000 (member credits revalue) |
| Declared bonus credited (declared-rate funds) | 2600/3000 fund reserve (investment return accumulates there) | 2000 per member, split EE/ER |
| Bonus reversal / interim→final true-up | 2000 | reserve (or the reverse) |
| Switch between portfolios | 2000 (portfolio A) | 2000 (portfolio B) — plus 1100 sub-accounts if assets move |
| Claim approved (units sold) | 2000 | 2200 gross |
| Lump-sum tax withheld | 2200 | 2300 |
| Claim paid | 2200 net | 1010 |
| Annuity purchase | 2200 | 1010 (paid to insurer) |
| Programmed-withdrawal monthly payment | 2700 / 2000 units sold | 1010 net, 2300 PAYE |
| Non-vested employer portion on withdrawal | 2000 | 2600 |
| Admin fee settled to administrator | 2500 | 1000 (fund) · and admin book: 1510 / 4500 |
| Late-payment interest charged to employer | 1200 | 4300 |

DB funds: contributions Dr 1000 / Cr 4000; benefits Dr 5000 / Cr 1010; no member credits —
liabilities come from the actuarial valuation, recorded as disclosure.

## Reconciliation & controls

- Trial balance per fund; Σ member values per portfolio = GL 2000 sub-account; units tie-out.
- GL 1100 per portfolio = asset manager / custodian statement (monthly).
- Contributions: billed vs received vs allocated per employer per month; ageing of 1200
  (arrears) and 2100 (unallocated) — both must trend to zero.
- Bank reconciliation of 1000/1010 vs bank statements (see `pz-banking`).
- Period close per fund: no postings in a closed month; prior-period price corrections go into
  the open period with reference.

## Reports the books must support

Trustee financial statements (statement of net assets, changes in net assets), member
statements, contribution arrears reports, regulatory returns to the Registrar/RBM *(confirm
formats)*, MRA PAYE remittance, fee invoices to employers.

## When unsure

Treatment that changes member values, fees or tax is a business decision — state the
proposed journal entries and ask the user/finance before building.
