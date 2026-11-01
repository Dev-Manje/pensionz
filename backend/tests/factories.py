"""Small builders for test data. Each flushes (never commits) so the row gets
an id but is still rolled back with the test."""
import itertools
import uuid

from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.identity import User, UserRole
from app.services import identity

_seq = itertools.count(1)
PASSWORD = "password123"


def make_user(db: Session, *roles: UserRole, password: str = PASSWORD) -> User:
    return identity.create_user(
        db, f"user{next(_seq)}-{uuid.uuid4().hex[:6]}@test.dev", password, list(roles), full_name=f"Test User {next(_seq)}"
    )


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def make_fund(db: Session, *staff: User, code: str | None = None, fund_type: str = "standalone_dc"):
    """A fund (no approval round-trip) that the given staff users administer."""
    from app.models.fund import Fund, FundType
    from app.services import fund_access

    fund = Fund(code=code or f"F{next(_seq):05d}", name="Factory Fund", fund_type=FundType(fund_type))
    db.add(fund)
    db.flush()
    for user in staff:
        fund_access.grant(db, user.id, fund.id, None)
    db.flush()
    return fund
