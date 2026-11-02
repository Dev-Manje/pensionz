"""Principal officer portal (/po in the app). Role gate: principal officer;
row gate: `services/portal.require_officer_scheme` for anything per employer."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models.identity import User, UserRole
from app.models.member import Member
from app.schemas.portal import PortalSchemeOut
from app.services import portal

router = APIRouter(prefix="/po", tags=["principal officer portal"])

officer_only = require_roles(UserRole.principal_officer)


@router.get("/schemes", response_model=list[PortalSchemeOut])
def my_schemes(db: Session = Depends(get_db), user: User = Depends(officer_only)) -> list[PortalSchemeOut]:
    """The employers this officer acts for, in every fund."""
    rows = portal.officer_schemes(db, user)
    counts = dict(db.execute(
        select(Member.scheme_id, func.count(Member.id)).where(Member.scheme_id.in_([s.id for s, _ in rows])).group_by(Member.scheme_id)
    ).all()) if rows else {}
    return [
        PortalSchemeOut(id=s.id, code=s.code, name=s.name, status=s.status, fund_id=f.id, fund_code=f.code, fund_name=f.name,
                        contribution_day=s.contribution_day, billing_frequency=s.billing_frequency, member_count=counts.get(s.id, 0))
        for s, f in rows
    ]
