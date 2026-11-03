"""Daily employer reminders (FR-NOT-003, FR-CON-008) to the principal officers of
active employers:

- **Schedule due** — `employer_due_reminder_days` before the due date (and on it)
  while last month's schedule hasn't been sent: what is still missing.
- **Arrears** — when an overdue month reaches one of `arrears_reminder_days` days
  overdue: one message per employer with the total owed and the months.
  From `arrears_escalation_days` the contributions officers with access to the fund
  are told too (escalation).

Idempotent per business date through the job runner; reminders are by exact day
counts, so a re-run on another day doesn't repeat them."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.scheme import Scheme, SchemeOfficer, SchemeStatus
from app.services import arrears, fund_access, notifications, periods, portal, receipts, schedules


def _officers(db: Session, scheme: Scheme) -> list:
    return [o.user for o in scheme.officers if o.user.status.value == "active"]


def _when(days: int, due: date) -> str:
    return "today" if days == 0 else f"by {due.day} {due:%B} (in {days} day{'s' if days != 1 else ''})"


MISSING = {"not_started": "send the schedule and pay", "payment_only": "send the schedule", "draft": "finish and send the schedule"}


def run(db: Session, as_of: date) -> str:
    due_sent = arrears_sent = escalated = 0
    active = db.execute(select(Scheme).where(Scheme.status == SchemeStatus.active).join(SchemeOfficer).distinct()).scalars().all()
    for scheme in active:
        officers = _officers(db, scheme)
        if not officers:
            continue
        current = portal.current_remittance(db, scheme, as_of)
        if current["days_to_due"] in settings.employer_due_reminder_days and current["stage"] in MISSING:
            notifications.notify_schedule_due(db, officers, scheme.name, periods.label(current["month"]),
                                              _when(current["days_to_due"], current["due_date"]), MISSING[current["stage"]], scheme.id)
            due_sent += 1
        result = arrears.scheme_arrears(db, scheme, as_of)
        overdue = [m for m in result.months if m.arrears > 0 and m.days_overdue > 0]
        hitting = [m for m in overdue if m.days_overdue in settings.arrears_reminder_days]
        if not hitting:
            continue
        months = ", ".join(periods.label(m.month) for m in overdue[-6:]) + (f" and {len(overdue) - 6} earlier" if len(overdue) > 6 else "")
        interest = receipts.money_label(result.total_interest) if result.total_interest else None
        notifications.notify_arrears(db, officers, scheme.name, receipts.money_label(result.total_arrears), months, interest, scheme.id)
        arrears_sent += 1
        if any(m.days_overdue >= settings.arrears_escalation_days for m in hitting):
            staff = [u for u in notifications.users_with_roles(db, set(schedules.MAKERS)) if fund_access.can_access(db, u, scheme.fund_id)]
            notifications.notify_arrears_escalation(db, staff, f"{scheme.code} {scheme.name}", receipts.money_label(result.total_arrears),
                                                    periods.label(overdue[0].month), scheme.fund_id)
            escalated += 1
    db.commit()
    return f"{due_sent} due reminder(s), {arrears_sent} arrears reminder(s), {escalated} escalation(s)"
