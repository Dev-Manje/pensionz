"""User administration. Creating a user and changing a user's roles or status
are maker-checker: one admin proposes, a different admin approves
(approval kind "user_access"). Sending a password link is immediate."""
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.identity import User, UserRole, UserStatus
from app.models.mixins import utcnow
from app.services import approvals, audit, identity, notifications, passwords

KIND = "user_access"


def snapshot(user: User) -> dict:
    return {
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "roles": [r.value for r in user.roles],
        "status": user.status.value,
    }


def _role_names(roles: list[UserRole]) -> str:
    return ", ".join(r.value.replace("_", " ") for r in roles) or "no roles"


def propose_new_user(db: Session, maker: User, *, email: str, full_name: str, phone: str | None,
                     roles: list[UserRole]) -> ApprovalRequest:
    email = email.strip().lower()
    if identity.find_by_email(db, email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    if not roles:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give the user at least one role")
    request = approvals.submit(
        db, maker, KIND, entity_type="user", entity_id=None,
        summary=f"New user {full_name} <{email}> with {_role_names(roles)}",
        payload={"action": "create", "email": email, "full_name": full_name, "phone": phone,
                 "roles": [r.value for r in roles]},
    )
    db.commit()
    db.refresh(request)
    return request


def propose_update(db: Session, maker: User, user: User, *, full_name: str | None, phone: str | None,
                   roles: list[UserRole] | None, new_status: UserStatus | None) -> ApprovalRequest:
    current = snapshot(user)
    changes: dict = {}
    if full_name is not None and full_name != user.full_name:
        changes["full_name"] = full_name
    if phone is not None and phone != user.phone:
        changes["phone"] = phone
    if roles is not None and sorted(r.value for r in roles) != current["roles"]:
        if not roles:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give the user at least one role, or deactivate them instead")
        changes["roles"] = sorted(r.value for r in roles)
    if new_status is not None and new_status != user.status:
        changes["status"] = new_status.value
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing has changed")
    request = approvals.submit(
        db, maker, KIND, entity_type="user", entity_id=user.id,
        summary=f"Change user {user.full_name or user.email}: {', '.join(changes)}",
        payload={"action": "update", **changes},
        previous={k: current[k] for k in changes},
    )
    db.commit()
    db.refresh(request)
    return request


def _apply(db: Session, request: ApprovalRequest, checker: User) -> None:
    data = request.payload
    if data["action"] == "create":
        if identity.find_by_email(db, data["email"]) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email was created in the meantime")
        # Nobody knows this password: the user sets theirs from the emailed link.
        user = identity.create_user(db, data["email"], secrets.token_urlsafe(32), [UserRole(r) for r in data["roles"]],
                                    full_name=data["full_name"], phone=data.get("phone"))
        request.entity_id = str(user.id)
        token = passwords.issue_token(db, user, "invite", checker.id)
        notifications.notify_invite(db, user, token, passwords.INVITE_DAYS)
        audit.record(db, checker.id, "user", user.id, "created", after=snapshot(user))
        return

    user = db.get(User, uuid.UUID(request.entity_id))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That user no longer exists")
    before = snapshot(user)
    if "full_name" in data:
        user.full_name = data["full_name"]
    if "phone" in data:
        user.phone = data["phone"]
    if "roles" in data:
        identity.set_roles(db, user, [UserRole(r) for r in data["roles"]])
    if "status" in data:
        user.status = UserStatus(data["status"])
        if user.status != UserStatus.active:
            user.password_changed_at = utcnow()  # signs them out everywhere
    db.flush()
    db.refresh(user)
    audit.record(db, checker.id, "user", user.id, "updated", before=before, after=snapshot(user))


approvals.register(approvals.ApprovalKind(
    name=KIND, label="User access", checker_roles=frozenset({UserRole.admin}), apply=_apply,
))


def send_password_link(db: Session, actor: User, user: User) -> None:
    """Invitation if they never set a password, otherwise a reset link."""
    if user.status != UserStatus.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This user isn't active — reactivate them first")
    never_set = user.password_changed_at is None and user.last_login_at is None
    token = passwords.issue_token(db, user, "invite" if never_set else "reset", actor.id)
    if never_set:
        notifications.notify_invite(db, user, token, passwords.INVITE_DAYS)
    else:
        notifications.notify_password_reset_link(db, user, token, passwords.STAFF_RESET_HOURS)
    audit.record(db, actor.id, "user", user.id, "password_link_sent")
    db.commit()
