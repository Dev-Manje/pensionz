"""Principal officer portal access (FR-PRT-001, FR-PRT-006).

An officer sees only the employers (schemes) they are linked to — possibly
several, in one or more funds. Every portal endpoint that takes a scheme goes
through `require_officer_scheme`; anything else is 404, so officers can't
probe for other employers."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.contribution import (
    AllocationStatus, ContributionAllocation, ContributionReceipt, ContributionSchedule, ReceiptSource, ReceiptStatus,
    ScheduleStatus,
)
from app.models.fund import Fund
from app.models.identity import User, UserRole
from app.models.kyc import ClientType, KycApplication, Party
from app.models.member import Member
from app.models.scheme import Scheme, SchemeOfficer
from app.services import arrears, kyc, kyc_forms, periods, receipts

ZERO = Decimal("0")


def officer_schemes(db: Session, user: User) -> list[tuple[Scheme, Fund]]:
    if not user.has_role(UserRole.principal_officer):
        return []
    return list(db.execute(
        select(Scheme, Fund).join(SchemeOfficer, SchemeOfficer.scheme_id == Scheme.id).join(Fund, Fund.id == Scheme.fund_id)
        .where(SchemeOfficer.user_id == user.id).order_by(Fund.name, Scheme.name)
    ).tuples())


def require_officer_scheme(db: Session, user: User, scheme_id: uuid.UUID) -> Scheme:
    scheme = db.get(Scheme, scheme_id)
    linked = scheme is not None and user.has_role(UserRole.principal_officer) and db.execute(
        select(SchemeOfficer.id).where(SchemeOfficer.scheme_id == scheme.id, SchemeOfficer.user_id == user.id)
    ).first() is not None
    if not linked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employer not found")
    return scheme


def member_counts(db: Session, scheme_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not scheme_ids:
        return {}
    return dict(db.execute(
        select(Member.scheme_id, func.count(Member.id)).where(Member.scheme_id.in_(scheme_ids)).group_by(Member.scheme_id)
    ).all())


def scheme_row(scheme: Scheme, fund: Fund, member_count: int) -> dict:
    return {"id": scheme.id, "code": scheme.code, "name": scheme.name, "status": scheme.status, "fund_id": fund.id,
            "fund_code": fund.code, "fund_name": fund.name, "contribution_day": scheme.contribution_day,
            "billing_frequency": scheme.billing_frequency, "member_count": member_count}


# ---- dashboard (FR-PRT-001) ------------------------------------------------------------

ACTIVITY_DAYS = 90
ACTIVITY_LIMIT = 12
LIVE_RECEIPTS = (ReceiptStatus.notified, ReceiptStatus.pending_approval, ReceiptStatus.confirmed)


def remittance_month(as_at: date) -> date:
    """The month whose contributions fall due this month: last month."""
    return periods.month_start(periods.month_start(as_at) - timedelta(days=1))


def current_remittance(db: Session, scheme: Scheme, as_at: date) -> dict:
    """Where this month's remittance (last month's contributions) has got to.

    stage: allocated → members credited; awaiting_allocation → schedule sent and
    being matched to the money; draft → schedule started, not sent;
    payment_only → money notified or received but no schedule yet; not_started."""
    month = remittance_month(as_at)
    due = arrears.due_date(scheme, month)
    main = db.execute(select(ContributionSchedule).where(
        ContributionSchedule.scheme_id == scheme.id, ContributionSchedule.contribution_month == month,
        ContributionSchedule.supplementary.is_(False), ContributionSchedule.status != ScheduleStatus.cancelled,
    )).scalars().first()
    live = list(db.execute(select(ContributionReceipt).where(
        ContributionReceipt.scheme_id == scheme.id, ContributionReceipt.contribution_month == month,
        ContributionReceipt.status.in_(LIVE_RECEIPTS),
    )).scalars())
    notified = sum((r.notified_amount or ZERO for r in live if r.status != ReceiptStatus.confirmed), ZERO)
    confirmed = sum((r.amount or ZERO for r in live if r.status == ReceiptStatus.confirmed), ZERO)
    if main is not None:
        stage = {ScheduleStatus.allocated: "allocated", ScheduleStatus.ready: "awaiting_allocation"}.get(main.status, "draft")
    else:
        stage = "payment_only" if live else "not_started"
    return {
        "month": month, "due_date": due, "days_to_due": (due - as_at).days, "stage": stage,
        "schedule_id": main.id if main else None, "schedule_reference": main.reference if main else None,
        "schedule_total": main.total if main else None, "member_lines": main.line_count if main else 0,
        "notified_amount": notified, "confirmed_amount": confirmed,
    }


def arrears_summary(db: Session, scheme: Scheme, as_at: date) -> dict:
    """Totals only — what the employer owes, without member-level detail."""
    result = arrears.scheme_arrears(db, scheme, as_at)
    overdue = [m for m in result.months if m.days_overdue > 0 and m.arrears > 0]
    return {
        "total": sum((m.arrears for m in overdue), ZERO), "interest": result.total_interest, "overdue_months": len(overdue),
        "oldest_month": overdue[0].month if overdue else None,
        "oldest_days_overdue": overdue[0].days_overdue if overdue else None,
    }


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def recent_activity(db: Session, scheme_ids: list[uuid.UUID], as_at: date) -> list[dict]:
    """Latest events on the officer's employers, newest first."""
    if not scheme_ids:
        return []
    since = datetime.combine(as_at - timedelta(days=ACTIVITY_DAYS), datetime.min.time(), tzinfo=timezone.utc)
    names = dict(db.execute(select(Scheme.id, Scheme.name).where(Scheme.id.in_(scheme_ids))).all())
    events: list[dict] = []

    def add(at, scheme_id, kind, title, detail=None, link=None):
        if at is not None and at >= since:
            events.append({"at": at, "scheme_id": scheme_id, "scheme_name": names[scheme_id], "kind": kind,
                           "title": title, "detail": detail, "link": link})

    for r in db.execute(select(ContributionReceipt).where(ContributionReceipt.scheme_id.in_(scheme_ids))).scalars():
        month = f" for {periods.label(r.contribution_month)}" if r.contribution_month else ""
        if r.source == ReceiptSource.portal_notice:
            add(r.created_at, r.scheme_id, "notice_sent", f"Payment notice {r.notice_number} sent{month}",
                f"{receipts.money_label(r.notified_amount)} paid on {r.payment_date.day} {r.payment_date:%b %Y}", f"/po/remittances/{r.id}")
        if r.status == ReceiptStatus.confirmed:
            add(r.confirmed_at, r.scheme_id, "payment_confirmed", f"Payment received — receipt {r.receipt_number}",
                f"{receipts.money_label(r.amount)}{month}", f"/po/remittances/{r.id}")
        elif r.status == ReceiptStatus.rejected and r.source == ReceiptSource.portal_notice:
            add(r.updated_at, r.scheme_id, "notice_rejected", f"Payment notice {r.notice_number} could not be confirmed",
                r.rejection_reason, f"/po/remittances/{r.id}")
    for s in db.execute(select(ContributionSchedule).where(ContributionSchedule.scheme_id.in_(scheme_ids))).scalars():
        add(s.submitted_at, s.scheme_id, "schedule_sent", f"Schedule {s.reference} for {periods.label(s.contribution_month)} sent",
            f"{_plural(s.line_count, 'member')} · {receipts.money_label(s.total)}", f"/po/schedules/{s.id}")
    rows = db.execute(
        select(ContributionAllocation, ContributionSchedule)
        .join(ContributionSchedule, ContributionSchedule.id == ContributionAllocation.schedule_id)
        .where(ContributionAllocation.scheme_id.in_(scheme_ids))
    ).tuples()
    for a, s in rows:
        month = periods.label(s.contribution_month)
        if a.status in (AllocationStatus.posted, AllocationStatus.reversed):
            add(a.posted_at, a.scheme_id, "allocated", f"Contributions for {month} credited to members",
                f"{_plural(s.line_count, 'member')} · {receipts.money_label(a.net_to_members)}", f"/po/schedules/{s.id}")
        if a.status == AllocationStatus.reversed:
            add(a.updated_at, a.scheme_id, "allocation_reversed", f"Contributions for {month} taken back for correction",
                "Your pension administrator will contact you about the schedule.", f"/po/schedules/{s.id}")
    events.sort(key=lambda e: e["at"], reverse=True)
    return events[:ACTIVITY_LIMIT]


def dashboard(db: Session, user: User, as_at: date) -> dict:
    pairs = officer_schemes(db, user)
    counts = member_counts(db, [s.id for s, _ in pairs])
    return {
        "as_at": as_at,
        "schemes": [
            {**scheme_row(s, f, counts.get(s.id, 0)),
             "current": current_remittance(db, s, as_at), "arrears": arrears_summary(db, s, as_at)}
            for s, f in pairs
        ],
        "activity": recent_activity(db, [s.id for s, _ in pairs], as_at),
    }


# ---- organisation details & KYC (FR-PRT-001) -------------------------------------------

REVIEW_SOON_DAYS = 60
DETAIL_FIELDS = (
    ("entity_name", "Organisation name"), ("group_name", "Group name"), ("registration_number", "Registration number"),
    ("tpin", "TPIN"), ("office_phone", "Office phone"), ("phone", "Phone"), ("email", "Email"),
    ("physical_address", "Physical address"), ("postal_address", "Postal address"),
    ("contact_name", "Contact person"), ("contact_phone", "Contact person's phone"), ("contact_email", "Contact person's email"),
)


def _application_row(db: Session, app: KycApplication) -> dict:
    return {"id": app.id, "reference": app.reference, "status": app.status, "is_change": kyc.is_change(db, app),
            "submitted_at": app.submitted_at, "decided_at": app.decided_at, "review_note": app.review_note,
            "decision_reason": app.decision_reason, "updated_at": app.updated_at}


def _state(days: int | None, overdue: str) -> str | None:
    if days is None:
        return None
    return overdue if days < 0 else "due_soon" if days <= REVIEW_SOON_DAYS else "current"


def organisation(db: Session, scheme: Scheme, as_at: date) -> dict:
    """What we hold about the employer as a client: the approved details, the documents
    and their expiry, when the next KYC review is due, and any application in progress."""
    party = db.get(Party, scheme.party_id) if scheme.party_id else None
    approved = db.get(KycApplication, party.latest_application_id) if party and party.latest_application_id else None
    data = approved.data if approved else {}
    people_key = "signatories" if approved and approved.client_type == ClientType.group else "directors"
    documents = []
    if approved:
        current = {d.requirement: d for d in kyc.current_documents(approved)}
        for slot in kyc_forms.slots(approved.client_type, approved.data):
            doc = current.get(slot.key)
            if doc is None:
                continue
            documents.append({
                "label": slot.label,
                "type_label": doc.doc_type_other or next((t.label for t in slot.requirement.types if t.code == doc.doc_type), doc.doc_type),
                "issue_date": doc.issue_date, "expiry_date": doc.expiry_date,
                "state": _state((doc.expiry_date - as_at).days if doc.expiry_date else None, "expired"),
            })
    applications = kyc.scheme_applications(db, scheme)
    in_progress = next((a for a in applications if a.status in kyc.OPEN), None)
    return {
        "scheme_id": scheme.id, "scheme_name": scheme.name, "has_client": party is not None,
        "approved_at": party.kyc_approved_at if party else None, "review_due": party.kyc_review_due if party else None,
        "review_state": _state((party.kyc_review_due - as_at).days if party else None, "overdue"),
        "approved_reference": approved.reference if approved else None,
        "details": [{"label": label, "value": str(data[key])} for key, label in DETAIL_FIELDS if data.get(key) not in (None, "")],
        "people_title": "Signatories" if people_key == "signatories" else "Directors and senior managers",
        "people": [{"name": p.get("full_name") or "—", "role": p.get("position") or p.get("occupation")}
                   for p in (data.get(people_key) or []) if isinstance(p, dict)],
        "documents": documents,
        "in_progress": _application_row(db, in_progress) if in_progress else None,
        "history": [_application_row(db, a) for a in applications if a is not in_progress][:10],
    }
