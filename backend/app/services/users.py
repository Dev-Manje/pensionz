"""User administration. Creating a user and changing a user's roles or status
are maker-checker: one admin proposes, a different admin approves
(approval kind "user_access"). Sending a password link is immediate."""
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.fund import Fund
from app.models.identity import User, UserRole, UserStatus
from app.models.mixins import utcnow
from app.services import approvals, audit, fund_access, identity, notifications, passwords

KIND = "user_access"


def _fund_codes(db: Session, fund_ids) -> list[str]:
    """Fund access is shown and approved by fund code, which people recognise."""
    ids = set(fund_ids)
    if not ids:
        return []
    codes = list(db.execute(select(Fund.code).where(Fund.id.in_(ids))).scalars())
    if len(codes) != len(ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "One of the chosen funds doesn't exist")
    return sorted(codes)


def _fund_ids(db: Session, codes: list[str]) -> set:
    rows = dict(db.execute(select(Fund.code, Fund.id).where(Fund.code.in_(codes))).all()) if codes else {}
    missing = [c for c in codes if c not in rows]
    if missing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Fund {', '.join(missing)} no longer exists — ask for the change again")
    return set(rows.values())


def snapshot(db: Session, user: User) -> dict:
    return {
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "roles": [r.value for r in user.roles],
        "status": user.status.value,
        "funds": _fund_codes(db, fund_access.granted_fund_ids(db, user.id)),
    }


def _role_names(roles: list[UserRole]) -> str:
    return ", ".join(r.value.replace("_", " ") for r in roles) or "no roles"


def propose_new_user(db: Session, maker: User, *, email: str, full_name: str, phone: str | None,
                     roles: list[UserRole], fund_ids: list[uuid.UUID] | None = None) -> ApprovalRequest:
    email = email.strip().lower()
    if identity.find_by_email(db, email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    if not roles:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give the user at least one role")
    request = approvals.submit(
        db, maker, KIND, entity_type="user", entity_id=None,
        summary=f"New user {full_name} <{email}> with {_role_names(roles)}",
        payload={"action": "create", "email": email, "full_name": full_name, "phone": phone,
                 "roles": [r.value for r in roles], "funds": _fund_codes(db, fund_ids or [])},
    )
    db.commit()
    db.refresh(request)
    return request


def propose_update(db: Session, maker: User, user: User, *, full_name: str | None, phone: str | None,
                   roles: list[UserRole] | None, new_status: UserStatus | None,
                   fund_ids: list[uuid.UUID] | None = None) -> ApprovalRequest:
    current = snapshot(db, user)
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
    if fund_ids is not None and _fund_codes(db, fund_ids) != current["funds"]:
        changes["funds"] = _fund_codes(db, fund_ids)
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
        fund_access.set_access(db, user.id, _fund_ids(db, data.get("funds", [])), checker.id)
        token = passwords.issue_token(db, user, "invite", checker.id)
        notifications.notify_invite(db, user, token, passwords.INVITE_DAYS)
        audit.record(db, checker.id, "user", user.id, "created", after=snapshot(db, user))
        return

    user = db.get(User, uuid.UUID(request.entity_id))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That user no longer exists")
    before = snapshot(db, user)
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
    if "funds" in data:
        fund_access.set_access(db, user.id, _fund_ids(db, data["funds"]), checker.id)
    db.flush()
    db.refresh(user)
    audit.record(db, checker.id, "user", user.id, "updated", before=before, after=snapshot(db, user))


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
