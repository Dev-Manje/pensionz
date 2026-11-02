"""Participating employers / schemes (FR-CFG-003) through maker-checker.

The maker sends the whole scheme — details and the principal officers who act
for it — as one snapshot (approval kind "scheme_setup", checker: scheme
setup checker who administers the fund). Linking an officer gives them portal
access to the scheme, which is why it is part of the approved snapshot.

Principal officers (FR-PRT-006): one officer may act for several employers in
one or more funds, and an employer may have several officers. The maker links
existing officers or names new ones (name, email, phone); on approval a new
officer gets a principal-officer login and an invitation, while an email that
already belongs to a principal officer just links that login."""
import secrets
import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.fund import Fund, FundStatus
from app.models.identity import User, UserRole, UserStatus
from app.models.kyc import ClientType, Party
from app.models.scheme import BillingFrequency, Scheme, SchemeOfficer, SchemeStatus
from app.schemas.scheme import SchemeIn
from app.services import approvals, audit, identity, notifications, passwords

KIND = "scheme_setup"

SCHEME_FIELDS = (
    "code", "name", "status", "registration_number", "tpin", "join_date", "exit_date",
    "contribution_day", "billing_frequency",
    "address_line1", "address_line2", "address_line3", "phone", "email",
    "contact_name", "contact_email", "contact_phone", "party_id",
)


def pending_request_id(db: Session, scheme_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(ApprovalRequest.id).where(
            ApprovalRequest.kind == KIND, ApprovalRequest.entity_id == str(scheme_id), ApprovalRequest.status == ApprovalStatus.pending,
        )
    ).scalar_one_or_none()


def _officer_row(user: User) -> dict:
    return {"user_id": str(user.id), "full_name": user.full_name or user.email, "email": user.email}


def _existing_officer(db: Session, email: str) -> User | None:
    """The login behind an email, if it may be linked; 400 if the email
    belongs to someone who can't act as a principal officer."""
    user = identity.find_by_email(db, email)
    if user is None:
        return None
    if not user.has_role(UserRole.principal_officer):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"{email} already has a login without the principal officer role — ask an administrator to add the role")
    if user.status != UserStatus.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{user.full_name or user.email} isn't an active user")
    return user


def snapshot(scheme: Scheme) -> dict:
    return audit._jsonable({
        **{f: getattr(scheme, f) for f in SCHEME_FIELDS},
        "principal_officers": sorted((_officer_row(o.user) for o in scheme.officers), key=lambda o: o["email"]),
    })


def officer_candidates(db: Session) -> list[User]:
    """Active users with the principal officer role, for the picker."""
    from app.models.identity import UserRoleAssignment

    return list(db.execute(
        select(User).join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
        .where(UserRoleAssignment.role == UserRole.principal_officer, User.status == UserStatus.active)
        .order_by(func.lower(User.full_name), User.email)
    ).scalars().unique())


def _check_party(db: Session, party_id: uuid.UUID | None) -> None:
    if party_id is None:
        return
    party = db.get(Party, party_id)
    if party is None or party.client_type != ClientType.corporate:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Link an approved corporate KYC client")


def _proposed(db: Session, data: SchemeIn) -> dict:
    _check_party(db, data.party_id)
    officers = []
    for user_id in dict.fromkeys(data.officer_ids):  # de-duplicated, order kept
        user = db.get(User, user_id)
        if user is None or not user.has_role(UserRole.principal_officer):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only users with the principal officer role can be linked to an employer")
        if user.status != UserStatus.active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{user.full_name or user.email} isn't an active user")
        officers.append(_officer_row(user))
    linked = {o["email"] for o in officers}
    for new in data.new_officers:
        email = new.email.strip().lower()
        if email in linked:
            continue
        linked.add(email)
        existing = _existing_officer(db, email)
        # An existing officer (perhaps acting for other employers or funds) is
        # linked, not invited again.
        officers.append(_officer_row(existing) if existing else
                        {"user_id": None, "full_name": new.full_name, "email": email, "phone": new.phone, "invite": True})
    return audit._jsonable({
        **data.model_dump(include=set(SCHEME_FIELDS)),
        "principal_officers": sorted(officers, key=lambda o: o["email"]),
    })


def _check_code_free(db: Session, fund_id: uuid.UUID, code: str, scheme_id: uuid.UUID | None, ignore_request: uuid.UUID | None = None) -> None:
    taken = db.execute(
        select(Scheme.id).where(Scheme.fund_id == fund_id, func.upper(Scheme.code) == code.upper())
    ).scalar_one_or_none()
    if taken is not None and taken != scheme_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Employer code {code} is already used in this fund")
    waiting = db.execute(
        select(ApprovalRequest.id, ApprovalRequest.entity_id).where(
            ApprovalRequest.kind == KIND, ApprovalRequest.status == ApprovalStatus.pending,
            ApprovalRequest.fund_id == fund_id, func.upper(ApprovalRequest.payload["code"].astext) == code.upper(),
        )
    ).all()
    for request_id, entity_id in waiting:
        same = scheme_id is not None and entity_id == str(scheme_id)
        if request_id != ignore_request and not same:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Employer code {code} is already used by an employer waiting for approval")


def propose_new(db: Session, maker: User, fund: Fund, data: SchemeIn) -> ApprovalRequest:
    if fund.status != FundStatus.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This fund isn't taking new employers (it is closed to new members or wound up)")
    if data.status != SchemeStatus.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A new employer starts as active")
    _check_code_free(db, fund.id, data.code, None)
    proposed = _proposed(db, data)
    request = approvals.submit(
        db, maker, KIND, entity_type="scheme", entity_id=None,
        summary=f"New employer {data.code} — {data.name} in fund {fund.code}",
        payload={"action": "create", "fund_id": str(fund.id), **proposed},
        fund_id=fund.id,
    )
    db.commit()
    db.refresh(request)
    return request


def propose_update(db: Session, maker: User, scheme: Scheme, data: SchemeIn) -> ApprovalRequest:
    current = snapshot(scheme)
    proposed = _proposed(db, data)
    changed = [k for k in proposed if proposed[k] != current.get(k)]
    if not changed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing has changed")
    if "code" in changed:
        _check_code_free(db, scheme.fund_id, data.code, scheme.id)
    request = approvals.submit(
        db, maker, KIND, entity_type="scheme", entity_id=scheme.id,
        summary=f"Change employer {scheme.code}: {', '.join(k.replace('_', ' ') for k in changed)}"[:300],
        payload={"action": "update", **proposed},
        previous=current,
        fund_id=scheme.fund_id,
    )
    db.commit()
    db.refresh(request)
    return request


def _values(data: dict) -> dict:
    values = {f: data.get(f) for f in SCHEME_FIELDS}
    values["status"] = SchemeStatus(values["status"])
    values["billing_frequency"] = BillingFrequency(values["billing_frequency"])
    for f in ("join_date", "exit_date"):
        values[f] = date.fromisoformat(values[f]) if values[f] else None
    values["party_id"] = uuid.UUID(values["party_id"]) if values.get("party_id") else None
    return values


def _officer_for(db: Session, row: dict, scheme: Scheme, fund: Fund, checker: User) -> tuple[uuid.UUID, bool]:
    """(user id, invited now)."""
    if row.get("user_id"):
        return uuid.UUID(row["user_id"]), False
    # Invited in this request — unless the email got a login in the meantime
    # (e.g. invited for another employer approved first).
    existing = _existing_officer(db, row["email"])
    if existing is not None:
        return existing.id, False
    # Nobody knows this password: the officer sets theirs from the emailed link.
    user = identity.create_user(db, row["email"], secrets.token_urlsafe(32), [UserRole.principal_officer],
                                full_name=row["full_name"], phone=row.get("phone"))
    token = passwords.issue_token(db, user, "invite", checker.id)
    notifications.notify_invite(db, user, token, passwords.INVITE_DAYS,
                                intro=f"You have been registered as a principal officer of {scheme.name} in {fund.name}, "
                                      "to send contribution schedules and look after its members online.")
    audit.record(db, checker.id, "user", user.id, "created",
                 after={"email": user.email, "full_name": user.full_name, "roles": ["principal_officer"], "scheme": scheme.code})
    return user.id, True


def _sync_officers(db: Session, scheme: Scheme, officers: list[dict], checker: User) -> None:
    fund = db.get(Fund, scheme.fund_id)
    resolved = [_officer_for(db, row, scheme, fund, checker) for row in officers]
    wanted = {user_id for user_id, _ in resolved}
    invited_now = {user_id for user_id, invited in resolved if invited}
    for link in list(scheme.officers):
        if link.user_id not in wanted:
            notifications.notify_portal_scheme_unlinked(db, link.user, scheme.name, fund.name)
            scheme.officers.remove(link)
    have = {link.user_id for link in scheme.officers}
    for user_id in wanted - have:
        scheme.officers.append(SchemeOfficer(user_id=user_id))
        if user_id not in invited_now:  # the invitation already says which employer
            notifications.notify_portal_scheme_linked(db, db.get(User, user_id), scheme.name, fund.name)


def _apply(db: Session, request: ApprovalRequest, checker: User) -> None:
    data = request.payload
    if data["action"] == "create":
        fund = db.get(Fund, uuid.UUID(data["fund_id"]))
        if fund is None or fund.status != FundStatus.active:
            raise HTTPException(status.HTTP_409_CONFLICT, "The fund is no longer taking new employers")
        _check_code_free(db, fund.id, data["code"], None, ignore_request=request.id)
        scheme = Scheme(fund_id=fund.id, **_values(data))
        db.add(scheme)
        db.flush()
        _sync_officers(db, scheme, data["principal_officers"], checker)
        request.entity_id = str(scheme.id)
        db.flush()
        db.refresh(scheme)
        audit.record(db, checker.id, "scheme", scheme.id, "created", after=snapshot(scheme), fund_id=fund.id)
        return

    scheme = db.execute(select(Scheme).where(Scheme.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one_or_none()
    if scheme is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That employer no longer exists")
    before = snapshot(scheme)
    values = _values(data)
    if values["code"] != scheme.code:
        _check_code_free(db, scheme.fund_id, values["code"], scheme.id, ignore_request=request.id)
    for field, value in values.items():
        setattr(scheme, field, value)
    _sync_officers(db, scheme, data["principal_officers"], checker)
    db.flush()
    db.refresh(scheme)
    audit.record(db, checker.id, "scheme", scheme.id, "updated", before=before, after=snapshot(scheme), fund_id=scheme.fund_id)


approvals.register(approvals.ApprovalKind(
    name=KIND, label="Employer (scheme) setup", checker_roles=frozenset({UserRole.scheme_config_checker}), apply=_apply,
))
