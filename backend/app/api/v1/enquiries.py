"""Account enquiry and member statements for staff (FR-ENQ-001…003, 008), bulk
benefit statements, and inviting a member to the portal (FR-PRT-006).
The JSON builders here are shared with the member portal (api/v1/member_portal.py)."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.members import get_member
from app.core.database import get_db
from app.models.category import BenefitCategory
from app.models.fund import Fund
from app.models.identity import User
from app.models.member import Member, MemberStatus
from app.models.scheme import Scheme
from app.services import audit, fund_access, member_portal, member_statements as ms, notifications, periods
from app.services.io import member_documents as docs

router = APIRouter(tags=["enquiries"])
inviters = require_roles(*member_portal.INVITERS)
DocKind = Literal["benefit", "client", "trail", "contributions", "voluntary"]
MAX_BULK = 2000


def _range(start: date | None, end: date | None, member: Member) -> tuple[date, date]:
    end = end or date.today()
    start = start or max(member.date_joined_fund, date(end.year - 1, end.month, 1))
    if start > end:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The start date is after the end date")
    if (end - start).days > 366 * 10:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose at most ten years")
    return start, end


def _money(d: Decimal) -> str:
    return f"{d:.2f}"


def summary_json(db: Session, member: Member) -> dict:
    today = date.today()
    s = ms.benefit_statement(db, member, today)
    fund = db.get(Fund, member.fund_id)
    scheme = db.get(Scheme, member.scheme_id) if member.scheme_id else None
    category = db.get(BenefitCategory, member.category_id) if member.category_id else None
    current = periods.current(db, member.fund_id)
    return {
        "member_id": str(member.id), "account_code": member.account_code, "full_name": member.full_name, "status": member.status.value,
        "fund_code": fund.code, "fund_name": fund.name, "employer": scheme.name if scheme else None,
        "employer_code": scheme.code if scheme else None, "category": category.name if category else None,
        "employee_no": member.employee_no, "date_of_birth": member.date_of_birth.isoformat(),
        "date_joined_fund": member.date_joined_fund.isoformat(), "exit_date": member.exit_date.isoformat() if member.exit_date else None,
        "balance": _money(s.total), "employee_total": _money(s.employee_total), "employer_total": _money(s.employer_total),
        "employee_lines": [{"label": k, "amount": _money(v)} for k, v in s.employee_lines],
        "employer_lines": [{"label": k, "amount": _money(v)} for k, v in s.employer_lines],
        "contributions_up_to": s.contributions_up_to.isoformat() if s.contributions_up_to else None,
        "current_period": current.period.isoformat() if current else None,
        "has_portal_login": member.portal_user_id is not None,
        "ageing": [{"label": k, "amount": _money(v)} for k, v in ms.ageing(db, member, today)],
    }


def _line(l: ms.StatementLine) -> dict:
    return {"date": l.transaction_date.isoformat(), "description": l.description, "reference": l.reference, "transaction": l.transaction,
            "component": l.component.value, "debit": _money(l.debit), "credit": _money(l.credit), "balance": _money(l.balance)}


def statement_json(db: Session, member: Member, start: date, end: date) -> dict:
    s = ms.client_statement(db, member, start, end)
    return {"start": start.isoformat(), "end": end.isoformat(), "opening": _money(s.opening), "closing": _money(s.closing),
            "lines": [_line(l) for l in s.lines], "ageing": [{"label": k, "amount": _money(v)} for k, v in s.ageing]}


def trail_json(db: Session, member: Member, start: date, end: date) -> dict:
    t = ms.transaction_trail(db, member, start, end)
    return {"start": start.isoformat(), "end": end.isoformat(), "lines": [_line(l) for l in t.lines],
            "totals": [{"component": c.value, "debit": _money(d), "credit": _money(cr)} for c, (d, cr) in t.totals.items()]}


def contributions_json(db: Session, member: Member, start: date, end: date) -> dict:
    rows = ms.contributions_trail(db, member, start, end)
    return {"start": start.isoformat(), "end": end.isoformat(), "months": [{
        "month": m.month.isoformat(), "employee": _money(m.employee), "company": _money(m.company),
        "employee_earning": _money(m.employee_earning), "company_earning": _money(m.company_earning), "earning": _money(m.earning),
        "earning_rate": f"{m.earning_rate:f}" if m.earning_rate is not None else None, "total": _money(m.total),
        "voluntary": _money(m.voluntary), "voluntary_earning": _money(m.voluntary_earning),
    } for m in rows]}


def document(db: Session, user: User, member: Member, kind: DocKind, start: date | None, end: date | None, as_at: date | None) -> Response:
    today = date.today()
    if kind == "benefit":
        as_at = as_at or today
        pdf, name = docs.benefit_statement_pdf(db, member, as_at, today), f"benefit-statement-{member.account_code}-{as_at:%Y%m%d}.pdf"
    else:
        start, end = _range(start, end, member)
        if kind == "client":
            pdf = docs.client_statement_pdf(db, member, start, end, today)
        elif kind == "trail":
            pdf = docs.transaction_trail_pdf(db, member, start, end, today)
        else:
            pdf = docs.contributions_trail_pdf(db, member, start, end, today, voluntary=kind == "voluntary")
        name = f"{kind}-{member.account_code}-{end:%Y%m%d}.pdf"
    audit.record(db, user.id, "member", member.id, "statement_downloaded", after={"kind": kind}, fund_id=member.fund_id)
    db.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


# ---- staff endpoints


@router.get("/members/{member_id}/enquiry")
def enquiry(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> dict:
    """Account enquiry → main information: balance by account, status, contributions up to, arrears ageing."""
    return summary_json(db, get_member(db, user, member_id))


@router.get("/members/{member_id}/statement")
def statement(member_id: uuid.UUID, start: date | None = None, end: date | None = None, db: Session = Depends(get_db),
              user: User = Depends(require_staff)) -> dict:
    member = get_member(db, user, member_id)
    return statement_json(db, member, *_range(start, end, member))


@router.get("/members/{member_id}/trail")
def trail(member_id: uuid.UUID, start: date | None = None, end: date | None = None, db: Session = Depends(get_db),
          user: User = Depends(require_staff)) -> dict:
    member = get_member(db, user, member_id)
    return trail_json(db, member, *_range(start, end, member))


@router.get("/members/{member_id}/contributions-trail")
def contributions_trail(member_id: uuid.UUID, start: date | None = None, end: date | None = None, db: Session = Depends(get_db),
                        user: User = Depends(require_staff)) -> dict:
    member = get_member(db, user, member_id)
    return contributions_json(db, member, *_range(start, end, member))


@router.get("/members/{member_id}/documents/{kind}")
def member_document(member_id: uuid.UUID, kind: DocKind, start: date | None = None, end: date | None = None, as_at: date | None = None,
                    db: Session = Depends(get_db), user: User = Depends(require_staff)) -> Response:
    """PDF: benefit statement (as_at), client statement, transaction trail, contributions / voluntary contributions trail."""
    return document(db, user, get_member(db, user, member_id), kind, start, end, as_at)


def _bulk_members(db: Session, user: User, fund_id: uuid.UUID, scheme_id: uuid.UUID | None) -> list[Member]:
    fund = fund_access.require_fund_access(db, user, fund_id)
    query = select(Member).where(Member.fund_id == fund.id, Member.status.notin_((MemberStatus.exited, MemberStatus.deceased)))
    if scheme_id:
        query = query.where(Member.scheme_id == scheme_id)
    rows = list(db.execute(query.order_by(Member.account_code)).scalars())
    if len(rows) > MAX_BULK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{len(rows)} members — choose one employer at a time (at most {MAX_BULK})")
    return rows


@router.get("/funds/{fund_id}/benefit-statements")
def bulk_statements(fund_id: uuid.UUID, as_at: date | None = None, scheme_id: uuid.UUID | None = None, db: Session = Depends(get_db),
                    user: User = Depends(require_staff)) -> Response:
    """Benefit statements for every current member of the fund (or one employer), one page each."""
    as_at = as_at or date.today()
    rows = _bulk_members(db, user, fund_id, scheme_id)
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No current members to print")
    pdf = docs.bulk_benefit_statements_pdf(db, rows, as_at, date.today())
    audit.record(db, user.id, "fund", fund_id, "bulk_statements_printed", after={"members": len(rows), "as_at": as_at, "scheme_id": scheme_id},
                 fund_id=fund_id)
    db.commit()
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="benefit-statements-{as_at:%Y%m%d}.pdf"'})


class PublishIn(BaseModel):
    as_at: date
    scheme_id: uuid.UUID | None = None


@router.post("/funds/{fund_id}/benefit-statements/publish")
def publish_statements(fund_id: uuid.UUID, payload: PublishIn, db: Session = Depends(get_db), user: User = Depends(inviters)) -> dict:
    """Tells members (email, and the portal bell for those with a login) that their statement as at the date is ready."""
    if payload.as_at > date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A statement can't be as at a future date")
    rows = _bulk_members(db, user, fund_id, payload.scheme_id)
    told = 0
    for member in rows:
        if member.email or member.portal_user_id:
            notifications.notify_member_statement_ready(db, member, payload.as_at)
            told += 1
    audit.record(db, user.id, "fund", fund_id, "statements_published", after={"as_at": payload.as_at, "members": told}, fund_id=fund_id)
    db.commit()
    return {"members": len(rows), "notified": told}


@router.post("/members/{member_id}/portal-invite")
def portal_invite(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(inviters)) -> dict:
    """Gives the member a portal login for the email on their record (or links their existing member login)."""
    login = member_portal.invite(db, user, get_member(db, user, member_id))
    return {"detail": f"Invitation sent to {login.email}"}
