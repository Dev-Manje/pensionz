import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models.identity import User, UserRole
from app.models.mixins import utcnow
from app.schemas.approval import ApprovalOut
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services import users as user_service
from app.api.v1.approvals import to_out

router = APIRouter(prefix="/users", tags=["users"])

admin_only = require_roles(UserRole.admin)
admin_or_auditor = require_roles(UserRole.admin, UserRole.auditor)


def _out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.locked = user.locked_until is not None and user.locked_until > utcnow()
    out.awaiting_setup = user.last_login_at is None and user.password_changed_at is None
    return out


def _get(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.get("", response_model=list[UserOut])
def list_users(q: str | None = None, db: Session = Depends(get_db), _: User = Depends(admin_or_auditor)) -> list[UserOut]:
    query = select(User).order_by(func.lower(User.full_name), User.email)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(User.email).like(like), func.lower(User.full_name).like(like)))
    return [_out(u) for u in db.execute(query).scalars()]


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(admin_or_auditor)) -> UserOut:
    return _out(_get(db, user_id))


@router.post("", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def create_user(payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(admin_only)) -> ApprovalOut:
    """Proposes a new user; another admin approves, then the user is emailed an invitation."""
    request = user_service.propose_new_user(db, actor, email=payload.email, full_name=payload.full_name,
                                            phone=payload.phone, roles=payload.roles)
    return to_out(db, request, actor)


@router.patch("/{user_id}", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def update_user(user_id: uuid.UUID, payload: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(admin_only)) -> ApprovalOut:
    """Proposes a change of name, phone, roles or status; another admin approves."""
    request = user_service.propose_update(db, actor, _get(db, user_id), full_name=payload.full_name, phone=payload.phone,
                                          roles=payload.roles, new_status=payload.status)
    return to_out(db, request, actor)


@router.post("/{user_id}/send-password-link", status_code=status.HTTP_202_ACCEPTED)
def send_password_link(user_id: uuid.UUID, db: Session = Depends(get_db), actor: User = Depends(admin_only)) -> dict:
    user_service.send_password_link(db, actor, _get(db, user_id))
    return {"detail": "Link sent"}
