# Legacy system analysis — PFS (Pension Fund System)

Sources: `Pension Funds.docx`, `PFS.docx` (screenshots, 16 Oct 2026) and
`ipf_member_stat_VOL-1.pdf` (member benefit statement). Written 2026-11-01.

## The system

- **PFS – Pension Fund System** by Independent Technologies (Blantyre). Oracle Forms
  application (`IPF_COM.FMX`), status bar "Connected to: xe" → **Oracle Database XE**.
  The Oracle XE client is installed on this machine (`C:\oraclexe\...` on PATH) — the legacy
  data can likely be extracted directly with SQL for migration (FR-MIG).
- One installation per **company/fund**: e.g. "Press Corporation Group Pension Fund Scheme"
  and company 10 "PCL Group Pension Minors Trust Accounts".
- Main menu: Setup · Payment Processing · Enquiries (Accounts → Comprehensive, Account
  Information, Account Reconcile; Reports) · Administration · Restricted Access · Consolidated
  Reporting · Beneficiaries · Change Password · **RBM Interface** (regulatory returns) ·
  **Web Portal** · Audit Trail · Setup System.

## Ledger conventions

- Each member is a **client account** (e.g. `0000702960`, `0000100005`) with a current balance
  and account status (Active / Inactive / Deceased).
- Transactions: Reference · Transaction (code + name) · Date · Description · Amount · **Shares** ·
  **Price** (unit fields exist but are empty for these declared-bonus funds).
- **Sign convention: credits to the member are negative** (liability stored as credit), so
  member balances display negative (`MK -48,485.49`). Pensionz shows member balances as
  positive amounts owed to the member; migration must flip the sign.
- Transaction codes seen (in addition to 1–6 in `Pension Funds.docx`):

  | Code | Name | Typical reference | Notes |
  |---|---|---|---|
  | 2 | CONTRIBUTIONS RECEIVED | `GENERATED` | One line per member per month: "CONTRIBUTIONS FOR 01-OCT-11 MK…" |
  | 7 | BONUS/EARNINGS EARNED | `IMPORT` | Half-yearly (30/06, 31/12): "CONTRIBUTION EARNINGS FOR 2017/06/30" |
  | 14 | STATEMENT BALANCE | `O/BAL` | Opening balance carried at a period start ("OPENING BALANCE AS AT 01/06/2025") |
  | 68 | COMP-TRANSFERS-S64 | e.g. `PTC70` | Company account supplementary transfer |

  The code list in the legacy DB is the authority — extract the full table during migration.
- Bonus appears to be declared **half-yearly** (June and December).

## Enquiry views (Account Enquiries → "Query On")

Main information · Transactions for current period · Transaction history · Statement · Transaction
trail · Contributions · Voluntary contributions. Each has a printable report:

- **Client Statement** — fund letterhead, statement date, member address, lines (date,
  description, reference, transaction, debit, credit, running balance), **aged analysis**
  (30 / 60 / 90 / 120 / 150 days & over) and current balance, footer "Please do not hesitate to
  contact us if you have any queries".
- **Transaction Trail** — for a date range: date, type, reference, description, debit, credit,
  total; totals per account.
- **Account Contributions Trail** — per period (month): Employee Contribution, Company
  Contribution, Emp. Earning, Comp. Earning, Earning, Earning Rate (%), Total.
- **Account Voluntary Contributions Trail** — per period: Employee Contribution, Total.

## Member Benefit Statement (PDF)

Fund logo + "Member Benefit Statement as at <date>".

- Personal details: Name, Member No, Date of Joining Scheme, Employee No, Date of Birth.
- **Employee account** = Employee Contributions + Bonus on Employee Contributions + Employee
  Voluntary Contributions + Bonus on Employee Voluntary Contributions − Employee Withdrawals.
- **Employer account** = Employer Contributions + **Severance** + Bonus on Employer Account −
  Employer Account Withdrawals.
- Total Benefits for the member (Withdraw/Death) = Employee account + Employer account.
- "Contributions up to: <last contribution month>", "Printed On: <date>".

So member balances must be held by **component**: EE contributions, EE bonus, AVC, AVC bonus,
ER contributions, severance, ER bonus — each with its own withdrawals.

## Handling of the sample documents

They contain real member names and figures — use them only to understand layouts. Never copy
them into seed data, tests or fixtures; seed data uses invented people.
