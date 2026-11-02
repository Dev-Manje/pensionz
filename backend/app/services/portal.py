"""Principal officer portal access (FR-PRT-001, FR-PRT-006).

An officer sees only the employers (schemes) they are linked to — possibly
several, in one or more funds. Every portal endpoint that takes a scheme goes
through `require_officer_scheme`; anything else is 404, so officers can't
probe for other employers."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fund import Fund
from app.models.identity import User, UserRole
from app.models.scheme import Scheme, SchemeOfficer


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
