import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token, issued_before_password_change
from app.models.identity import STAFF_ROLES, User, UserRole, UserStatus

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Your session has ended. Please sign in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access" or payload.get("sub") is None:
        raise credentials_error
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or user.status != UserStatus.active:
        raise credentials_error
    if issued_before_password_change(payload, user.password_changed_at):
        raise credentials_error
    return user


def require_roles(*roles: UserRole):
    def _check(user: User = Depends(get_current_user)) -> User:
        if not user.has_any_role(*roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action")
        return user

    return _check


# Any administrator-side role (not portal users).
require_staff = require_roles(*STAFF_ROLES)


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
