# Pensionz — System Requirements

| | |
|---|---|
| **Document** | System requirements specification (draft for review) |
| **Version** | 0.1 — 2026-11-01 |
| **Client** | Old Mutual Malawi — pension administration (OMPSC) |
| **Sources** | `kyc Requirements.docx` (KYC forms), `Pension Funds.docx` + `PFS.docx` (legacy PFS screens, analysed in `docs/legacy/PFS-analysis.md`), `ipf_member_stat_VOL-1.pdf` (member benefit statement), Malawi Pension Act No. 6 of 2023 (public summaries), sibling Money Market platform (stack & conventions) |
| **Status** | Requirements only — planning (`TASKS.md`, phases) follows once §10 open questions are answered |

Items marked *(confirm)* are assumptions or regulatory figures that need sign-off from the
business, compliance or finance before they are built.

---

## 1. Purpose and scope

Build a web-based **pension management system** that replaces the current desktop pension
administration system (legacy screens in `Pension Funds.docx`) and adds client self-service.
It must administer:

| Business line | Description |
|---|---|
| **Group / employer DC schemes** | Standalone defined-contribution funds for single employers |
| **Umbrella fund** | One multi-employer DC fund with many participating employers |
| **Individual personal pensions** | Voluntary individual retirement savings accounts |
| **Defined benefit (DB) schemes** | Formula-based schemes with actuarial valuation support |
| **Minors' trust accounts** | Death benefits held in trust for minor beneficiaries (legacy "Group Pension Minors Trust Accounts") |

Covered end-to-end: onboarding & KYC → fund/scheme setup → membership → contributions →
investment earnings (declared bonus and/or unit pricing) → benefits & claims → payments &
pensioner payroll → fund accounting → enquiries, statements & reporting → portals.

**Out of scope** (unless §10 decides otherwise): asset management / trading of fund investments,
the insurer's group-life underwriting system (OMLAC), the actuary's valuation modelling,
general ledger of Old Mutual as a company (we produce fund books and an administrator fee
ledger, and export journals).

## 2. Context

- **Administrator:** Old Mutual Pension Services Company (OMPSC) administers funds on behalf of
  **trustees**. Fund money is held for members and kept separate from administrator income.
- **Regulator:** Registrar of Financial Institutions (Reserve Bank of Malawi) under the
  **Pension Act 2023** and Financial Services Act. Tax: Malawi Revenue Authority (MRA).
  AML: Financial Intelligence Authority (FIA).
- **Key 2023 Act parameters** *(all to be confirmed and held as effective-dated configuration)*:
  minimum contributions employer 10% / employee 5%; retirement age 50–70; maximum retirement lump
  sum 50% (was 40%) with the balance to annuity or programmed withdrawal; access after
  3 months' unemployment; access to up to 50% within 5 years of retirement.
- **Group context:** the KYC form is shared across Old Mutual Malawi businesses (MPICO, OMIG,
  OMUT, OMPSC, OMLAC); clients may hold several products.
- **Technology** (decided 2026-11-01): same as the Money Market platform — FastAPI +
  SQLAlchemy 2.0 + Alembic + Postgres backend, React + TypeScript + Vite + MUI frontend,
  MinIO for documents, Docker Compose. Dev ports: frontend 5178, API 8002.

## 3. Users and roles

| Role | Who | Main activities |
|---|---|---|
| `admin` | System administrator | Users, roles, system parameters, reference data |
| `scheme_config_maker` / `scheme_config_checker` | Scheme setup team | Funds, employers, categories, rates, fees, transaction types |
| `member_admin` / `member_checker` | Member administration | Member capture, changes, beneficiaries, exits |
| `contributions_officer` / `contributions_checker` | Contributions team | Schedules, receipts, allocation, arrears, reversals |
| `benefits_officer` / `benefits_checker` / `benefits_approver_l2` | Claims team | Benefit quotes, claims, death-benefit cases |
| `finance` / `finance_checker` | Fund accounting | Bonus runs, unit prices, payments, bank recon, period close, GL |
| `payroll_officer` | Pensioner payroll | Monthly pension runs, life certificates |
| `compliance` | Compliance / AML | KYC review, PEP/EDD, screening, STRs |
| `relationship_manager` | Client service | Employer relationships, enquiries |
| `auditor` | Internal/external audit | Read-only everything, audit trail |
| `trustee` | Fund trustees | Read-only fund reports; record trustee decisions |
| `principal_officer` | Scheme/fund **principal officer** — the employer's officer who remits contributions (legacy company "Contact Person") | Principal officer portal |
| `member` | Members, deferred members, pensioners | Member portal |
| `individual` | Personal pension holders | Individual portal |

Staff access is additionally **scoped to the funds they administer**.

## 4. Functional requirements

Priority: **M** must (go-live / legacy parity) · **S** should · **C** could (later phase).
IDs are stable; tasks in `TASKS.md` reference them.

### 4.1 ONB — Client onboarding & KYC (source: `kyc Requirements.docx`)

**Common**

| ID | Requirement | Pri |
|---|---|---|
| FR-ONB-001 | First question: client type **Corporate** (formally registered: plc, private ltd, NGO, trust, sole trader) or **Group** (unregistered collective: village bank, family group, club, association); individuals onboard through the individual form. | M |
| FR-ONB-002 | Organisation/group name typed in full; the system must **never** show a list of existing clients to applicants (privacy). Duplicate matching happens on the staff side. | M |
| FR-ONB-003 | Product/scheme multi-select (optional): MPICO Property; OMIG Private Wealth, Money Market, Segregated Funds; OMUT Interest Bearing Asset Fund, Balanced Fund; **OMPSC Group/Employer Pension**; OMLAC Group Life Assurance, Group Funeral. | M |
| FR-ONB-004 | Scheme / investment / policy numbers: optional, multiple entries. | M |
| FR-ONB-005 | Every document requirement has an upload control, document type, issue date and (where relevant) expiry date; every pick-list includes "Other (type it)". | M |
| FR-ONB-006 | Declaration text shown verbatim (true and correct; misrepresentation; keep Old Mutual informed of changes; consent to share within Old Mutual Malawi business units; confidentiality notice) with stored acceptance (who, when, IP, declaration version). | M |
| FR-ONB-007 | Applications can be saved as draft and resumed; submitted applications go to a compliance review queue. | M |
| FR-ONB-008 | Staff can capture an application on a client's behalf (paper forms) with the same validation. | M |

**Corporate** (all mandatory unless stated)

| ID | Requirement | Pri |
|---|---|---|
| FR-ONB-C01 | Identification document: business registration certificate / incorporation certificate / Act of Parliament / other — with upload. | M |
| FR-ONB-C02 | Office phone, email, postal or physical address (three fields). | M |
| FR-ONB-C03 | Contact person/representative: name, phone, email. | M |
| FR-ONB-C04 | Proof of physical address: landline telephone bill / utility bill ≤ 3 months / lease or sale agreement / city rates ≤ 12 months / other. | M |
| FR-ONB-C05 | One supporting document: articles of association / constitution / partnership agreement / MoU or board resolution / other. | M |
| FR-ONB-C06 | IDs of directors and senior management (repeatable); foreign nationals: passport, plus immigration permit if resident in Malawi. | M |
| FR-ONB-C07 | Source of funds: bank statements (≥ 3 months) / latest audited financials / income tax returns. | M |
| FR-ONB-C08 | Proof of bank account: bank statement / bank confirmation letter / deposit slip / cancelled cheque / MO626 or other transfer slip. | M |
| FR-ONB-C09 | Entity PEP declaration (Yes/No) with the definition of a politically exposed entity shown. | M |

**Group**

| ID | Requirement | Pri |
|---|---|---|
| FR-ONB-G01 | Founding document: constitution / minutes / other — with upload. | M |
| FR-ONB-G02 | Source of funds and proof of bank account (same options as corporate). | M |
| FR-ONB-G03 | Signatories, **unlimited** (add button): full name, address, phone, email, occupation, PEP Yes/No (PEP definition shown). | M |
| FR-ONB-G04 | ID for every signatory (passport + immigration permit for resident foreign nationals) and proof of physical address for every signatory. | M |
| FR-ONB-G05 | Group declaration (as FR-ONB-006, worded for groups). | M |

**Individual**

| ID | Requirement | Pri |
|---|---|---|
| FR-ONB-I01 | Names: first, last, middle (optional), maiden name, other names. | M |
| FR-ONB-I02 | Policy/member numbers, multiple (comma-separated input accepted). | M |
| FR-ONB-I03 | Gender; marital status (single, married, divorced, widow/er); civil status on entry and current. | M |
| FR-ONB-I04 | Physical address description; postal address; Malawi locality: district, traditional authority (TA), village; place-of-birth district/village. | M |
| FR-ONB-I05 | Proof of address type (water bill, electricity bill, city rates, lease agreement) + upload. | M |
| FR-ONB-I06 | ID type (national ID, passport, driver's licence), ID number, date of birth, ID expiry date + upload. | M |
| FR-ONB-I07 | Country of residence and nationality (ISO country lists). | M |
| FR-ONB-I08 | Foreign nationals: immigration permit type (employment, study, temporary residence, business residence, permanent residence, diplomatic, technical assistance) and expiry date. | M |
| FR-ONB-I09 | Source of income: employment (employer name, start date, monthly net income) or business (type, physical address, registration number if registered, monthly income); other income (specify); source of funds. | M |
| FR-ONB-I10 | Next of kin / related person: name, relationship (pick-list), occupation, cell number, email *(confirm the purpose of source-doc items 28–32)*. | M |
| FR-ONB-I11 | Contact: telephone, mobile, email; preferred mode of communication (phone call, SMS, email, post). | M |
| FR-ONB-I12 | PEP self-declaration and related-to-PEP declaration (Yes/No each). | M |
| FR-ONB-I13 | Terms agreement (stored as FR-ONB-006). | M |

**Due diligence**

| ID | Requirement | Pri |
|---|---|---|
| FR-ONB-101 | Compliance reviews each document (accept / reject with reason); rejection notifies the applicant to re-upload. Capturer ≠ approver. | M |
| FR-ONB-102 | Sanctions/PEP screening of the client, directors, signatories and beneficial owners; results stored *(confirm list/provider)*. | S |
| FR-ONB-103 | Rule-based risk rating (low/medium/high); PEP or high risk ⇒ enhanced due diligence and senior approval. | M |
| FR-ONB-104 | Periodic KYC review dates by risk rating; reminders before ID/permit/proof expiry. | S |
| FR-ONB-105 | Approved corporate clients become **employers / participating employers**; approved individuals become members or personal-pension holders. | M |

### 4.2 CFG — Fund, scheme and system setup

| ID | Requirement | Pri |
|---|---|---|
| FR-CFG-001 | **Fund/company record** (legacy "Company Setup"): company code, name, address lines 1–5, phone, fax, tax ID (TPIN), email, website, contact person (full name, email, phone, alternative phone), registration number with the Registrar, fund type (standalone DC, umbrella DC, personal pension, DB, minors' trust), trustees, bank accounts. | M |
| FR-CFG-002 | **Processing month** per fund: one open period; transactions post only into it; month-end close with checks; re-open requires approval. | M |
| FR-CFG-003 | Participating employers (umbrella funds) with their own contribution day, billing and contact details. | M |
| FR-CFG-004 | **Benefit categories** per scheme: DC/DB design, employee & employer rates (% or fixed), pensionable salary definition, normal retirement age, eligibility/waiting period, vesting scale, default investment option, insured benefits, member choice allowed. | M |
| FR-CFG-005 | **Account types** (legacy): Pension Fund, Member Account, Company Account, Reserve Account, Share — configurable list with ledger behaviour. | M |
| FR-CFG-006 | **Transaction types** (legacy, configurable): code, description, effect (credit/debit), paired reversal type, GL mapping. Seed: 1 Initial Allocation (Cr), 2 Reversal Initial Allocation (Dr), 3 Withdrawal (Dr), 4 Reversal Withdrawal (Cr), 5 Bonus Reversal (Dr), 6 Bonus (Cr). | M |
| FR-CFG-007 | Investment options per fund: **declared-rate** (bonus) pools and/or **unit-priced** portfolios. | M |
| FR-CFG-008 | Fee rules: admin fee (% of contributions, % of assets, flat per member), who pays (fund/employer/member), frequency. | M |
| FR-CFG-009 | Regulatory & tax parameters, effective-dated: minimum contribution rates, lump-sum maximum, retirement age band, access rules, tax tables, late-payment interest rate. | M |
| FR-CFG-010 | Reference data: banks & branches, districts, TAs, villages, countries, nationalities, relationships, salutations, ID types, permit types. | M |
| FR-CFG-011 | Every configuration change is maker-checker with a diff view and an effective date. | M |
| FR-CFG-012 | DB factor tables (commutation, early-retirement reduction, late-retirement increase) uploaded as versioned tables. | C |

### 4.3 MEM — Membership administration

| ID | Requirement | Pri |
|---|---|---|
| FR-MEM-001 | **Member record** (legacy "Account Setup"): account code, names (first, other, maiden, last), nationality, ID type & number, old member no., employee no., group account Y/N + linked group account, postal & physical addresses, postal district/village, home district/TA/village, bank name/branch/account no., contact, telephone, mobile, fax, email, next of kin (name, telephone, email, relation). | M |
| FR-MEM-002 | Member information: date of birth, date joined, exit date, gender, account type, account status, **UPID**, **BI UPID** *(confirm meaning)*, nationality code, salutation, civil status (foreign, on entry, current), place of birth district/village. | M |
| FR-MEM-003 | Company info per member: owner name, corporate form, TPIN, fund name. | M |
| FR-MEM-004 | KYC tabs per member (individual KYC fields from 4.1) and **Regulatory Authority Data** (fields for regulator returns *(confirm field list)*). | M |
| FR-MEM-005 | Member status: **Active, Inactive, Deceased** — extended with Deferred/Paid-up, Pensioner, Exited *(confirm)*; status changes are audited and drive what transactions are allowed. | M |
| FR-MEM-006 | **Bulk onboarding** via a downloadable Excel template (to be designed) including KYC fields and an account-code column; row-level validation report; only valid rows import; import is maker-checker. | M |
| FR-MEM-007 | New member application form (online, and printable PDF for paper capture). | M |
| FR-MEM-008 | **Beneficiaries**: multiple nominees with name, relationship, DOB, ID, contact, percentage share (must total 100%), guardian for minors; nomination history kept. | M |
| FR-MEM-009 | Salary history (effective-dated) and service history (for DB and salary-based contributions). | M |
| FR-MEM-010 | Category moves, employer transfers within an umbrella fund, data corrections — all maker-checker with audit. | M |
| FR-MEM-011 | Duplicate detection (ID number, name + DOB) across funds. | S |
| FR-MEM-012 | Member balances shown with **ageing buckets** (brought forward and carried forward: current, 30, 60, 90, 120, 150 days) *(confirm what is aged)*. | M |

### 4.4 CON — Contributions

| ID | Requirement | Pri |
|---|---|---|
| FR-CON-001 | Contribution components: **employee, employer, voluntary (AVC), severance, transfer-in**; fund-level contributions where applicable. Balances are held per component, each with its own bonus and withdrawals (legacy benefit statement). | M |
| FR-CON-002 | Expected monthly schedule per employer generated from active members, salaries and category rates. | S |
| FR-CON-003 | Employer **schedule upload** (Excel/CSV template) and manual capture; validation per row (member exists, rate ≥ statutory minimum, totals). | M |
| FR-CON-004 | **Receipts**: record money received (bank, date, value date, amount, reference, payer); unidentified money held in unallocated suspense. | M |
| FR-CON-005 | Reconcile schedule to receipt; **allocate** to members (legacy "Initial Allocation") net of fees/risk premiums, posting member transactions and ledger entries. | M |
| FR-CON-006 | Over/under-payment handling rules (hold, refund, carry forward, bill arrears). | M |
| FR-CON-007 | **Reversals** of allocations (legacy "Reversal Initial Allocation"), referencing the original, maker-checker. | M |
| FR-CON-008 | Arrears tracking per employer per month, late-payment interest *(confirm rate)*, reminders and escalation; report of non-compliant employers for the Registrar. | S |
| FR-CON-009 | Personal pensions: contribution plans (amount, frequency), payment by debit order / mobile money / EFT, premium holidays. | S |
| FR-CON-010 | Contributions receipt document / acknowledgement to employers. | M |

### 4.5 EAR — Investment earnings (bonus & unit pricing)

| ID | Requirement | Pri |
|---|---|---|
| FR-EAR-001 | **Configure bonus rate** per fund: period (from–to), rate %, interim/final flag, applying to **both employee and employer** balances (and AVC/transfer-in where configured). | M |
| FR-EAR-002 | Bonus run: preview (member count, totals, exceptions) → approve → post Bonus transactions and ledger entries. | M |
| FR-EAR-003 | Bonus calculation method configurable *(confirm: opening balance × rate, plus contributions pro-rated by month received)*; interim rate for exits mid-period with final true-up. | M |
| FR-EAR-004 | **Bonus reversal** (legacy type 5) for a whole run or individual members, maker-checker. | M |
| FR-EAR-005 | Unit-priced portfolios: daily/monthly unit prices (6 dp) approved before use; forward pricing for buys and sells; price corrections with reprocessing. | S |
| FR-EAR-006 | Member investment choice, switches (limits/fees configurable) and life-stage de-risking for unit-priced funds. | C |

### 4.6 BEN — Benefits & claims

| ID | Requirement | Pri |
|---|---|---|
| FR-BEN-001 | Claim types: normal, early, late and ill-health retirement; death in service; withdrawal (resignation, dismissal, retrenchment); unemployment access *(confirm 3-month rule)*; pre-retirement partial access *(confirm 50% within 5 years)*; transfer out; minors' trust payouts. | M |
| FR-BEN-002 | Claim intake by staff, employer (exit notification) or member portal; document checklist per claim type; KYC must be current. | M |
| FR-BEN-003 | **Benefit quote**: balances by component, vesting of employer portion, interim bonus, lump-sum / residual split under the regulatory maximum, tax, fees; stored with all inputs; quote expiry. | M |
| FR-BEN-004 | Member/beneficiary election: lump sum + annuity (insurer named) or programmed withdrawal; small-balance full commutation *(confirm threshold)*. | M |
| FR-BEN-005 | Approval workflow with amount-based levels (officer → checker → level-2 approver). | M |
| FR-BEN-006 | **Death claims**: trustee decision workflow allocating among dependants/nominees (nominations advisory); minors' shares transferred to the **minors' trust fund** as individual trust accounts. | M |
| FR-BEN-007 | Non-vested employer money to the reserve/forfeiture account. | M |
| FR-BEN-008 | Withdrawal transaction (legacy type 3) and its reversal (type 4). | M |
| FR-BEN-009 | DB benefit calculation from salary/service and factor tables. | C |
| FR-BEN-010 | Tax on lump sums from the versioned MRA table; tax certificate. | M |

### 4.7 PAY — Payments & pensioner payroll

| ID | Requirement | Pri |
|---|---|---|
| FR-PAY-001 | **Payment entry** (legacy): bank, cheque/payment number, date, payee, amount, transaction type, with **allocations across several clients/members** (date, client, description, amount); allocations must equal the payment. | M |
| FR-PAY-002 | **Payment voucher** (PDF) for every payment, with approval signatures. | M |
| FR-PAY-003 | Payment methods: cheque, EFT/RTGS (bank file export), mobile money *(confirm providers)*. | M |
| FR-PAY-004 | Payments only to verified payee bank details; bank-detail changes are maker-checker with notification and configurable cooling-off. | M |
| FR-PAY-005 | Payment batches with second approval and idempotent bank instructions; returned payments reversed and re-queued. | M |
| FR-PAY-006 | **Pensioner payroll** (programmed withdrawal, DB pensions, minors' trust instalments): monthly run, PAYE, payslips, approval, bank file. | S |
| FR-PAY-007 | Life certificates / proof of existence: annual, reminders, auto-suspension when overdue. | S |

### 4.8 ACC — Fund accounting

| ID | Requirement | Pri |
|---|---|---|
| FR-ACC-001 | Double-entry ledger **per fund**; administrator fee income in a separate ledger. | M |
| FR-ACC-002 | Chart of accounts per `pz-accounting` (to be confirmed by finance); GL mapping per transaction type. | M |
| FR-ACC-003 | Immutable postings; corrections by reversal. | M |
| FR-ACC-004 | **Account reconciliation**: member sub-ledger = control accounts; schedules vs receipts vs allocations; unallocated and arrears ageing. | M |
| FR-ACC-005 | Bank statement import and reconciliation per fund bank account. | S |
| FR-ACC-006 | Period close per processing month with checklist (all receipts allocated or in suspense, reconciliations signed off). | M |
| FR-ACC-007 | Trial balance, statement of net assets, statement of changes in net assets per fund. | S |
| FR-ACC-008 | Journal export to Old Mutual's corporate GL *(confirm system/format)*. | C |

### 4.9 ENQ — Enquiries, statements & reports

| ID | Requirement | Pri |
|---|---|---|
| FR-ENQ-001 | **Account enquiry** (legacy): pick a client/member and query: main information, transactions for current period, transaction history, statement, transaction trail, contributions, voluntary contributions; show current balance and account status. | M |
| FR-ENQ-002 | **Comprehensive enquiry**: one screen with member, employer, KYC, beneficiaries, balances by component, transactions, claims, documents, notes. | M |
| FR-ENQ-003 | **Member Benefit Statement** (PDF, fund logo) on demand and in bulk: personal details; employee account (EE contributions, bonus on EE, AVC, bonus on AVC, less EE withdrawals); employer account (ER contributions, severance, bonus on ER, less ER withdrawals); total benefit; contributions-up-to date; printed-on date. | M |
| FR-ENQ-008 | **Client Statement** (legacy layout): letterhead, lines with debit/credit/running balance, aged analysis 30/60/90/120/150+ days, current balance. **Transaction Trail** for a date range. **Contributions Trail** per month (EE, company, EE earning, company earning, earning rate %) and **Voluntary Contributions Trail**. | M |
| FR-ENQ-004 | Operational reports: contributions received/outstanding, allocations, bonus runs, claims pipeline & SLA, payments, membership movements. | M |
| FR-ENQ-005 | Regulatory returns to the Registrar/RBM *(confirm formats)*; MRA PAYE returns; FIA reports. | S |
| FR-ENQ-006 | Trustee reports pack per fund. | S |
| FR-ENQ-007 | All tabular reports export to Excel and PDF. | M |

### 4.10 PRT — Portals

| ID | Requirement | Pri |
|---|---|---|
| FR-PRT-001 | **Principal officer portal** (the person who remits pension for a scheme/participating employer): organisation onboarding/KYC, monthly contribution schedule upload/capture & proof of payment (remittance), remittance history and allocation status, arrears & penalties, member list, new-member applications and bulk upload, exit notifications (start claims), salary updates, contribution statements/invoices, scheme reports, change requests. One principal officer may act for several schemes; several officers per scheme. | M |
| FR-PRT-002 | **Member portal**: balances by component (EE/ER/AVC/transfer-in) incl. bonus, statements (PDF), transaction history, beneficiary nominations, contact/bank-detail change requests, KYC document updates, claim submission with documents and claim tracking, projections, life certificate upload (pensioners). | M |
| FR-PRT-003 | **Individual portal**: self-onboarding with individual KYC, contribution plan, payments, plus member features. | C |
| FR-PRT-004 | **Trustee portal**: fund reports, trustee decisions (death benefits). | C |
| FR-PRT-005 | Portal actions are requests reviewed by staff (maker-checker); requesters see status and next steps. | M |
| FR-PRT-006 | Portal access: staff invite principal officers and members (or members self-register by member number + ID number + DOB + OTP); OTP on first login and on money-affecting actions. | M |

### 4.11 NOT — Notifications

| ID | Requirement | Pri |
|---|---|---|
| FR-NOT-001 | In-app, email and SMS notifications through a transactional outbox with retries. | S |
| FR-NOT-002 | Staff alerts for items awaiting their approval; SLA escalation. | S |
| FR-NOT-003 | Employer reminders (schedule due, arrears), member messages (joined, claim progress, statement ready, bank-detail change, KYC/life-certificate expiry, approaching retirement). | S |
| FR-NOT-004 | Respect preferred mode of communication; "post"/"phone call" creates a staff task. | C |

### 4.12 MIG — Data migration from the legacy system

| ID | Requirement | Pri |
|---|---|---|
| FR-MIG-001 | Extract & map legacy companies (funds), members, KYC, beneficiaries, account types, transaction types and full transaction history *(confirm legacy database/platform and access)*. | M |
| FR-MIG-002 | Keep legacy identifiers (company code, account code, old member no., UPID) and legacy transaction codes (2, 7, 14, 68 …) as a mapping. Legacy stores member credits as **negative** amounts — flip the sign on load. Legacy DB is Oracle XE (PFS by Independent Technologies). | M |
| FR-MIG-003 | Reconciliation report: every member's migrated balance = legacy closing balance, per fund, signed off before go-live. | M |
| FR-MIG-004 | Repeatable trial migrations into a staging environment. | M |

### 4.13 SEC — Security, access & audit

| ID | Requirement | Pri |
|---|---|---|
| FR-SEC-001 | Role-based access plus row-level scoping (funds for staff, employer for HR users, self for members). | M |
| FR-SEC-002 | Maker-checker on all money, member-data, bank-detail and configuration changes. | M |
| FR-SEC-003 | Full audit trail: who, what, when, before/after, IP; views of sensitive documents logged. | M |
| FR-SEC-004 | Login with password policy, lockout, password reset; **MFA** for staff and for portal actions affecting money *(confirm OTP channel)*. | M |
| FR-SEC-005 | Sensitive data (IDs, bank details, medical evidence) masked in lists, exports and messages. | M |

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 Performance | Enquiry screens < 2 s; schedule allocation for 5,000 members < 5 min; bonus run for 100,000 members < 30 min (batch, in background). |
| NFR-02 Scale | Initial sizing *(confirm)*: ~50 funds/employers, ~100k members, ~10 years of transaction history migrated. |
| NFR-03 Availability | Business hours 99.5%; portals 24/7 best effort; daily backups, point-in-time recovery, tested restore. |
| NFR-04 Accuracy | Money 2 dp, units/prices 6 dp, round half-up; ledgers always balanced; daily automated reconciliation checks. |
| NFR-05 Security | TLS everywhere; encryption at rest for documents; OWASP ASVS L2; least privilege; secrets outside code. |
| NFR-06 Compliance | Pension Act 2023, Financial Crimes Act (AML/CFT), Data Protection Act 2024, MRA tax rules; record retention ≥ 7 years *(confirm)*. |
| NFR-07 Usability | Portals phone-first (390px), WCAG 2.1 AA; staff screens keyboard-friendly at 1366–1920px. |
| NFR-08 Auditability | Every figure on a statement traceable to transactions and ledger entries. |
| NFR-09 Maintainability | Same architecture and conventions as Money Market; automated tests on money, approvals and access; migrations versioned. |
| NFR-10 Hosting | Docker containers; hosting environment *(confirm: Old Mutual data centre vs cloud; data residency)*. |
| NFR-11 Localisation | MWK, `2 Oct 2026` date format, Africa/Blantyre time zone, Malawi public-holiday calendar. |

## 6. Integrations

| System | Purpose | Pri |
|---|---|---|
| Banks (fund collection/payment accounts) | Statement import, payment files | S |
| Mobile money (Airtel Money, TNM Mpamba) | Personal-pension collections, small payouts | C |
| Email (SMTP) and SMS gateway | Notifications, OTP | S |
| OMLAC | Group-life/funeral premiums & claims, annuity purchase | C |
| Old Mutual corporate GL | Journal export | C |
| Sanctions/PEP screening service | KYC screening | S |
| National Registration Bureau (national ID verification) *(confirm availability)* | ID verification | C |

## 7. Data model overview (indicative)

Fund · Period · Employer/ParticipatingEmployer · BenefitCategory · Portfolio/InvestmentOption ·
Party (corporate/group/individual) · KYCApplication · Document · Signatory/Director ·
Member · SalaryHistory · Beneficiary · AccountType · TransactionType · MemberTransaction ·
ContributionSchedule/ScheduleLine · Receipt · Allocation · BonusDeclaration/BonusRun ·
UnitPrice · Claim/BenefitQuote · TrusteeDecision · Payment/PaymentAllocation/PaymentVoucher ·
PayrollRun/Payslip · LedgerEntry/GLAccount · FeeRule · RegulatoryParameter/TaxTable ·
User/Role/FundAccess · AuditEvent · Notification/Outbox · MigrationBatch.

## 8. Assumptions

1. OMPSC is the administrator; trustees approve bonus rates and death-benefit allocations
   (recorded in the system).
2. Declared bonus rates are the primary earnings method for existing funds (legacy behaviour);
   unit pricing is added for funds that need it.
3. Currency is MWK only.
4. Asset values per fund come from asset managers/custodians as statements; we record them, we
   do not trade.
5. The KYC form serves all Old Mutual Malawi businesses, but this system processes the
   pension-related products; KYC data may be shared with other units under the consent clause.

## 9. Glossary

| Term | Meaning |
|---|---|
| AVC | Additional voluntary contribution by a member |
| Bonus | Declared investment return credited to member balances for a period |
| BI UPID / UPID | Legacy member identifiers *(confirm — likely regulator-issued unique pension IDs)* |
| DB / DC | Defined benefit / defined contribution |
| EE / ER | Employee / employer (contributions) |
| EDD | Enhanced due diligence |
| NRA | Normal retirement age |
| PEP | Politically exposed person/entity |
| Processing month | The fund's single open accounting period |
| Programmed withdrawal | Retirement income drawn from a still-invested balance |
| TA | Traditional Authority (Malawi administrative area) |
| Umbrella fund | One fund with many participating employers |

## 10. Open questions (answer before planning the related phase)

1. **Phasing / MVP:** go-live = legacy parity **plus the member portal and the principal
   officer portal** (decided 2026-11-01); unit pricing, personal pensions, DB and trustee portal
   in later phases *(confirm the later ones)*.
2. **Legacy system:** *partly answered 2026-11-01* — PFS (Independent Technologies), Oracle Forms on
   Oracle XE. Still needed: DB access/credentials or an export, number of funds/members, history depth.
3. **Bonus calculation:** exact method (time-weighting, interim vs final, which components earn
   bonus, rounding), and who declares (trustees per fund?).
4. **What is aged** in the 30/60/90/120/150-day buckets? *Seen on the Client Statement as "aged
   analysis" of the account balance — confirm the ageing rule (by transaction date?).*
5. **UPID / BI UPID** and the **Regulatory Authority Data** tab: meaning and field list.
6. **"Share" account type** — what is it used for?
7. **KYC 1–4 tabs** in the legacy member screen: which fields are on each?
8. **Individual KYC items 28–32** (Monthly Income1, Name, Relationship, Occupation, Cell
   Number): are these next of kin, a third-party funder, or a beneficiary? *Built as next of kin (default) on 2026-11-02.*
16. **KYC policy:** review periods by risk (dev default high 1 / medium 2 / low 3 years), the risk rules
    (any PEP ⇒ high; unregistered group, foreign national, business income ⇒ medium), who gives senior
    approval for high risk (built: an administrator), the declaration wording (neutral v1 seeded), and the
    sanctions/PEP screening provider (FR-ONB-102, not built).
9. **Regulatory figures** to confirm: minimum contribution rates, lump-sum maximum (50%),
   unemployment wait (3 months), pre-retirement access (50% within 5 years), small-balance
   threshold, late-payment interest, vesting minimums, tax on benefits. *Built 2026-11-01 as
   effective-dated parameters + tax tables (Regulatory screen); the dev seed uses the working defaults
   and monthly PAYE bands 0% to MWK 150,000 / 25% to 500,000 / 30% to 2,550,000 / 35% above — confirm
   the PAYE bands and the lump-sum tax rules with MRA before production values are entered.*
10. **Payments:** which banks; bank file formats; cheques still used; mobile-money payouts.
11. **Chart of accounts and journal recipes** in `pz-accounting`: confirm with finance;
    integration with Old Mutual's corporate GL. *Partly resolved 2026-11-02 (user): receipts post cash to suspense
    (Dr 1000 / Cr 2100) only after staff confirm the money and a checker approves — the principal officer's payment notice
    gets an acknowledgement "received, pending confirmation", the official receipt follows confirmation; allocation posts
    Dr 2100 / Cr 2000 net + fee payables; schedule ≠ money → hold until resolved (FR-CON-006); %-of-contribution fees
    follow the rule's payer. Chart itself still to confirm with finance.*
12. **Minors' trust accounts:** payout rules (instalments for school fees/maintenance, age of
    majority 18?), guardian verification.
13. **Hosting, SSO** (Old Mutual Active Directory for staff?), MFA channel, data residency.
14. **Bulk upload template:** fields and format for members (with KYC + account code) — draft to
    be produced in planning for sign-off.
15. **Branding:** Old Mutual brand guidelines/logo for portals and documents.
