"""Principal officers onboarded by staff (FR-PRT-006) — see services/officers.py."""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.approvals import to_out
from app.core.database import get_db
from app.models.fund import Fund
from app.models.identity import User, UserRole
from app.models.scheme import Scheme, SchemeOfficer
from app.schemas.approval import ApprovalOut
from app.schemas.officer import OfficerCreate, OfficerEmployerOut, OfficerFundOut, OfficerListOut, OfficerUpdate
from app.services import fund_access
from app.services import officers as officer_service
from app.services import users as user_service

router = APIRouter(prefix="/officers", tags=["officers"])

makers = require_roles(*officer_service.MAKERS)
viewers = require_roles(UserRole.scheme_config_maker, UserRole.scheme_config_checker, UserRole.admin, UserRole.auditor,
                        UserRole.relationship_manager, UserRole.compliance)


def _out(db: Session, user: User) -> OfficerListOut:
    granted = set(fund_access.granted_fund_ids(db, user.id))
    funds = db.execute(select(Fund).where(Fund.id.in_(officer_service.officer_fund_ids(db, user))).order_by(Fund.code)).scalars()
    employers = db.execute(
        select(Scheme, Fund.code).join(SchemeOfficer, SchemeOfficer.scheme_id == Scheme.id).join(Fund, Fund.id == Scheme.fund_id)
        .where(SchemeOfficer.user_id == user.id).order_by(Fund.code, Scheme.code)
    ).all()
    return OfficerListOut(
        user_id=user.id, full_name=user.full_name or user.email, email=user.email, phone=user.phone, status=user.status,
        awaiting_setup=user.last_login_at is None and user.password_changed_at is None, last_login_at=user.last_login_at,
        funds=[OfficerFundOut(id=f.id, code=f.code, name=f.name, granted=f.id in granted) for f in funds],
        employers=[OfficerEmployerOut(scheme_id=s.id, code=s.code, name=s.name, fund_code=code) for s, code in employers],
        pending_approval_id=officer_service.pending_request_id(db, user.id),
    )


@router.get("", response_model=list[OfficerListOut])
def list_officers(q: str | None = None, db: Session = Depends(get_db), user: User = Depends(viewers)) -> list[OfficerListOut]:
    return [_out(db, u) for u in officer_service.officers(db, user, q)]


@router.post("", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def create_officer(payload: OfficerCreate, db: Session = Depends(get_db), maker: User = Depends(makers)) -> ApprovalOut:
    """Proposes a principal officer's portal login for one or more funds; a
    scheme-setup checker approves, then the officer is emailed an invitation."""
    request = officer_service.propose_new(db, maker, email=payload.email, full_name=payload.full_name,
                                          phone=payload.phone, fund_ids=payload.fund_ids)
    return to_out(db, request, maker)


@router.patch("/{user_id}", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def update_officer(user_id: uuid.UUID, payload: OfficerUpdate, db: Session = Depends(get_db), maker: User = Depends(makers)) -> ApprovalOut:
    officer = officer_service.require_officer(db, maker, user_id)
    request = officer_service.propose_update(db, maker, officer, full_name=payload.full_name, phone=payload.phone,
                                             fund_ids=payload.fund_ids)
    return to_out(db, request, maker)


@router.post("/{user_id}/send-invitation", status_code=status.HTTP_202_ACCEPTED)
def send_invitation(user_id: uuid.UUID, db: Session = Depends(get_db), maker: User = Depends(makers)) -> dict:
    """Invitation again if they never set a password, otherwise a reset link."""
    user_service.send_password_link(db, maker, officer_service.require_officer(db, maker, user_id))
    return {"detail": "Link sent"}
