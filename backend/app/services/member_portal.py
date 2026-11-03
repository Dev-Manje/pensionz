"""Member portal access and self-service (FR-PRT-002, FR-PRT-006).

Access:
- **Invite** (member administration): a member-role login for the email on the
  member record, linked through `member.portal_user_id`, with an invitation email.
  Direct action, no checker — it only lets the member see their own records;
  anything they change goes through the member checker.
- **Self-register**: member number + ID number + date of birth. When they match
  a member with an email on record, a one-time code goes to that email (never to
  an address typed in), and the code + a new password finish it. The answer is
  the same whether or not anything matched, so the form can't be used to find
  out who is a member.
- One login may hold memberships in several funds (same email on each record).
- Sign-in then needs the emailed code like every portal user.

Self-service (all maker-checker, member checker approves): contact details and
bank details (bank needs a one-time code first), beneficiary nomination, and the
member's individual KYC (change of details / documents).
"""
import secrets
import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.fund import Fund
from app.models.identity import User, UserRole, UserStatus
from app.models.kyc import ClientType, KycApplication, Party
from app.models.member import Member, MemberStatus
from app.models.mixins import utcnow
from app.schemas.member import MemberDetailsIn
from app.services import audit, identity, kyc, members, notifications, otp, passwords

REGISTER = "member_register"
BANK_CHANGE = "bank_change"
CONTACT_FIELDS = ("postal_address", "physical_address", "telephone", "mobile", "email", "preferred_contact")
BANK_FIELDS = members.BANK_FIELDS
INVITERS = (UserRole.member_admin, UserRole.admin)


def memberships(db: Session, user: User) -> list[Member]:
    return list(db.execute(select(Member).where(Member.portal_user_id == user.id).order_by(Member.account_code)).scalars())


def require_member(db: Session, user: User, member_id: uuid.UUID) -> Member:
    member = db.get(Member, member_id)
    if member is None or member.portal_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")
    return member


# ---- access


def _login_for(db: Session, email: str, full_name: str, phone: str | None) -> tuple[User, bool]:
    """(the member login for this email, created now). 409 if the email belongs to someone who isn't a member."""
    user = identity.find_by_email(db, email)
    if user is not None:
        if not user.has_role(UserRole.member):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"{email} already has a login without the member role — ask an administrator to add the role")
        if user.status != UserStatus.active:
            raise HTTPException(status.HTTP_409_CONFLICT, f"The login for {email} isn't active")
        return user, False
    # Nobody knows this password: the member sets theirs from the emailed link or code.
    return identity.create_user(db, email, secrets.token_urlsafe(32), [UserRole.member], full_name=full_name, phone=phone), True


def invite(db: Session, staff: User, member: Member) -> User:
    if not member.email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Record the member's email address first (Correct details)")
    if member.status == MemberStatus.deceased:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This member is deceased")
    if member.portal_user_id:
        linked = db.get(User, member.portal_user_id)
        if linked and linked.email.lower() == member.email.lower():
            raise HTTPException(status.HTTP_409_CONFLICT, "This member already has portal access — send a password link from Users if needed")
    user, created = _login_for(db, member.email.strip().lower(), member.full_name, member.mobile)
    member.portal_user_id = user.id
    fund = db.get(Fund, member.fund_id)
    if created or (user.password_changed_at is None and user.last_login_at is None):
        token = passwords.issue_token(db, user, "invite", staff.id)
        notifications.notify_invite(db, user, token, passwords.INVITE_DAYS,
                                    intro=f"You can now see your savings in {fund.name} (member {member.account_code}) online.")
    else:
        notifications._notify(db, user, "member.linked", f"{fund.name} added to your account",
                              f"Your membership {member.account_code} in {fund.name} is now on your portal.", link="/member")
    audit.record(db, staff.id, "member", member.id, "portal_invited", after={"email": user.email, "created": created}, fund_id=member.fund_id)
    db.commit()
    return user


def _match(db: Session, member_number: str, id_number: str, born: date) -> Member | None:
    key = members.id_key(id_number)
    if not key:
        return None
    number = member_number.strip().upper()
    rows = db.execute(select(Member).where(
        or_(func.upper(Member.account_code) == number, func.upper(Member.old_member_no) == number),
        Member.id_number_key == key, Member.date_of_birth == born, Member.status != MemberStatus.deceased,
    )).scalars().all()
    return rows[0] if len(rows) == 1 else None


def register_start(db: Session, member_number: str, id_number: str, born: date) -> uuid.UUID:
    """The subject of the registration challenge: the member's login if the details
    matched (a code is on its way), else a random id that can never verify."""
    member = _match(db, member_number, id_number, born)
    if member is None or not member.email:
        audit.record(db, None, "member", member.id if member else None, "portal_register_no_match",
                     after={"member_number": member_number.strip()[:30], "has_email": bool(member and member.email)})
        db.commit()
        return uuid.uuid4()
    try:
        user, created = _login_for(db, member.email.strip().lower(), member.full_name, member.mobile)
    except HTTPException:
        audit.record(db, None, "member", member.id, "portal_register_email_taken", fund_id=member.fund_id)
        db.commit()
        return uuid.uuid4()
    member.portal_user_id = user.id
    otp.send(db, user, REGISTER, "finish registering for the member portal")
    audit.record(db, None, "member", member.id, "portal_register_started", after={"created_login": created}, fund_id=member.fund_id)
    db.commit()
    return user.id


def register_finish(db: Session, user_id: uuid.UUID, code: str, new_password: str) -> User:
    user = db.get(User, user_id)
    if user is None or not user.has_role(UserRole.member) or user.status != UserStatus.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code isn't right — start again")
    otp.verify(db, user, REGISTER, code)
    passwords.check_policy(new_password, user.email)
    passwords._set_password(db, user, new_password)
    user.last_login_at = utcnow()
    audit.record(db, user.id, "user", user.id, "portal_registered")
    db.commit()
    return user


# ---- self-service requests


def _portal_update(db: Session, user: User, member: Member, changes: dict, what: str):
    values = {**members.values_of(member), **changes}
    request = members.propose_update(db, user, member, MemberDetailsIn.model_validate(values))
    request.summary = f"{what} for member {member.account_code} (requested from the member portal)"[:300]
    request.payload = {**request.payload, "_portal": True}
    db.commit()
    db.refresh(request)
    return request


def request_contact_change(db: Session, user: User, member: Member, changes: dict):
    changes = {k: v for k, v in changes.items() if k in CONTACT_FIELDS}
    return _portal_update(db, user, member, changes, "Change of contact details")


def send_bank_code(db: Session, user: User) -> str:
    otp.send(db, user, BANK_CHANGE, "change the bank account for your pension payments")
    db.commit()
    return otp.masked_destination(user)


def request_bank_change(db: Session, user: User, member: Member, changes: dict, code: str):
    changes = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in changes.items() if k in BANK_FIELDS}
    if not changes.get("bank_id") or not changes.get("bank_account_number") or not changes.get("bank_account_name"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give the bank, the account name and the account number")
    otp.verify(db, user, BANK_CHANGE, code)
    return _portal_update(db, user, member, changes, "Change of bank details")


def requests(db: Session, user: User, member: Member) -> list[ApprovalRequest]:
    return list(db.execute(select(ApprovalRequest).where(
        ApprovalRequest.initiated_by_user_id == user.id, ApprovalRequest.entity_id == str(member.id),
    ).order_by(ApprovalRequest.created_at.desc()).limit(50)).scalars())


def start_kyc(db: Session, user: User, member: Member) -> KycApplication:
    """The member's individual KYC: a change of the approved details (documents
    carried over) when they are a KYC client, else a first application."""
    party = db.get(Party, member.party_id) if member.party_id else None
    open_app = db.execute(select(KycApplication).where(
        KycApplication.applicant_user_id == user.id, KycApplication.client_type == ClientType.individual,
        KycApplication.status.in_(kyc.OPEN),
    )).scalars().first()
    if open_app is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{open_app.reference} is already in progress — continue that one")
    if party is not None:
        return kyc.start_change_for_party(db, user, party)
    data = {"first_name": member.first_name, "last_name": member.last_name, "date_of_birth": member.date_of_birth.isoformat(),
            "id_number": member.id_number, "email": member.email, "mobile": member.mobile}
    return kyc.create(db, user, ClientType.individual, {k: v for k, v in data.items() if v})


def kyc_applications(db: Session, user: User) -> list[KycApplication]:
    return list(db.execute(select(KycApplication).where(KycApplication.applicant_user_id == user.id)
                           .order_by(KycApplication.created_at.desc())).scalars())

