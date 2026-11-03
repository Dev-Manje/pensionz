# Test users (dev only)

For the UAT server (install, logins, sample data) see **UAT.md**; `python -m app.seed_uat` adds the UAT data set
including po2@pensionz.dev.

Created by `docker compose exec backend python -m app.seed`. Password for every account:
**`Pensionz2026`**. Sign in at http://localhost:5178. Emails the app sends land in Mailpit:
http://localhost:8026.

| Email | Name | Role(s) | Lands on |
|---|---|---|---|
| admin@pensionz.dev | Ada Admin | Administrator | Home (staff) |
| admin2@pensionz.dev | Ben Admin | Administrator — second checker for user changes | Home (staff) |
| config.maker@pensionz.dev | Chikondi Setup | Scheme setup | Home (staff) |
| config.checker@pensionz.dev | Dalitso Setup-Checker | Scheme setup checker | Home (staff) |
| members@pensionz.dev | Esther Members | Member administration | Home (staff) |
| members.checker@pensionz.dev | Felix Members-Checker | Member checker | Home (staff) |
| contributions@pensionz.dev | Grace Contributions | Contributions officer | Home (staff) |
| contributions.checker@pensionz.dev | Hastings Contributions-Checker | Contributions checker | Home (staff) |
| benefits@pensionz.dev | Ida Benefits | Benefits officer | Home (staff) |
| benefits.checker@pensionz.dev | James Benefits-Checker | Benefits checker | Home (staff) |
| benefits.l2@pensionz.dev | Kondwani Benefits-L2 | Benefits approver (level 2) | Home (staff) |
| finance@pensionz.dev | Linda Finance | Finance | Home (staff) |
| finance.checker@pensionz.dev | Mphatso Finance-Checker | Finance checker | Home (staff) |
| payroll@pensionz.dev | Ndaona Payroll | Pensioner payroll | Home (staff) |
| compliance@pensionz.dev | Owen Compliance | Compliance | Home (staff) |
| rm@pensionz.dev | Pemphero Relationships | Relationship manager | Home (staff) |
| auditor@pensionz.dev | Queen Auditor | Auditor (read-only) | Home (staff) |
| trustee@pensionz.dev | Ruth Trustee | Trustee | (trustee portal — later phase) |
| po@pensionz.dev | Steve Principal-Officer | Principal officer — acts for employers in UMB01 and LSS01; after the password, enter the 6-digit code emailed to Mailpit (every sign-in) | `/po` portal |
| member@pensionz.dev | Tiwonge Member | Member | `/member` portal |
| individual@pensionz.dev | Upile Individual | Personal pension holder | `/member` portal |

All names are invented. Never put real member data (e.g. from the legacy sample documents) into
seed data or tests.
