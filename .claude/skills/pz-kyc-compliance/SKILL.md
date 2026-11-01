---
name: pz-kyc-compliance
description: Use for any Pensionz work on client onboarding and compliance — corporate, group and individual KYC/CDD forms and documents (per "kyc Requirements.docx"), document upload and expiry, PEP declarations and enhanced due diligence, sanctions screening, risk rating, ongoing monitoring, suspicious transaction reporting, consent/declarations, data protection and record retention.
---

# KYC, AML and data protection

Source of truth for onboarding fields: `kyc Requirements.docx` (Old Mutual Malawi), summarised
in `docs/REQUIREMENTS.md` → module **ONB**. Requirement IDs there are `FR-ONB-C*` (corporate),
`FR-ONB-G*` (group), `FR-ONB-I*` (individual). Facts marked *(confirm)* need compliance sign-off.

## Client types

| Type | Who | Key evidence |
|---|---|---|
| **Corporate** | Registered entity: plc, private ltd, NGO, trust, sole trader | Registration/incorporation certificate or Act of Parliament; proof of physical address; constitutive document (articles, constitution, partnership agreement, MoU/board resolution); IDs of directors & senior management (+ passport & immigration permit for foreign nationals); source of funds; proof of bank account; entity PEP declaration |
| **Group** | Unregistered collective: village bank, club, association, family group | Founding document (constitution / minutes); source of funds; proof of bank account; **unlimited signatories** each with name, address, phone, email, occupation, PEP flag, ID, proof of address |
| **Individual** | Member / personal pension holder / beneficiary | Name, gender, marital status, addresses, proof of address, ID type+number+expiry, DOB, residence, nationality, immigration permit (foreigners), source of income/funds, contact preferences, PEP self + related, terms agreement |

Product/scheme multi-select on the form: MPICO Property, OMIG Private Wealth / Money Market /
Segregated Funds, OMUT Interest Bearing / Balanced, **OMPSC Group/Employer Pension**, OMLAC
Group Life / Group Funeral. Scheme/policy numbers: optional, multiple.

## Rules from the source document

- **Never show a list of existing clients** (e.g. an organisation-name dropdown) — typing the
  name in full is required because listing clients to other organisations is a privacy breach.
  Matching to existing records happens on the staff side.
- Every "choose one" document list includes **Other (type it)**.
- Each document requirement has an **upload** control; files are stored, typed and dated.
- The **declaration** text (true & correct, misrepresentation, keep us informed, consent to
  share within the administrator's group business units, confidentiality notice) must be shown
  verbatim from configurable, versioned declaration text (the source wording is Old Mutual's —
  use it as the default template only; the product itself is unbranded)
  and its acceptance stored with timestamp, user, IP and declaration version.
- Proof of address freshness: utility bill ≤ 3 months, city rates ≤ 12 months; telephone bill
  landline only. Bank statements for source of funds cover ≥ 3 months. Validate document dates
  where entered and flag for reviewer otherwise.

## Due diligence workflow

1. Submission (portal or staff-captured) → status `submitted`.
2. Compliance reviewer checks each document (accept / reject with reason → client notified to
   re-upload) — maker-checker: capturer ≠ approver.
3. **Screening**: names of the client, directors, signatories and beneficial owners against
   sanctions/PEP lists *(confirm provider/list)*; results stored with the KYC record.
4. **Risk rating** (low/medium/high) from rules: PEP, foreign national, high-risk country,
   cash-intensive source of funds, group (unregistered) entity. High risk or PEP → **enhanced
   due diligence** + senior-management approval.
5. Approved → client active; KYC review date set by risk (e.g. high 1y, medium 2y, low 3y
   *(confirm)*).
6. Expiring ID/permit/proof → reminders before expiry; benefits not paid against expired KYC.

## AML/CFT obligations (Financial Crimes Act — confirm specifics)

- CDD before any benefit payment; payee identity re-verified at claim time.
- Monitor: contributions inconsistent with declared income, frequent personal-pension ad-hoc
  deposits then early access, third-party payments, bank-detail change followed by a claim.
- Suspicious transactions → internal escalation → STR to the **Financial Intelligence
  Authority**; never tip off the client. Keep records ≥ 7 years after relationship ends *(confirm)*.

## Data protection (Malawi Data Protection Act 2024 — confirm)

- ID numbers, bank details, medical evidence (ill-health claims) are sensitive: role-limited
  access, masked in lists/exports/emails (`****4821`), encrypted at rest for documents.
- Consent to share within Old Mutual units is explicit and stored; employer HR users see only
  their own employees and only what they need.
- Every view of a sensitive document is audit-logged.
