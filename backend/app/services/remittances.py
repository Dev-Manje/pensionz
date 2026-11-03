"""Remitting contributions from the principal officer portal (FR-PRT-001, FR-CON-001/003/004).

A remittance is one month's contributions for one employer: the schedule
(member-by-member split) and the payment notice(s) for the money. Both reuse the
staff services — `schedules` (draft → checks every line → submit hands it to
the contributions officers' allocation queue) and `receipts.submit_notice`
("received, pending confirmation" until the bank statement shows the money).

- An officer edits only drafts started in the portal; a schedule staff
  captured from paper stays theirs (read-only here).
- Sending a schedule or a payment notice moves money, so it needs a one-time
  code emailed to the officer (purpose `remit`), checked after the request
  itself is known to be valid so a refused request doesn't use up the code.
- Everything is per employer through `portal.require_officer_scheme`: other
  employers' schedules and receipts are 404.
"""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.contribution import (
    AllocationStatus, ContributionAllocation, ContributionReceipt, ContributionSchedule, PaymentMethod, ReceiptStatus,
    ScheduleSource, ScheduleStatus,
)
from app.models.fund import Fund
from app.models.identity import User
from app.models.scheme import Scheme
from app.services import fund_access, notifications, otp, periods, portal, receipts, schedules

REMIT = "remit"
HISTORY_MONTHS = 24
ZERO = Decimal("0.00")


# ---- row gates


def require_schedule(db: Session, user: User, schedule_id: uuid.UUID) -> ContributionSchedule:
    schedule = db.get(ContributionSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    portal.require_officer_scheme(db, user, schedule.scheme_id)
    return schedule


def require_receipt(db: Session, user: User, receipt_id: uuid.UUID) -> ContributionReceipt:
    receipt = db.get(ContributionReceipt, receipt_id)
    if receipt is None or receipt.scheme_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    portal.require_officer_scheme(db, user, receipt.scheme_id)
    return receipt


def editable(schedule: ContributionSchedule) -> bool:
    return schedule.status == ScheduleStatus.draft and schedule.source == ScheduleSource.portal


def require_editable(schedule: ContributionSchedule) -> None:
    if schedule.source != ScheduleSource.portal:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{settings.brand_administrator.capitalize()} prepared this schedule — ask them to change it")
    if schedule.status != ScheduleStatus.draft:
        raise HTTPException(status.HTTP_409_CONFLICT, "This schedule has been sent — it can't be changed now")


# ---- schedules


def start(db: Session, user: User, scheme: Scheme, month: date, supplementary: bool) -> ContributionSchedule:
    """A draft for the month, prefilled with every active member at the expected amounts."""
    fund = db.get(Fund, scheme.fund_id)
    return schedules.create(db, user, fund, scheme.id, month, supplementary=supplementary, source=ScheduleSource.portal, prefill=True)


def send_code(db: Session, user: User) -> str:
    otp.send(db, user, REMIT, "send contributions")
    db.commit()
    return otp.masked_destination(user)


def _staff(db: Session, fund_id: uuid.UUID) -> list[User]:
    return [u for u in notifications.users_with_roles(db, set(schedules.MAKERS)) if fund_access.can_access(db, u, fund_id)]


def submit(db: Session, user: User, schedule: ContributionSchedule, code: str) -> ContributionSchedule:
    require_editable(schedule)
    schedules.recheck(db, schedule)
    if not schedule.lines:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The schedule has no members on it")
    if schedule.error_count:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Fix the {schedule.error_count} row(s) with errors first")
    otp.verify(db, user, REMIT, code)
    scheme = db.get(Scheme, schedule.scheme_id)
    for officer in _staff(db, schedule.fund_id):
        notifications._notify(db, officer, "schedule.portal_submitted", f"Schedule {schedule.reference} to allocate",
                              f"{scheme.name} sent its {periods.label(schedule.contribution_month)} schedule: {schedule.line_count} members, "
                              f"{receipts.money_label(schedule.total)}.", link=f"/contributions/schedules/{schedule.id}",
                              entity_type="contribution_schedule", entity_id=schedule.id, email=False)
    others = [o.user for o in scheme.officers if o.user_id != user.id]
    notifications.notify_officers(
        db, [user, *others], "schedule.received", f"Schedule {schedule.reference} received",
        f"We have received the {periods.label(schedule.contribution_month)} schedule for {scheme.name} "
        f"({schedule.line_count} members, {receipts.money_label(schedule.total)}), sent by {user.full_name}. "
        "Members are credited once it is matched to your payment.",
        link=f"/po/schedules/{schedule.id}", entity_type="contribution_schedule", entity_id=schedule.id)
    return schedules.submit(db, user, schedule)


def cancel(db: Session, user: User, schedule: ContributionSchedule) -> ContributionSchedule:
    require_editable(schedule)
    return schedules.cancel(db, user, schedule)


# ---- payment notices


def notice(db: Session, user: User, scheme: Scheme, *, amount: Decimal, payment_date: date, payment_method: PaymentMethod,
           payer_reference: str | None, contribution_month: date | None, notes: str | None, code: str) -> ContributionReceipt:
    """Tells the administrator the employer has paid; staff confirm it against the bank statement."""
    if amount is None or amount <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter the amount paid")
    if payment_date > receipts.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The payment date can't be in the future")
    if contribution_month and periods.month_start(contribution_month) > periods.month_start(receipts.today()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The contribution month can't be in the future")
    otp.verify(db, user, REMIT, code)
    return receipts.submit_notice(db, user, scheme, amount=amount, payment_date=payment_date, payment_method=payment_method,
                                  payer_reference=payer_reference, contribution_month=contribution_month, notes=notes)


# ---- what the officer sees


def schedule_row(db: Session, s: ContributionSchedule) -> dict:
    allocation = db.execute(select(ContributionAllocation).where(
        ContributionAllocation.schedule_id == s.id, ContributionAllocation.status == AllocationStatus.posted,
    )).scalar_one_or_none()
    return {"id": s.id, "reference": s.reference, "month": s.contribution_month, "supplementary": s.supplementary, "status": s.status,
            "total": s.total, "line_count": s.line_count, "error_count": s.error_count, "submitted_at": s.submitted_at,
            "credited_at": allocation.posted_at if allocation else None, "from_portal": s.source == ScheduleSource.portal,
            "editable": editable(s)}


def payment_row(r: ContributionReceipt) -> dict:
    return {"id": r.id, "notice_number": r.notice_number, "receipt_number": r.receipt_number, "status": r.status,
            "month": r.contribution_month, "notified_amount": r.notified_amount, "amount": r.amount, "payment_date": r.payment_date,
            "value_date": r.value_date, "payment_method": r.payment_method, "payer_reference": r.payer_reference,
            "rejection_reason": r.rejection_reason, "has_proof": r.proof_storage_key is not None, "created_at": r.created_at}


def history(db: Session, scheme: Scheme, as_at: date) -> list[dict]:
    """Month by month, newest first: the schedules and payments for each. Always includes
    the month now due (last month); payments without a month are listed on their own."""
    since = date(as_at.year - HISTORY_MONTHS // 12, as_at.month, 1)
    scheds = db.execute(select(ContributionSchedule).where(
        ContributionSchedule.scheme_id == scheme.id, ContributionSchedule.status != ScheduleStatus.cancelled,
        ContributionSchedule.contribution_month >= since,
    ).order_by(ContributionSchedule.supplementary, ContributionSchedule.created_at)).scalars().all()
    pays = db.execute(select(ContributionReceipt).where(
        ContributionReceipt.scheme_id == scheme.id, ContributionReceipt.status != ReceiptStatus.cancelled,
        ContributionReceipt.payment_date >= since,
    ).order_by(ContributionReceipt.payment_date)).scalars().all()
    months: dict[date | None, dict] = {}

    def month(m: date | None) -> dict:
        return months.setdefault(m, {"month": m, "schedules": [], "payments": []})

    month(portal.remittance_month(as_at))
    for s in scheds:
        month(s.contribution_month)["schedules"].append(schedule_row(db, s))
    for r in pays:
        month(r.contribution_month)["payments"].append(payment_row(r))
    for row in months.values():
        main = next((s for s in row["schedules"] if not s["supplementary"]), None)
        # What's been sent (a draft isn't owed yet).
        row["schedule_total"] = sum((s["total"] for s in row["schedules"]
                                     if s["status"] in (ScheduleStatus.ready, ScheduleStatus.allocated)), ZERO)
        row["paid"] = sum((p["amount"] or ZERO for p in row["payments"] if p["status"] == ReceiptStatus.confirmed), ZERO)
        row["noted"] = sum((p["notified_amount"] or ZERO for p in row["payments"]
                            if p["status"] in (ReceiptStatus.notified, ReceiptStatus.pending_approval)), ZERO)
        row["stage"] = _stage(main, row["payments"])
    dated = sorted((r for m, r in months.items() if m is not None), key=lambda r: r["month"], reverse=True)
    return dated + ([months[None]] if None in months else [])


def _stage(main: dict | None, payments: list[dict]) -> str:
    """Same words as the dashboard: allocated / awaiting_allocation / draft / payment_only / not_started."""
    if main is not None:
        return {ScheduleStatus.allocated: "allocated", ScheduleStatus.ready: "awaiting_allocation"}.get(main["status"], "draft")
    live = [p for p in payments if p["status"] != ReceiptStatus.rejected]
    return "payment_only" if live else "not_started"


def payment_detail(db: Session, receipt: ContributionReceipt) -> dict:
    scheme = db.get(Scheme, receipt.scheme_id)
    same_month = []
    if receipt.contribution_month:
        same_month = [schedule_row(db, s) for s in db.execute(select(ContributionSchedule).where(
            ContributionSchedule.scheme_id == scheme.id, ContributionSchedule.contribution_month == receipt.contribution_month,
            ContributionSchedule.status != ScheduleStatus.cancelled,
        )).scalars()]
    from app.services.io import receipt_document
    return {**payment_row(receipt), "scheme_id": scheme.id, "scheme_name": scheme.name, "notes": receipt.notes,
            "proof_filename": receipt.proof_filename, "confirmed_at": receipt.confirmed_at,
            "can_add_proof": receipt.status == ReceiptStatus.notified, "document_kind": receipt_document.kind(receipt),
            "schedules": same_month}
