"""Principal officer portal (/po in the app). Role gate: principal officer;
row gate: `services/portal.require_officer_scheme` for anything per employer."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models.identity import User, UserRole
from app.schemas.portal import PoDashboardOut, PortalSchemeOut
from app.services import portal, receipts

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
