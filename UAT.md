# Pensionz — UAT server guide

User acceptance testing of Phases 0–7 (the Phase 0–5 features can be tried now; bonus and the member portal follow). This page covers installing the UAT server, the logins, and the
sample data testers will find. Everything in the data set is **invented**: no real people, employers or funds.

## 1a. Run UAT on the development machine (current set-up)

UAT runs on the development PC with its own database, **`pensionz_uat`**, next to the dev database. Docker Desktop
supplies Postgres, document storage and Mailpit. The API, worker and web app run from the project folder.

In PowerShell **as administrator**, in the project folder:

```powershell
.\uat-local.ps1 reset     # fresh pensionz_uat database: tables + UAT data, then starts UAT mode (3-5 min)
.\uat-local.ps1 start     # start UAT mode again (after a restart), keeping the data
.\uat-local.ps1 status    # what is running and the address to give testers
.\uat-local.ps1 dev       # back to normal development (dev database, localhost only)
```

UAT mode makes the app listen on the PC's network address (found automatically; pass `-Address <ip>` to choose
one). Testers need three ports: **5278** (the app; `-WebPort` changes it), **8002** (the API, which the browser
calls) and **8026** (Mailpit, for sign-in codes). The script adds a Windows Firewall rule for them when run as
administrator; otherwise open them yourself. Testers open `http://<PC address>:5278`; `status` prints the exact
URLs. The PC's address comes from DHCP. If it
changes, run `.\uat-local.ps1 start` again and give testers the new address. Keep the PC awake while testing.

## 1b. Install on a separate Linux server with Docker

You need a Linux server with Docker (Engine 24+ with the Compose v2 plugin) and git. On a Windows server, run
the same commands from Git Bash with Docker Desktop.

```bash
git clone https://github.com/Dev-Manje/pensionz.git
cd pensionz
./uat.sh install          # first run creates .env from .env.uat.example and stops
nano .env                 # replace UAT_HOST (see below), change the passwords and JWT_SECRET_KEY
./uat.sh install          # builds, starts, creates the database tables, loads the UAT data (≈ 3–5 min)
```

In `.env`, replace every `UAT_HOST` with the server's address **exactly as testers will type it** in the
browser, for example `uat.example.org` or `10.0.0.25`. If it doesn't match, sign-in fails: the browser
blocks the API calls, or the screens don't load.

Open these ports to the testers' network:

| Port | What | Who needs it |
|---|---|---|
| 5178 | Pensionz web app | everyone |
| 8002 | API (the web app calls it from the browser) | everyone |
| 8026 | Mailpit — every email the app sends, including sign-in codes | everyone testing |
| 9002 | Document storage (viewing uploaded files) | everyone |

Keep 5433 (Postgres), 9003 (storage console) and 1026 (SMTP) closed to everyone else.

### Everyday commands

| Command | Does |
|---|---|
| `git pull && ./uat.sh update` | install a new version (keeps the data, runs new database changes) |
| `./uat.sh reset` | **wipe everything** and load fresh UAT data — between test rounds (asks you to type RESET) |
| `./uat.sh seed` | load the UAT data again; adds only what is missing |
| `./uat.sh status` | containers and URLs |
| `./uat.sh logs` | follow the API and background-worker logs |
| `./uat.sh stop` | stop (data kept; `./uat.sh update` starts it again) |

The data is dated from the day it is loaded. "Last month" is always the month testers are working on.
After a `reset`, the history moves forward with the calendar.

## 2. Signing in

- App: `http://<PC address>:5278` on the development PC (`http://UAT_HOST:5178` on a Linux server)
- Password for **every** account: **`Pensionz2026`**, unless the server's `.env` sets `SEED_PASSWORD`.
- **Principal officers get a 6-digit code by email at every sign-in.** They also get one before sending a
  schedule or a payment notice. Codes arrive in **Mailpit** at `http://UAT_HOST:8026`; open the newest
  message to that address. A code works once, for 10 minutes.
- Five wrong passwords in a row lock an account for 15 minutes.
- Every action that changes money or records needs a **second person** to approve it (maker-checker).
  Nobody can approve their own request, so test with two logins: two browsers, or a normal window plus
  a private window.

## 3. Logins

### Staff (back office)

| Email | Name | Role | Use it to test |
|---|---|---|---|
| admin@pensionz.dev | Ada Admin | Administrator | Users and roles, fund access, approving high-risk KYC, seeing everything |
| admin2@pensionz.dev | Ben Admin | Administrator | Second administrator, who approves user-access changes made by Ada |
| config.maker@pensionz.dev | Chikondi Setup | Scheme setup | Funds, employers, categories and rates, fees, investment options, Setup lists, regulatory figures, inviting principal officers |
| config.checker@pensionz.dev | Dalitso Setup-Checker | Scheme setup checker | Approving those setup changes |
| members@pensionz.dev | Esther Members | Member administration | New members, corrections, status changes, beneficiaries, salaries, moves, bulk upload |
| members.checker@pensionz.dev | Felix Members-Checker | Member checker | Approving member changes — including requests from the employer portal |
| contributions@pensionz.dev | Grace Contributions | Contributions officer | Receipts, payment notices, schedules, allocation, reversals, arrears |
| contributions.checker@pensionz.dev | Hastings Contributions-Checker | Contributions checker | Approving receipts, allocations and reversals |
| compliance@pensionz.dev | Owen Compliance | Compliance | KYC review queue: documents, risk, return / approve / reject |
| rm@pensionz.dev | Pemphero Relationships | Relationship manager | Capturing KYC applications for clients |
| auditor@pensionz.dev | Queen Auditor | Auditor (read-only) | Looking at everything, changing nothing |
| finance@pensionz.dev | Linda Finance | Finance | — (finance screens come in later phases) |
| finance.checker@pensionz.dev | Mphatso Finance-Checker | Finance checker | — (later phases) |
| benefits@pensionz.dev | Ida Benefits | Benefits officer | — (claims come in Phase 8) |
| benefits.checker@pensionz.dev | James Benefits-Checker | Benefits checker | — (Phase 8) |
| benefits.l2@pensionz.dev | Kondwani Benefits-L2 | Benefits approver (level 2) | — (Phase 8) |
| payroll@pensionz.dev | Ndaona Payroll | Pensioner payroll | — (Phase 9) |

Fund-level staff can work in all four sample funds. Administrators and the auditor see every fund.

### Employer portal (principal officers) — code by email at every sign-in

| Email | Name | Acts for | Use it to test |
|---|---|---|---|
| po@pensionz.dev | Steve Principal-Officer | **Chikwawa Tea Estates** (CTE01, umbrella fund UMB01) and **Lakeshore Sugar Company** (LSC01, stand-alone fund LSS01): two employers in two funds | Dashboard, sending schedules, payment notices, members, requests, statements, organisation KYC, switching employer |
| po2@pensionz.dev | Vitumbiko Principal-Officer | **Nkhata Bay Logistics** (NBL01, UMB01) | An employer in arrears with a part payment waiting for confirmation |

### Other portals (not part of this UAT round)

| Email | Name | Role | State |
|---|---|---|---|
| member@pensionz.dev | Tiwonge Member | Member | Placeholder page — the member portal comes in Phase 7 |
| individual@pensionz.dev | Upile Individual | Individual (personal pension) | Placeholder — Phase 7 |
| trustee@pensionz.dev | Ruth Trustee | Trustee | Placeholder — later phase |

Staff can invite more principal officers from an employer's screen; the invitation email arrives in Mailpit.

## 4. The sample data

### Funds

| Code | Fund | Type | Processing month |
|---|---|---|---|
| UMB01 | Chitukuko Umbrella Pension Fund | Umbrella DC | current month, open |
| LSS01 | Lakeshore Sugar Staff Pension Fund | Stand-alone DC | current month, open |
| MTDB1 | Mulunguzi Teachers Defined Benefit Scheme | Defined benefit | current month, open |
| PPF01 | Tsogolo Personal Pension Fund | Personal pension | none yet (shows that state) |

Each fund has trustees, a collections bank account and investment pools. UMB01 has fees:
- a 1.5% administration fee, paid by members;
- a negotiated 1.25% for CTE01, paid by the employer;
- a 0.75% investment management fee.

The regulatory figures are working defaults and still need confirming. They include:
- minimum contributions of 5% employee and 10% employer;
- KYC reviews every 1, 2 or 3 years by risk;
- a PAYE table.

### Employers and where each one stands

| Code | Employer | Fund | Due by | Principal officer | Situation when loaded |
|---|---|---|---|---|---|
| CTE01 | Chikwawa Tea Estates Ltd | UMB01 | 14th of the next month | po@ | **Fully paid**: every month since Jan 2024 sent, paid, confirmed and credited, last month included |
| LSC01 | Lakeshore Sugar Company Ltd | LSS01 | 14th | po@ | Paid up to two months ago; **last month not sent yet** (due-date reminder scenario) |
| NBL01 | Nkhata Bay Logistics Ltd | UMB01 | 10th | po2@ | Paid up to three months ago; **two months ago overdue** (arrears), with a **part payment notice** (MWK 190,000) waiting for staff to confirm; last month not sent |
| MET01 | Mulunguzi Education Trust | MTDB1 | 7th | — | Defined-benefit employer. Contributions can't be allocated yet, so it shows arrears (known limitation) |

The history goes through the real workflow, so the books tie out:
- the officer's schedule;
- the officer's payment notice;
- the staff confirmation, approved by a checker;
- the receipt;
- the allocation, approved by a checker.

None of the employers has KYC on file yet. Onboarding an employer is a test scenario: the officer starts it
under **Organisation & KYC**, and compliance reviews it.

### Members (16)

| Employer | Account | Name | Employee no. | Category | Status | Salary (MWK) | Beneficiaries |
|---|---|---|---|---|---|---|---|
| CTE01 | UMB01000001 | Thoko Mwale | CT0001 | Management | Active | 900,000 | yes (spouse + minor child) |
| CTE01 | UMB01000002 | Yamikani Phiri | CT0102 | Staff | Active | 420,000 | yes |
| CTE01 | UMB01000003 | Chimwemwe Banda | CT0117 | Staff | Active | 350,000 | — |
| CTE01 | UMB01000004 | Kondwani Gondwe | CT0043 | Staff | Deferred (left 30 Jun 2026) | 380,000 | — |
| CTE01 | UMB01000010 | Madalitso Chikoti | CT0131 | Staff | Active | 520,000 | — |
| CTE01 | UMB01000011 | Tadala Ngwira | CT0150 | Staff | Active (joined 2025) | 310,000 | — |
| CTE01 | UMB01000012 | Lusungu Mhango | CT0009 | Management | Active | 750,000 | — |
| NBL01 | UMB01000005 | Mercy Chirwa | NB2201 | All employees | Active | 610,000 | yes (two children) |
| NBL01 | UMB01000006 | Blessings Nyirenda | NB2378 | All employees | Active (joined 2025) | 280,000 | — |
| NBL01 | UMB01000013 | Fatsani Kachale | NB2240 | All employees | Active | 450,000 | — |
| NBL01 | UMB01000014 | Wongani Msiska | NB2251 | All employees | Active | 395,000 | — |
| LSC01 | LSS01000007 | Grace Kumwenda | LS015 | Permanent staff | Active | 480,000 | yes |
| LSC01 | LSS01000008 | Patrick Mbewe | LS031 | Permanent staff | Inactive (from 30 Jun 2026) | 300,000 | — |
| LSC01 | LSS01000015 | Chikondi Zulu | LS044 | Permanent staff | Active | 365,000 | — |
| LSC01 | LSS01000016 | Mphatso Kamanga | LS052 | Permanent staff | Active (joined Jul 2025) | 295,000 | — |
| MET01 | MTDB1000009 | Esnart Kalua | TCH0007 | Teaching staff | Active | 640,000 | — |

These account numbers are what a fresh install (`install` or `reset`) produces. Members added during testing
take the next numbers.

## 5. Good places to start

- **po@** → dashboard → Lakeshore Sugar → *Send a schedule* for last month. Download the spreadsheet and
  upload it back, or edit rows; try a wrong account number to see the row errors. Send it with the emailed
  code, then *Tell us about a payment* and attach a PDF as proof.
- **contributions@** → Contributions → confirm that payment against the bank, then allocate the schedule.
  **contributions.checker@** approves both. The officer then sees "Members credited".
- **contributions@** → NBL01's part-payment notice → confirm or decline it. **po2@** sees the outcome and
  the arrears.
- **po@** → Members → add a member, change a salary, or report a leaver. **members.checker@** approves;
  the officer sees the result under *Requests*.
- **po@** → Statements → invoice, statement of contributions, arrears statement (PDF).
- **po@** → Organisation & KYC → *Start KYC*. **compliance@** reviews it: returns it, then approves. Then
  try *Change details*.
- Access limits: po2@ must not see Chikwawa or Lakeshore; staff can't use the portal; nobody approves their
  own change.

## 6. Known limitations in this round

- Defined-benefit contributions (MET01) can't be allocated yet, and late-payment interest is calculated but not
  posted.
- Sign-in codes go by email only (SMS comes later). Member, individual and trustee portals come in later
  phases.
- Reminder emails (due date, arrears) go out each morning at 07:30 server time. Results of a test show up the
  next day; staff can run the job by hand with
  `docker compose -f docker-compose.yml -f docker-compose.uat.yml exec backend python -m app.worker run employer_reminders`.

Report problems with the screen, the login used, what you did, what you expected and what happened.
