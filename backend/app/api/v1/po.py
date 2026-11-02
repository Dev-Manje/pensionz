"""Principal officer portal (/po in the app). Role gate: principal officer;
row gate: `services/portal.require_officer_scheme` for anything per employer."""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models.identity import User, UserRole
from app.api.v1 import kyc as kyc_api
from app.schemas.kyc import ApplicationOut
from app.schemas.portal import OrganisationOut, PoDashboardOut, PortalSchemeOut
from app.services import kyc, portal, receipts

router = APIRouter(prefix="/po", tags=["principal officer portal"])

officer_only = require_roles(UserRole.principal_officer)


@router.get("/schemes", response_model=list[PortalSchemeOut])
def my_schemes(db: Session = Depends(get_db), user: User = Depends(officer_only)) -> list[PortalSchemeOut]:
    """The employers this officer acts for, in every fund."""
    rows = portal.officer_schemes(db, user)
    counts = portal.member_counts(db, [s.id for s, _ in rows])
    return [PortalSchemeOut(**portal.scheme_row(s, f, counts.get(s.id, 0))) for s, f in rows]


@router.get("/dashboard", response_model=PoDashboardOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    """Per employer: this month's remittance, arrears totals; plus recent activity."""
    return portal.dashboard(db, user, receipts.today())


@router.get("/schemes/{scheme_id}/organisation", response_model=OrganisationOut)
def organisation(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    """The employer's approved KYC details, documents, review date and any application in progress."""
    return portal.organisation(db, portal.require_officer_scheme(db, user, scheme_id), kyc.today())


@router.post("/schemes/{scheme_id}/kyc", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def start_kyc(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ApplicationOut:
    """Starts the employer's KYC — or a change to approved details, prefilled from them. One at a time per employer."""
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    return kyc_api._out(db, kyc.start_for_scheme(db, user, scheme), user)
