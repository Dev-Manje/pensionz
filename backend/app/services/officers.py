"""Principal officers onboarded by the pension administrator (FR-PRT-006).

Decided 2026-11-03: staff create the officer's portal login on its own — not
only from an employer's screen — for one or more funds. The funds are the ones
the officer may apply into with a new employer (employer onboarding by the
officer); they are kept in `user_fund_access`, which only staff endpoints
read for scoping, so for a portal user the rows mean "may apply into".

Maker: scheme-setup maker (or an administrator) who administers every chosen
fund. Checker: scheme-setup checker (approval kind "officer_access"). On
approval a new officer gets a principal-officer login and an invitation email;
sign-in then needs the emailed one-time code like every portal user."""
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.fund import Fund, FundStatus, UserFundAccess
from app.models.identity import User, UserRole, UserRoleAssignment, UserStatus
from app.models.scheme import Scheme, SchemeOfficer
from app.services import approvals, audit, fund_access, identity, notifications, passwords
from app.services.users import _fund_codes, _fund_ids

KIND = "officer_access"
MAKERS = (UserRole.scheme_config_maker, UserRole.admin)


def officer_fund_ids(db: Session, user: User) -> set[uuid.UUID]:
    """Funds the officer may apply into: granted by staff, plus the funds of
    the employers they already act for (officers invited from an employer
    screen before this existed)."""
    granted = set(fund_access.granted_fund_ids(db, user.id))
    linked = set(db.execute(
        select(Scheme.fund_id).join(SchemeOfficer, SchemeOfficer.scheme_id == Scheme.id).where(SchemeOfficer.user_id == user.id)
    ).scalars())
    return granted | linked


def pending_request_id(db: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(ApprovalRequest.id).where(
            ApprovalRequest.kind == KIND, ApprovalRequest.entity_id == str(user_id), ApprovalRequest.status == ApprovalStatus.pending,
        )
    ).scalar_one_or_none()


def officers(db: Session, viewer: User, q: str | None = None) -> list[User]:
    """Principal officers the viewer may see: all for admins/auditors, else
    those with a fund (granted or through an employer) the viewer administers."""
    query = (select(User).join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
             .where(UserRoleAssignment.role == UserRole.principal_officer))
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)))
    allowed = fund_access.fund_ids_for(db, viewer)
    if allowed is not None:
        granted = select(UserFundAccess.user_id).where(UserFundAccess.fund_id.in_(allowed))
        linked = (select(SchemeOfficer.user_id).join(Scheme, Scheme.id == SchemeOfficer.scheme_id)
                  .where(Scheme.fund_id.in_(allowed)))
        query = query.where(or_(User.id.in_(granted), User.id.in_(linked)))
    return list(db.execute(query.order_by(func.lower(User.full_name), User.email)).scalars().unique())


def require_officer(db: Session, viewer: User, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None or not user.has_role(UserRole.principal_officer) or user not in officers(db, viewer):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Principal officer not found")
    return user


def _check_funds(db: Session, maker: User, fund_ids: list[uuid.UUID]) -> list[Fund]:
    if not fund_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose at least one fund the officer will work in")
    funds = [fund_access.require_fund_access(db, maker, fid) for fid in dict.fromkeys(fund_ids)]
    closed = [f.code for f in funds if f.status != FundStatus.active]
    if closed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Fund {', '.join(closed)} isn't active")
    return funds


def _scope(funds: list[Fund]) -> uuid.UUID | None:
    # One fund → only that fund's checkers see it; several → any scheme-setup checker.
    return funds[0].id if len(funds) == 1 else None


def snapshot(db: Session, user: User) -> dict:
    return {
        "email": user.email, "full_name": user.full_name, "phone": user.phone,
        "funds": _fund_codes(db, fund_access.granted_fund_ids(db, user.id)),
    }


def propose_new(db: Session, maker: User, *, email: str, full_name: str, phone: str | None,
                fund_ids: list[uuid.UUID]) -> ApprovalRequest:
    email = email.strip().lower()
    existing = identity.find_by_email(db, email)
    if existing is not None:
        if existing.has_role(UserRole.principal_officer):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "This email already belongs to a principal officer — change their funds instead")
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{email} already has a login without the principal officer role — ask an administrator to add the role")
    waiting = db.execute(
        select(ApprovalRequest.id).where(ApprovalRequest.kind == KIND, ApprovalRequest.status == ApprovalStatus.pending,
                                         func.lower(ApprovalRequest.payload["email"].astext) == email)
    ).first()
    if waiting is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This officer is already waiting for approval")
    funds = _check_funds(db, maker, fund_ids)
    request = approvals.submit(
        db, maker, KIND, entity_type="user", entity_id=None,
        summary=f"New principal officer {full_name} <{email}> for {', '.join(sorted(f.code for f in funds))}",
        payload={"action": "create", "email": email, "full_name": full_name, "phone": phone,
                 "funds": sorted(f.code for f in funds)},
        fund_id=_scope(funds),
    )
    db.commit()
    db.refresh(request)
    return request


def propose_update(db: Session, maker: User, user: User, *, full_name: str | None, phone: str | None,
                   fund_ids: list[uuid.UUID] | None) -> ApprovalRequest:
    current = snapshot(db, user)
    changes: dict = {}
    if full_name is not None and full_name != user.full_name:
        changes["full_name"] = full_name
    if phone is not None and (phone or None) != user.phone:
        changes["phone"] = phone or None
    funds: list[Fund] = []
    if fund_ids is not None:
        funds = _check_funds(db, maker, fund_ids)
        codes = sorted(f.code for f in funds)
        # Funds the maker can't see stay as they are (not theirs to remove).
        hidden = [c for c in current["funds"] if c not in codes and not _maker_sees(db, maker, c)]
        codes = sorted(set(codes) | set(hidden))
        if codes != current["funds"]:
            changes["funds"] = codes
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing has changed")
    request = approvals.submit(
        db, maker, KIND, entity_type="user", entity_id=user.id,
        summary=f"Change principal officer {user.full_name or user.email}: {', '.join(k.replace('_', ' ') for k in changes)}",
        payload={"action": "update", **changes},
        previous={k: current[k] for k in changes},
        fund_id=_scope(funds) if funds else None,
    )
    db.commit()
    db.refresh(request)
    return request


def _maker_sees(db: Session, maker: User, code: str) -> bool:
    fund_id = db.execute(select(Fund.id).where(Fund.code == code)).scalar_one_or_none()
    return fund_id is not None and fund_access.can_access(db, maker, fund_id)


def _fund_names(db: Session, codes: list[str]) -> str:
    names = list(db.execute(select(Fund.name).where(Fund.code.in_(codes)).order_by(Fund.name)).scalars())
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _apply(db: Session, request: ApprovalRequest, checker: User) -> None:
    data = request.payload
    if data["action"] == "create":
        if identity.find_by_email(db, data["email"]) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "A login with this email was created in the meantime")
        # Nobody knows this password: the officer sets theirs from the emailed link.
        user = identity.create_user(db, data["email"], secrets.token_urlsafe(32), [UserRole.principal_officer],
                                    full_name=data["full_name"], phone=data.get("phone"))
        request.entity_id = str(user.id)
        fund_access.set_access(db, user.id, _fund_ids(db, data["funds"]), checker.id)
        token = passwords.issue_token(db, user, "invite", checker.id)
        notifications.notify_invite(
            db, user, token, passwords.INVITE_DAYS,
            intro=f"You have been registered as a principal officer with {_fund_names(db, data['funds'])}. "
                  "Once you have signed in you can apply for your employer to join, send contribution schedules "
                  "and look after your members online.")
        audit.record(db, checker.id, "user", user.id, "created",
                     after={**snapshot(db, user), "roles": ["principal_officer"]})
        return

    user = db.get(User, uuid.UUID(request.entity_id))
    if user is None or not user.has_role(UserRole.principal_officer):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That principal officer no longer exists")
    before = snapshot(db, user)
    if "full_name" in data:
        user.full_name = data["full_name"]
    if "phone" in data:
        user.phone = data["phone"]
    if "funds" in data:
        added = sorted(set(data["funds"]) - set(before["funds"]))
        fund_access.set_access(db, user.id, _fund_ids(db, data["funds"]), checker.id)
        if added and user.status == UserStatus.active:
            notifications.notify_officer_funds_added(db, user, _fund_names(db, added))
    db.flush()
    audit.record(db, checker.id, "user", user.id, "updated", before=before, after=snapshot(db, user))


approvals.register(approvals.ApprovalKind(
    name=KIND, label="Principal officer access", checker_roles=frozenset({UserRole.scheme_config_checker}), apply=_apply,
))
