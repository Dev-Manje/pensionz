---
name: pz-pension-domain
description: Use for any Pensionz work involving pension business rules and their maths — defined contribution (DC) and defined benefit (DB) schemes, umbrella funds, personal pensions, membership lifecycle, contributions, unitisation and unit prices, investment choice and switches, vesting, benefit calculations (retirement, early/ill-health retirement, death, withdrawal, unemployment access, transfers), lump sum vs annuity vs programmed withdrawal, pensioner payroll, actuarial valuations, Malawi Pension Act 2023 and tax on benefits — or when the user asks a pension domain question.
---

# Pension domain knowledge

The system is run by a **pension administrator** (reference client: Old Mutual Pension Services Company —
OMPSC) on behalf of **funds** whose **trustees** own the decisions. Members' money belongs
to the fund, not to the administrator: keep the fund's books and the administrator's own
fee income strictly apart (see `pz-accounting`).

Malawi-specific facts marked *(confirm)* must be checked with the user/compliance before
code depends on them. Every regulatory number is **configuration with an effective date**,
never a constant in code.

## Core structure

```
Fund (registered with the Registrar, has trustees, rules, bank accounts, portfolios)
 ├─ type: standalone employer fund | umbrella (multi-employer) fund | personal pension fund
 ├─ Scheme / Participating employer (umbrella: one per employer; standalone: one)
 │    ├─ Benefit category (e.g. Management, Staff) — contribution rates, salary basis,
 │    │   vesting, insured benefits, DB/DC design, normal retirement age
 │    └─ Member  ── employment, salary history, beneficiaries, KYC
 │         └─ Member account, split by contribution source:
 │              employee, employer, voluntary (AVC), transfer-in — each holds UNITS per portfolio
 └─ Portfolio(s) — unit-priced investment pools (e.g. Balanced, Money Market, Guaranteed)
```

Personal pensions: the individual is both "employer" and member; contributions by debit
order / mobile money / ad hoc; same unit machinery.

## Defined contribution (DC)

- **Contribution** = rate × pensionable salary (per category; employer and employee split),
  or fixed amount. Statutory minimum: **employer 10% + employee 5%** of pensionable
  emoluments *(confirm current figures & salary definition)*.
- Contributions are due monthly by a set day after month end *(confirm deadline — late
  payment attracts penalties/interest under the Act)*; arrears are tracked per employer
  per month.
- **Allocation:** a contribution is invested only when the schedule (who/how much) is
  reconciled to cash received. Units bought = net amount ÷ unit price on the **pricing date
  after cash is good funds** (forward pricing — never buy at a known historical price).
- **Deductions before investing** (configurable): admin fee, group-life / funeral risk
  premiums (insured with OMLAC), levy. Gross → net shown on the member statement.
- **Unit price** = (portfolio net asset value − accrued fees) ÷ units in issue, calculated
  daily or monthly per portfolio, published only after approval. Store to 6 dp; units to
  6 dp; money to 2 dp. Back-dated price corrections need reprocessing of affected
  transactions — design for it.
- **Investment choice:** default portfolio per category; member choice and switches if the
  scheme allows (switch = sell units at price P, buy at price P same date; switch limits /
  fees configurable); **life-stage** automatic de-risking N years before NRA.
- **Declared bonus rate (the legacy system's primary method — build this first).** Trustees
  declare a **bonus/earnings rate (%) per period** per fund (e.g. 2026 H1: 6.5%); the bonus run
  credits each member's **employee and employer** balances (and AVC/transfer-in if configured)
  with `opening balance × rate × time-weighting` plus contributions × rate pro-rated by month
  received *(confirm the time-weighting method: simple pro-rata on monthly balances vs annual
  opening balance only)*. Interim rate for exits mid-period; final rate replaces interim with a
  true-up. Model as `pricing_method = declared_rate`; unit-priced portfolios
  (`pricing_method = unit_price`) remain an option per fund.

## Legacy system vocabulary (PFS — full notes in `docs/legacy/PFS-analysis.md`; migrate faithfully)

- Legacy stores member credits as **negative** amounts; Pensionz shows balances positive.
- Balance **components** (benefit statement): EE contributions, EE bonus, AVC, AVC bonus, ER
  contributions, **severance**, ER bonus — each with its own withdrawals. Bonus is declared
  half-yearly (June/December) and shown per period with its rate on the contributions trail.
- Extra transaction codes: 2 Contributions Received, 7 Bonus/Earnings Earned, 14 Statement
  Balance (opening balance), 68 Company Transfers.

- **Company** = fund/scheme record (Company Code, name, 5 address lines, phone, fax, Tax ID,
  email, website, contact person) with a **Processing Month** — the open period; transactions
  post only into it, month-end closes it.
- **Account types:** Pension Fund, Member Account, Company Account, Reserve Account, Share.
  **Member status:** Active, Inactive, Deceased.
- **Transaction types** are configurable codes with an **effect** (credit/debit): 1 Initial
  Allocation (Cr), 2 Reversal Initial Allocation (Dr), 3 Withdrawal (Dr), 4 Reversal
  Withdrawal (Cr), 5 Bonus Reversal (Dr), 6 Bonus (Cr). Every type has its paired reversal.
- Member keys: Account Code, Old Member No., Employee No., **UPID** and **BI UPID**
  *(confirm meaning — likely regulator-issued unique pension IDs)*; group accounts (Group
  Account Y/N → parent group account).
- Malawi address model: postal district/village, physical address, **home district, home TA
  (traditional authority), home village**, place-of-birth district/village.
- **Minors' trust accounts** (e.g. "PCL Group Pension Minors Trust Accounts"): death benefits
  allocated to minors are held in a trust fund, earn bonuses, and are paid to guardians in
  instalments (school fees, maintenance) or in full at majority.
- Member balances show **ageing buckets** (Current, 30/60/90/120/150 days) brought and
  carried forward *(confirm what is aged — likely contributions receivable/arrears)*.

## Defined benefit (DB)

- Benefit = **accrual rate × pensionable service × final (or average) pensionable salary**,
  e.g. 1/60 × 25 years × MWK 2,400,000 = MWK 1,000,000 p.a. pension.
- Needs full **salary and service history** (breaks, part-time factors), commutation factors
  (lump sum per MWK 1 of pension, by age/sex), early-retirement reduction factors, late
  retirement increases, spouse's/dependant pension %, guaranteed periods, pension increases.
- Employer pays the **balance of cost**; contribution rate set by the actuary at each
  **actuarial valuation** (statutory, typically every 3 years *(confirm)*). The system
  produces valuation data extracts (members, pensioners, deferred, salaries, service) and
  records the actuary's results; it does not replace the actuary.
- Factor tables are versioned, effective-dated data, uploaded and approved — never code.

## Membership lifecycle

join (eligibility: category rules, waiting period, max entry age) → active → (salary
changes, category moves, beneficiary nominations, data corrections) → exit:
**retirement · early retirement · ill-health/incapacity · death in service · withdrawal
(resignation/dismissal/retrenchment) · transfer out** → deferred / paid-up / pensioner →
death of pensioner → spouse/dependant pension or nil.

- **Vesting:** employer portion may vest on a scale by service (scheme rule) subject to
  statutory minimum vesting *(confirm)*; non-vested employer money goes to a forfeiture /
  reserve account per scheme rules.
- **Unemployment access:** a member who has lost employment and not found work for
  **3 months** may access savings *(confirm: 3 vs 6 months, % allowed)*.
- **Pre-retirement access:** within **5 years of retirement** a member may access **up to
  50%** *(confirm)*.
- **Retirement age:** benefits payable between **50 and 70** *(confirm)*; normal retirement
  age per scheme/category.
- **Death:** benefit to nominated beneficiaries/dependants at **trustees' discretion**
  (nominations guide, don't bind) — needs a trustee-decision workflow, minors' share via
  guardian/trust, plus any group-life payout (OMLAC) tracked alongside.
- **Transfers:** in/out between funds (section-to-section, fund-to-fund), with transfer
  value, source fund details, and preserved vesting/service.

## Benefit payment options at retirement

- **Lump sum** up to the statutory maximum — **50% of the benefit** under the 2023 Act
  (40% under 2011) *(confirm)*; balance must buy an **annuity** (OMLAC or another insurer)
  or go into **programmed withdrawal** (in-fund drawdown with min/max annual draw *(confirm)*).
- **Small-balance rule:** if the residual is below a threshold the whole amount may be paid
  as a lump sum *(confirm threshold)*.
- **Programmed withdrawal / in-fund pension:** residual stays invested in units; monthly
  pension = units sold each payroll run; annual review of drawdown rate; life certificate
  (proof of life) required yearly or payments suspend.
- **DB pensions:** fixed MWK amount paid from fund, increased per trustee decision; spouse
  pension on death.

## Tax (confirm with MRA rules before building)

- Contributions: employee contributions to an approved fund are tax-deductible up to a
  limit *(confirm)*.
- Benefits: lump sums and pensions taxed per MRA schedule; certain amounts exempt
  *(confirm)*. The system calculates PAYE on pensions and tax on lump sums from a
  versioned tax table and produces remittance reports and tax certificates.

## Known-answer examples (use in tests)

- Declared bonus (simple annual, opening balance only): EE MWK 400,000 + ER 800,000 at 8.00%
  → bonus EE 32,000.00, ER 64,000.00.
- DC buy: net MWK 150,000 at unit price 12.345678 → 12,150.000996 units (6 dp, round half-up).
- DC sell at retirement: 50,000.000000 units × 15.000000 = MWK 750,000.00; lump sum 50% =
  375,000.00; residual 375,000.00 to annuity/programmed withdrawal.
- DB: 1/60 × 25 × 2,400,000 = 1,000,000.00 p.a. → 83,333.33/month.

## Rules for building

- Effective-dated everything: rates, factors, tax tables, fees, unit prices, salaries.
- A benefit calculation is a stored **quote** (inputs, factors, prices, result) — the
  payment uses the approved quote, never a re-calculation done silently later.
- Two-person rule on every benefit, transfer, data change that affects money, and unit price.
- When a regulatory or scheme-rule point is uncertain, present the standard practice and
  options, ask the user, and record the answer in `TASKS.md` → Open decisions and
  `docs/REQUIREMENTS.md` §10.
