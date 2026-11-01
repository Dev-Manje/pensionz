---
name: pz-notifications
description: Use when adding or changing any message Pensionz sends — email, SMS, in-app notifications, approval alerts, contribution due/arrears reminders to employers, claim progress updates, KYC/life-certificate expiry reminders, retirement reminders, member statements and benefit statements — or the notification infrastructure itself (outbox, templates, preferences, delivery worker).
---

# Notifications & messaging

Build it the way Money Market finished it (see
`C:/moneymarket/moneymarket/backend/app/services/notifications.py`,
`notification_events.py`, `notification_delivery.py`) — copy the design, not the names.

## Architecture

```
service operation ──(same DB commit)──► notification_outbox row(s) + user_notification (bell)
                                              │  worker polls (SKIP LOCKED), retries 1m/5m/30m/2h
                              ┌───────────────┼────────────────┐
                           in-app           email             SMS (Airtel/TNM gateway — confirm)
```

To add a notification:
1. An `EventType` in `services/notification_events.py` — key like `claim.approved`, category
   one of account / money / security / approvals / reminders / statements.
2. A `notify_<event>()` in `services/notifications.py` that resolves recipients and calls
   `_notify(db, event, user_or_contact, title, body, link=..., entity_type=..., entity_id=...)`.
3. Call it from the service **before `db.commit()`**.

Recipients by rule: `member`, `employer_contacts(employer)`, `role:<x>` scoped to the fund,
`initiator`, `approvers_for(<queue>, fund)`. Never send one member's data to another, nor
member-level detail to employer users beyond what HR needs.

Members without portal logins still get email/SMS to the contact on record; respect the
**preferred mode of communication** captured at KYC (phone call / SMS / email / post — "post"
and "phone call" create a staff task instead of a message).

## Content rules

- Plain language; amounts `MWK 1,250,000.00`; dates `2 Oct 2026`.
- Never full ID numbers, bank account numbers or balances in SMS; mask (`****4821`).
- Staff alerts: which fund/employer/member, amount, link straight to the approval screen.
- Statements are PDFs (letterhead per fund) attached or linked behind login — password-protect
  emailed PDFs *(confirm: e.g. member DOB)*.

## Key events (initial list)

employer: schedule due, schedule received/rejected, arrears + penalty, invoice issued ·
member: joined (welcome + member number), contribution received (optional), bonus declared,
statement ready, claim received / documents missing / approved / paid, bank details changed
(to old contacts too), KYC expiring, life certificate due, approaching retirement ·
staff: anything awaiting their approval, ageing queues > SLA.

## Preferences

Per user, per category, per channel; security, money and claim messages are mandatory.

## Verify

Mailpit at http://localhost:8026; SMS gateway stubbed to a log table in dev. Check inbox as
member, employer HR and staff (`pz-verify`).
