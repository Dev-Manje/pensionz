"""Member portal (/member in the app; FR-PRT-002, FR-PRT-006). Role gate: member;
row gate: `member_portal.require_member` (the member's own memberships only).
Public: /auth/member-register/start + /finish (self-registration)."""
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1 import kyc as kyc_api
from app.api.v1.approvals import to_out
from app.api.v1.auth import _tokens
from app.api.v1.enquiries import DocKind, _money, _range, contributions_json, document, statement_json, summary_json
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_token, decode_token
from app.models.reference import Bank, BankBranch
from app.models.identity import User, UserRole
from app.models.ledger import MemberTransaction
from app.models.member import BeneficiaryNomination, Member
from app.schemas.approval import ApprovalOut
from app.schemas.auth import TokenPair
from app.schemas.kyc import ApplicationOut
from app.schemas.member import NominationIn
from app.services import ledger, member_portal as svc, member_records as records, members

router = APIRouter(tags=["member portal"])
member_only = require_roles(UserRole.member)
REGISTER_CHALLENGE = "member_register"


# ---- self-registration (public)


class RegisterStartIn(BaseModel):
    member_number: str = Field(min_length=2, max_length=30)
    id_number: str = Field(min_length=3, max_length=40)
    date_of_birth: date


class RegisterFinishIn(BaseModel):
    challenge: str
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/auth/member-register/start")
def register_start(payload: RegisterStartIn, db: Session = Depends(get_db)) -> dict:
    """Always the same answer, so the form doesn't reveal who is a member."""
    subject = svc.register_start(db, payload.member_number, payload.id_number, payload.date_of_birth)
    return {"challenge": create_token(str(subject), timedelta(minutes=settings.otp_minutes), REGISTER_CHALLENGE),
            "detail": "If these details match our records, we have sent a 6-digit code to the email address we hold for you."}


@router.post("/auth/member-register/finish", response_model=TokenPair)
def register_finish(payload: RegisterFinishIn, db: Session = Depends(get_db)) -> TokenPair:
    data = decode_token(payload.challenge)
    if data is None or data.get("type") != REGISTER_CHALLENGE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This registration has timed out — start again")
    return _tokens(svc.register_finish(db, uuid.UUID(data["sub"]), payload.code, payload.new_password))


# ---- memberships


def _member(db: Session, user: User, member_id: uuid.UUID) -> Member:
    return svc.require_member(db, user, member_id)


@router.get("/my/members")
def my_memberships(db: Session = Depends(get_db), user: User = Depends(member_only)) -> list[dict]:
    out = []
    for m in svc.memberships(db, user):
        s = summary_json(db, m)
        out.append({k: s[k] for k in ("member_id", "account_code", "full_name", "status", "fund_name", "employer", "balance",
                                      "contributions_up_to")})
    return out


@router.get("/my/members/{member_id}")
def my_member(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(member_only)) -> dict:
    """Balances by account and the details on record (bank account masked)."""
    m = _member(db, user, member_id)
    s = summary_json(db, m)
    s.pop("ageing", None)
    bank = db.get(Bank, m.bank_id) if m.bank_id else None
    branch = db.get(BankBranch, m.bank_branch_id) if m.bank_branch_id else None
    s["details"] = {
        **{f: getattr(m, f) for f in svc.CONTACT_FIELDS},
        "bank_name": bank.name if bank else None, "bank_branch": branch.name if branch else None, "bank_account_name": m.bank_account_name,
        "bank_account_number": members.mask(m.bank_account_number), "id_number": members.mask(m.id_number),
    }
    s["pending_change_id"] = members.pending_request_id(db, m.id)
    s["pending_nomination_id"] = records.pending_id(db, records.KIND_NOMINATION, m.id)
    return s


@router.get("/my/members/{member_id}/transactions")
def my_transactions(member_id: uuid.UUID, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                    db: Session = Depends(get_db), user: User = Depends(member_only)) -> dict:
    m = _member(db, user, member_id)
    query = select(MemberTransaction).where(MemberTransaction.member_id == m.id)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar()
    rows = db.execute(query.order_by(MemberTransaction.transaction_date.desc(), MemberTransaction.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {"total": total, "items": [{
        "id": str(t.id), "date": t.transaction_date.isoformat(), "transaction": t.transaction_name, "code": t.transaction_code,
        "group": ledger.code_group(t.transaction_code), "component": t.component.value, "description": t.description,
        "amount": _money(t.amount), "credit": t.effect.value == "credit",
        "contribution_month": t.contribution_month.isoformat() if t.contribution_month else None,
    } for t in rows]}


@router.get("/my/members/{member_id}/statement")
def my_statement(member_id: uuid.UUID, start: date | None = None, end: date | None = None, db: Session = Depends(get_db),
                 user: User = Depends(member_only)) -> dict:
    m = _member(db, user, member_id)
    return statement_json(db, m, *_range(start, end, m))


@router.get("/my/members/{member_id}/contributions-trail")
def my_contributions(member_id: uuid.UUID, start: date | None = None, end: date | None = None, db: Session = Depends(get_db),
                     user: User = Depends(member_only)) -> dict:
    m = _member(db, user, member_id)
    return contributions_json(db, m, *_range(start, end, m))


@router.get("/my/members/{member_id}/documents/{kind}")
def my_document(member_id: uuid.UUID, kind: DocKind, start: date | None = None, end: date | None = None, as_at: date | None = None,
                db: Session = Depends(get_db), user: User = Depends(member_only)) -> Response:
    return document(db, user, _member(db, user, member_id), kind, start, end, min(as_at or date.today(), date.today()))


# ---- beneficiaries


@router.get("/my/members/{member_id}/beneficiaries")
def my_beneficiaries(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(member_only)) -> dict:
    m = _member(db, user, member_id)
    names = records.relationship_names(db)
    n = db.execute(select(BeneficiaryNomination).where(BeneficiaryNomination.member_id == m.id, BeneficiaryNomination.is_current)).scalar_one_or_none()
    return {
        "signed_date": n.signed_date.isoformat() if n else None,
        # The member's own nomination: they see what they gave (contact details included).
        "beneficiaries": [{
            "full_name": b.full_name, "relationship": b.relationship_code, "relationship_label": names.get(b.relationship_code),
            "date_of_birth": b.date_of_birth.isoformat() if b.date_of_birth else None, "share_pct": f"{b.share_pct:.2f}",
            "phone": b.phone, "email": b.email, "address": b.address, "id_number": b.id_number,
            "is_minor": records.is_minor(b.date_of_birth), "guardian_name": b.guardian_name,
            "guardian_relationship": b.guardian_relationship, "guardian_phone": b.guardian_phone, "guardian_id_number": b.guardian_id_number,
        } for b in (n.beneficiaries if n else [])],
        "pending_approval_id": records.pending_id(db, records.KIND_NOMINATION, m.id),
        "can_nominate": m.status in records.NOMINATING,
    }


@router.post("/my/members/{member_id}/beneficiaries", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def my_nomination(member_id: uuid.UUID, payload: NominationIn, db: Session = Depends(get_db), user: User = Depends(member_only)) -> ApprovalOut:
    """A new nomination form; the member checker approves it."""
    return to_out(db, records.propose_nomination(db, user, _member(db, user, member_id), payload), user)


# ---- contact / bank details


class ContactIn(BaseModel):
    postal_address: str | None = Field(default=None, max_length=200)
    physical_address: str | None = Field(default=None, max_length=200)
    telephone: str | None = Field(default=None, max_length=40)
    mobile: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    preferred_contact: str | None = Field(default=None, max_length=10)


class BankIn(BaseModel):
    bank_id: uuid.UUID
    bank_branch_id: uuid.UUID | None = None
    bank_account_name: str = Field(min_length=2, max_length=200)
    bank_account_number: str = Field(min_length=4, max_length=40)
    code: str = Field(min_length=6, max_length=6)


@router.post("/my/members/{member_id}/contact", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def my_contact(member_id: uuid.UUID, payload: ContactIn, db: Session = Depends(get_db), user: User = Depends(member_only)) -> ApprovalOut:
    m = _member(db, user, member_id)
    return to_out(db, svc.request_contact_change(db, user, m, payload.model_dump(mode="json")), user)


@router.post("/my/members/{member_id}/bank/code", status_code=status.HTTP_202_ACCEPTED)
def my_bank_code(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(member_only)) -> dict:
    _member(db, user, member_id)
    return {"detail": f"A code is on its way to {svc.send_bank_code(db, user)}"}


@router.post("/my/members/{member_id}/bank", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def my_bank(member_id: uuid.UUID, payload: BankIn, db: Session = Depends(get_db), user: User = Depends(member_only)) -> ApprovalOut:
    """Bank details for benefit payments: emailed code first, then the member checker approves."""
    m = _member(db, user, member_id)
    changes = payload.model_dump(exclude={"code"})
    return to_out(db, svc.request_bank_change(db, user, m, changes, payload.code), user)


@router.get("/my/members/{member_id}/requests")
def my_requests(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(member_only)) -> list[dict]:
    m = _member(db, user, member_id)
    return [{"id": str(r.id), "summary": r.summary, "kind": r.kind, "status": r.status.value, "created_at": r.created_at.isoformat(),
             "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None, "review_comment": r.review_comment}
            for r in svc.requests(db, user, m)]


# ---- KYC


@router.get("/my/kyc", response_model=list[ApplicationOut])
def my_kyc(db: Session = Depends(get_db), user: User = Depends(member_only)) -> list[ApplicationOut]:
    return [kyc_api._out(db, a, user) for a in svc.kyc_applications(db, user)]


@router.post("/my/members/{member_id}/kyc", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def my_kyc_start(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(member_only)) -> ApplicationOut:
    """Update my KYC details and documents (a change to the approved KYC, or a first one)."""
    return kyc_api._out(db, svc.start_kyc(db, user, _member(db, user, member_id)), user)
