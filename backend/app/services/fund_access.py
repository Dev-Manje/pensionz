"""Row-level fund scoping for staff (FR-SEC-001).

Admins and auditors see every fund; other staff see the funds granted to them
in `user_fund_access`. A fund someone can't see answers 404, not 403, so its
existence isn't disclosed."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fund import Fund, UserFundAccess
from app.models.identity import User, UserRole

ALL_FUNDS_ROLES = frozenset({UserRole.admin, UserRole.auditor})


def sees_all_funds(user: User) -> bool:
    return user.has_any_role(*ALL_FUNDS_ROLES)


def fund_ids_for(db: Session, user: User) -> set[uuid.UUID] | None:
    """The funds the user may see; None means all of them."""
    if sees_all_funds(user):
        return None
    return set(db.execute(select(UserFundAccess.fund_id).where(UserFundAccess.user_id == user.id)).scalars())


def granted_fund_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.execute(select(UserFundAccess.fund_id).where(UserFundAccess.user_id == user_id)).scalars())


def can_access(db: Session, user: User, fund_id: uuid.UUID) -> bool:
    allowed = fund_ids_for(db, user)
    return allowed is None or fund_id in allowed


def require_fund_access(db: Session, user: User, fund_id: uuid.UUID) -> Fund:
    fund = db.get(Fund, fund_id)
    if fund is None or not can_access(db, user, fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fund not found")
    return fund


def grant(db: Session, user_id: uuid.UUID, fund_id: uuid.UUID, granted_by: uuid.UUID | None) -> None:
    exists = db.execute(
        select(UserFundAccess.id).where(UserFundAccess.user_id == user_id, UserFundAccess.fund_id == fund_id)
    ).first()
    if exists is None:
        db.add(UserFundAccess(user_id=user_id, fund_id=fund_id, granted_by_user_id=granted_by))


def set_access(db: Session, user_id: uuid.UUID, fund_ids: set[uuid.UUID], granted_by: uuid.UUID | None) -> None:
    """Replaces the user's fund list. Does not commit."""
    rows = db.execute(select(UserFundAccess).where(UserFundAccess.user_id == user_id)).scalars().all()
    for row in rows:
        if row.fund_id not in fund_ids:
            db.delete(row)
    have = {row.fund_id for row in rows}
    for fund_id in fund_ids - have:
        db.add(UserFundAccess(user_id=user_id, fund_id=fund_id, granted_by_user_id=granted_by))
    db.flush()
