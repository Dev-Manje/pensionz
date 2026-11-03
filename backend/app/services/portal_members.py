"""Members from the principal officer portal (FR-PRT-001, FR-PRT-005).

The officer sees HR-level facts only — who is on the scheme, employee number,
category, status, dates and salary — never balances, beneficiaries, ID or bank
numbers. Everything they change is a request a member checker approves, built
by the staff services (`members.propose_new`, `member_records.propose_salary`,
`members.propose_status`, the bulk upload in `io/member_import`), so the same
checks apply. Each request is tagged with the employer (`_scheme_id`) and shown
back to the officers as "Requests" with its outcome.

Exit notice: the employer tells us a member has left (or died). It is a status
request — inactive from the last working day, or deceased — with the reason;
the benefit claim itself starts from it in Phase 8.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.category import BenefitCategory, CategoryStatus
from app.models.fund import Fund
from app.models.identity import User
from app.models.member import Member, MemberImport, MemberSalary, MemberStatus
from app.models.scheme import Scheme
from app.schemas.member import MemberCreateIn, SalaryIn, StatusChangeIn
from app.services import member_records, members, portal
from app.services.io import member_import

KIND_LABELS = {members.KIND_NEW: "New member", members.KIND_STATUS: "Exit notice", member_records.KIND_SALARY: "Salary change",
               member_import.KIND: "Bulk upload of new members"}
EXIT_REASONS = {
    "resigned": "Resigned", "dismissed": "Dismissed", "retrenched": "Retrenched / redundant", "contract_ended": "Contract ended",
    "retired": "Retired", "ill_health": "Left because of ill health", "died": "Died", "other": "Other",
}
PORTAL_TAG = "Employer portal (principal officer)"


def require_member(db: Session, user: User, member_id: uuid.UUID) -> Member:
    member = db.get(Member, member_id)
    if member is None or member.scheme_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    portal.require_officer_scheme(db, user, member.scheme_id)
    return member


def _tag(db: Session, request: ApprovalRequest, scheme: Scheme) -> ApprovalRequest:
    """Marks a request as made from the portal for this employer (shown to the checker too)."""
    request.payload = {**request.payload, "requested_from": PORTAL_TAG, "_scheme_id": str(scheme.id)}
    db.commit()
    db.refresh(request)
    return request


# ---- what the officer sees


def _categories(db: Session, scheme_ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {i for i in scheme_ids if i}
    if not ids:
        return {}
    return dict(db.execute(select(BenefitCategory.id, BenefitCategory.name).where(BenefitCategory.scheme_id.in_(ids))).all())


def row(db: Session, m: Member, category_names: dict, pending: set[uuid.UUID], as_at: date) -> dict:
    salary = member_records.salary_on(db, m.id, as_at)
    return {"id": m.id, "account_code": m.account_code, "employee_no": m.employee_no, "full_name": m.full_name, "gender": m.gender,
            "date_of_birth": m.date_of_birth, "category": category_names.get(m.category_id), "status": m.status,
            "status_label": members.STATUS_LABELS[m.status], "status_effective": m.status_effective,
            "date_joined_fund": m.date_joined_fund, "date_joined_employer": m.date_joined_employer,
            "salary": salary.pensionable_salary if salary else None, "salary_from": salary.effective_from if salary else None,
            "has_pending_request": m.id in pending}


def _pending_member_ids(db: Session, scheme: Scheme) -> set[uuid.UUID]:
    rows = db.execute(select(ApprovalRequest.entity_id).where(
        ApprovalRequest.status == "pending", ApprovalRequest.entity_type == "member", ApprovalRequest.entity_id.is_not(None),
        ApprovalRequest.payload["_scheme_id"].astext == str(scheme.id),
    )).scalars()
    return {uuid.UUID(r) for r in rows}


def member_list(db: Session, scheme: Scheme, as_at: date, q: str | None, current_only: bool) -> list[dict]:
    query = select(Member).where(Member.scheme_id == scheme.id)
    if current_only:
        query = query.where(Member.status.in_((MemberStatus.active, MemberStatus.inactive)))
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(Member.first_name + " " + Member.last_name).like(like), func.lower(Member.account_code).like(like),
                                func.lower(func.coalesce(Member.employee_no, "")).like(like)))
    found = list(db.execute(query.order_by(Member.last_name, Member.first_name).limit(500)).scalars())
    names = _categories(db, {scheme.id})
    pending = _pending_member_ids(db, scheme)
    return [row(db, m, names, pending, as_at) for m in found]


def member_detail(db: Session, member: Member, as_at: date) -> dict:
    scheme = db.get(Scheme, member.scheme_id)
    base = row(db, member, _categories(db, {scheme.id}), _pending_member_ids(db, scheme), as_at)
    salaries = db.execute(select(MemberSalary).where(MemberSalary.member_id == member.id)
                          .order_by(MemberSalary.effective_from.desc())).scalars()
    requests = [request_row(db, r) for r in db.execute(select(ApprovalRequest).where(
        ApprovalRequest.entity_type == "member", ApprovalRequest.entity_id == str(member.id),
        ApprovalRequest.payload["_scheme_id"].astext == str(scheme.id),
    ).order_by(ApprovalRequest.created_at.desc()).limit(20)).scalars()]
    return {**base, "scheme_id": scheme.id, "scheme_name": scheme.name,
            "salaries": [{"effective_from": s.effective_from, "basic_salary": s.basic_salary, "pensionable_salary": s.pensionable_salary}
                         for s in salaries],
            "requests": requests,
            "can_change_salary": member.status in member_records.SALARIED,
            "can_give_notice": member.status in (MemberStatus.active, MemberStatus.inactive)}


def categories(db: Session, scheme: Scheme) -> list[dict]:
    return [{"id": c.id, "code": c.code, "name": c.name} for c in db.execute(
        select(BenefitCategory).where(BenefitCategory.scheme_id == scheme.id, BenefitCategory.status == CategoryStatus.active)
        .order_by(BenefitCategory.name)).scalars()]


# ---- requests


def new_member(db: Session, user: User, scheme: Scheme, data: dict, basic_salary: Decimal | None) -> ApprovalRequest:
    fund = db.get(Fund, scheme.fund_id)
    payload = MemberCreateIn(**{**data, "scheme_id": scheme.id, "account_code": None})
    request = members.propose_new(db, user, fund, payload, first_salary=basic_salary)
    return _tag(db, request, scheme)


def salary_change(db: Session, user: User, member: Member, data: SalaryIn) -> ApprovalRequest:
    request = member_records.propose_salary(db, user, member, data)
    return _tag(db, request, db.get(Scheme, member.scheme_id))


def exit_notice(db: Session, user: User, member: Member, *, last_day: date, reason: str, note: str | None) -> ApprovalRequest:
    if reason not in EXIT_REASONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose why the member left")
    if member.status not in (MemberStatus.active, MemberStatus.inactive):
        raise HTTPException(status.HTTP_409_CONFLICT, f"The member is {members.STATUS_LABELS[member.status].lower()} — no notice is needed")
    if reason == "other" and not (note or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say why the member left")
    to = MemberStatus.deceased if reason == "died" else MemberStatus.inactive
    if to == member.status:
        raise HTTPException(status.HTTP_409_CONFLICT, "The member is already recorded as not contributing — ask us to start the claim")
    words = f"Employer exit notice: {EXIT_REASONS[reason].lower()}" + (" on " if reason == "died" else ", last working day ") + \
        f"{last_day.day} {last_day:%b %Y}" + (f". {note.strip()}" if note and note.strip() else "")
    request = members.propose_status(db, user, member, StatusChangeIn(to_status=to, effective_date=last_day, reason=words[:1000]))
    request.payload = {**request.payload, "exit_reason": EXIT_REASONS[reason], "_exit_reason": reason,
                       "next_step": "Start the benefit claim"}
    return _tag(db, request, db.get(Scheme, member.scheme_id))


def request_row(db: Session, r: ApprovalRequest) -> dict:
    member_id = uuid.UUID(r.entity_id) if r.entity_type == "member" and r.entity_id else None
    return {"id": r.id, "kind": r.kind, "kind_label": KIND_LABELS.get(r.kind, r.kind), "summary": r.summary, "status": r.status,
            "created_at": r.created_at, "decided_at": r.reviewed_at, "comment": r.review_comment, "member_id": member_id,
            "requested_by": db.get(User, r.initiated_by_user_id).full_name if r.initiated_by_user_id else None}


def scheme_requests(db: Session, scheme: Scheme) -> list[dict]:
    since = date.today() - timedelta(days=365)
    rows = db.execute(select(ApprovalRequest).where(
        ApprovalRequest.payload["_scheme_id"].astext == str(scheme.id), ApprovalRequest.created_at >= since,
    ).order_by(ApprovalRequest.created_at.desc()).limit(200)).scalars()
    return [request_row(db, r) for r in rows]


def require_request(db: Session, user: User, request_id: uuid.UUID) -> ApprovalRequest:
    request = db.get(ApprovalRequest, request_id)
    scheme_id = (request.payload or {}).get("_scheme_id") if request else None
    if not scheme_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    portal.require_officer_scheme(db, user, uuid.UUID(scheme_id))
    return request


# ---- bulk upload


def require_import(db: Session, user: User, import_id: uuid.UUID) -> MemberImport:
    batch = db.get(MemberImport, import_id)
    if batch is None or batch.scheme_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    portal.require_officer_scheme(db, user, batch.scheme_id)
    return batch


def submit_import(db: Session, user: User, batch: MemberImport) -> ApprovalRequest:
    request = member_import.submit(db, user, batch)
    return _tag(db, request, db.get(Scheme, batch.scheme_id))
