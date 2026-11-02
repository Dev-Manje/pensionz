import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import to_out
from app.core.database import get_db
from app.models.fund import Fund
from app.models.identity import User, UserRole
from app.models.member import Member
from app.models.scheme import Scheme, SchemeOfficer
from app.schemas.approval import ApprovalOut
from app.schemas.scheme import OfficerOut, SchemeIn, SchemeOut, SchemeSummaryOut
from app.services import fund_access
from app.services import members as member_service
from app.services import schemes as scheme_service

router = APIRouter(tags=["schemes"])

config_maker = require_roles(UserRole.scheme_config_maker)
config_roles = require_roles(UserRole.scheme_config_maker, UserRole.scheme_config_checker, UserRole.admin)


def _summary(db: Session, s: Scheme) -> dict:
    return {
        "id": s.id, "fund_id": s.fund_id, "code": s.code, "name": s.name, "status": s.status,
        "contribution_day": s.contribution_day, "billing_frequency": s.billing_frequency,
        "contact_name": s.contact_name, "officer_count": len(s.officers),
        "pending_approval_id": scheme_service.pending_request_id(db, s.id),
    }


def _get(db: Session, user: User, scheme_id: uuid.UUID) -> Scheme:
    scheme = db.get(Scheme, scheme_id)
    if scheme is None or not fund_access.can_access(db, user, scheme.fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employer not found")
    return scheme


def _officer(db: Session, user: User, scheme_id: uuid.UUID | None = None) -> OfficerOut:
    others = select(func.count(SchemeOfficer.id)).where(SchemeOfficer.user_id == user.id)
    if scheme_id is not None:
        others = others.where(SchemeOfficer.scheme_id != scheme_id)
    return OfficerOut(user_id=user.id, full_name=user.full_name or user.email, email=user.email,
                      awaiting_setup=user.last_login_at is None and user.password_changed_at is None,
                      other_scheme_count=db.execute(others).scalar_one())


@router.get("/funds/{fund_id}/schemes", response_model=list[SchemeSummaryOut])
def list_schemes(fund_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> list[SchemeSummaryOut]:
    fund = fund_access.require_fund_access(db, user, fund_id)
    rows = db.execute(select(Scheme).where(Scheme.fund_id == fund.id).order_by(Scheme.code)).scalars()
    return [SchemeSummaryOut(**_summary(db, s)) for s in rows]


@router.post("/funds/{fund_id}/schemes", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def create_scheme(fund_id: uuid.UUID, payload: SchemeIn, db: Session = Depends(get_db), maker: User = Depends(config_maker)) -> ApprovalOut:
    """Proposes a new participating employer; a scheme-setup checker approves it."""
    fund = fund_access.require_fund_access(db, maker, fund_id)
    return to_out(db, scheme_service.propose_new(db, maker, fund, payload), maker)


@router.get("/schemes/officer-candidates", response_model=list[OfficerOut])
def officer_candidates(db: Session = Depends(get_db), _: User = Depends(config_roles)) -> list[OfficerOut]:
    """Principal officers who can be linked to an employer (one officer may act
    for several employers, in any fund)."""
    return [_officer(db, u) for u in scheme_service.officer_candidates(db)]


@router.get("/schemes/{scheme_id}", response_model=SchemeOut)
def get_scheme(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> SchemeOut:
    s = _get(db, user, scheme_id)
    fund = db.get(Fund, s.fund_id)
    return SchemeOut(
        **_summary(db, s),
        fund_code=fund.code, fund_name=fund.name,
        **{f: getattr(s, f) for f in ("registration_number", "tpin", "join_date", "exit_date", "address_line1", "address_line2",
                                      "address_line3", "phone", "email", "contact_email", "contact_phone")},
        officers=sorted((_officer(db, o.user, s.id) for o in s.officers), key=lambda o: o.full_name.lower()),
        party_id=s.party_id, kyc=member_service.kyc_status(db, s.party_id),
        member_count=db.execute(select(func.count()).select_from(Member).where(Member.scheme_id == s.id)).scalar_one(),
        can_edit=user.has_role(UserRole.scheme_config_maker),
    )


@router.put("/schemes/{scheme_id}", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def update_scheme(scheme_id: uuid.UUID, payload: SchemeIn, db: Session = Depends(get_db), maker: User = Depends(config_maker)) -> ApprovalOut:
    """Proposes the employer as it should be (details and principal officers); a checker approves."""
    return to_out(db, scheme_service.propose_update(db, maker, _get(db, maker, scheme_id), payload), maker)
