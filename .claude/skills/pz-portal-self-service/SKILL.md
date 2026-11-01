---
name: pz-portal-self-service
description: Use when adding or changing anything done by people outside the administrator's staff in Pensionz portals — members (balances, statements, beneficiary nominations, contact/bank changes, claims, projections, investment choice), employers/HR (member joins/exits, monthly contribution schedules, salary updates, arrears, invoices), individual personal-pension holders (onboarding/KYC, top-ups, debit orders) and trustees (read-only reports, decisions) — including the staff approval side of a portal request.
---

# Portals and self-service

## Portals

| Portal | Users | Can do |
|---|---|---|
| **Member** (`/member`) | Active, deferred members; pensioners | View balance by source & portfolio, statements, transaction history, projections; update contact details; nominate beneficiaries; request switch (if allowed); submit claim with documents; upload life certificate; download tax certificate |
| **Principal officer** (`/po`) | Scheme/fund principal officers — the employer's officer who remits contributions (one officer may act for several schemes) | Onboard/KYC the organisation; add new members (single + bulk template), record exits, salary changes; upload/capture monthly contribution schedule & proof of payment (remittance); track allocation status; view arrears, invoices, member list, scheme reports; initiate exit claims on members' behalf |
| **Individual** (`/individual`) | Personal pension holders | Onboard with individual KYC; set contribution plan; pay (mobile money / debit order); everything a member can do |
| **Trustee** (`/trustee`) | Fund trustees | Read-only fund reports; vote/record decisions on death-benefit allocations and other trustee approvals |

Route guarding and nav come from one section table with the roles that unlock each.

## Backend rules for a portal-callable endpoint

1. Role gate (`member`, `principal_officer`, `individual`, `trustee`) **and** row-level gate:
   - member/individual → only their own `member_id`;
   - principal officer → only members of the schemes/employers they are linked to, and only fields HR needs
     (no beneficiary details, no medical evidence, no member bank details);
   - trustee → only funds they are appointed to.
2. Portal actions are **requests**, not instant changes to money or member data: create a
   request in `pending_review`; staff approve (maker-checker; approver ≠ initiator). Exceptions
   (no approval needed) are configurable: e.g. contact-detail changes with OTP confirmation.
3. Validate server-side against scheme rules (eligibility for claim type, switch limits,
   minimum contribution) — never trust client-side checks.
4. Notify the right staff team on submit and the requester on approve/reject (`pz-notifications`).
5. Contribution schedule upload: parse → validate every row (member exists, salary, rates per
   category, totals) → show errors per row to the employer → only a fully valid schedule can be
   submitted. Unknown members become **new-member requests**, never auto-created silently.

## Frontend rules

- Plain language: "Request a withdrawal", "Being checked by your pension administrator — usually within 5
  working days". No internal statuses or role names.
- Every request shows what happens next, who reviews it, expected timing, and appears at once
  in the history with a status chip.
- Confirmation step restating amounts/units before anything affecting money.
- Member and individual portals are **phone-first** (390px); principal officer portal is laptop-first
  but must work on a tablet. Follow `pz-ui-conventions` + `pz-cross-device`.

## Verify

`pz-verify`, logged in as the seeded member, principal officer and staff approver: submit
from the portal, approve as staff, screenshot both sides including 390px for members.
