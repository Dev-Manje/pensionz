"""Messages the platform sends (pz-notifications skill). Every function here
writes rows only — an in-app inbox entry and/or an outbox row the worker
delivers — and never commits: call it before the service's db.commit(), so a
rolled-back action sends nothing.

Add one `notify_<event>` per event; keep wording plain and never put
passwords, ID or account numbers in a message."""
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings

from app.models.identity import User, UserRole, UserStatus, UserRoleAssignment
from app.models.notification import NotificationChannel, NotificationOutbox, UserNotification

# Events whose link carries a secret (password links): kept out of the inbox
# and wiped from the outbox once delivered.
PRIVATE_LINK_EVENTS = frozenset({"auth.password_reset_link", "auth.invite"})


def _email(db: Session, user: User, event: str, subject: str, body: str, *, link: str | None = None,
           entity_type: str | None = None, entity_id: object | None = None) -> None:
    db.add(NotificationOutbox(
        event=event, channel=NotificationChannel.email, recipient_user_id=user.id, recipient_address=user.email,
        subject=subject, body=body, link=link, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
    ))


def _notify(db: Session, user: User, event: str, title: str, body: str, *, link: str | None = None,
            entity_type: str | None = None, entity_id: object | None = None, email: bool = True) -> None:
    """In-app inbox entry plus (by default) the same message by email."""
    db.add(UserNotification(
        user_id=user.id, event=event, title=title, body=body, link=link, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
    ))
    if email:
        _email(db, user, event, title, body, link=link, entity_type=entity_type, entity_id=entity_id)


def users_with_roles(db: Session, roles: set[UserRole], exclude: set[uuid.UUID] = frozenset()) -> list[User]:
    """Active users holding any of `roles`, minus `exclude` (e.g. the maker)."""
    query = (
        db.query(User)
        .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
        .filter(UserRoleAssignment.role.in_(roles), User.status == UserStatus.active)
    )
    if exclude:
        query = query.filter(User.id.notin_(exclude))
    return query.distinct().all()


# --- auth ---------------------------------------------------------------------

def notify_password_reset_link(db: Session, user: User, token: str, hours: int) -> None:
    _email(db, user, "auth.password_reset_link", "Reset your password",
           f"We received a request to reset your password. The link below works once, for {hours} hour(s).\n"
           "If you didn't ask for this, ignore this email — your password stays the same.",
           link=f"/reset-password?token={token}")


def notify_invite(db: Session, user: User, token: str, days: int) -> None:
    _email(db, user, "auth.invite", f"You have been given access to {settings.brand_name}",
           f"An account has been created for you. Use the link below to choose your password; it works once, for {days} days.",
           link=f"/reset-password?token={token}")


def notify_password_changed(db: Session, user: User, how: str) -> None:
    verb = {"changed": "was changed", "reset": "was reset", "set": "has been set"}.get(how, "was changed")
    _notify(db, user, "auth.password_changed", f"Your password {verb}",
            f"Your password {verb}. If this wasn't you, contact {settings.brand_administrator} straight away.",
            entity_type="user", entity_id=user.id)


# --- approvals ----------------------------------------------------------------

def notify_approval_needed(db: Session, checkers: list[User], summary: str, request_id: uuid.UUID) -> None:
    for checker in checkers:
        _notify(db, checker, "approval.needed", "Approval needed", summary,
                link=f"/approvals/{request_id}", entity_type="approval_request", entity_id=request_id)


def notify_approval_decided(db: Session, maker: User, summary: str, approved: bool, comment: str | None,
                            request_id: uuid.UUID) -> None:
    outcome = "approved" if approved else "rejected"
    body = f"{summary} — {outcome}." + (f" Comment: {comment}" if comment else "")
    _notify(db, maker, f"approval.{outcome}", f"Request {outcome}", body,
            link=f"/approvals/{request_id}", entity_type="approval_request", entity_id=request_id)


# --- KYC ----------------------------------------------------------------------

def notify_kyc_submitted(db: Session, reviewers: list[User], reference: str, name: str, application_id: uuid.UUID) -> None:
    for reviewer in reviewers:
        _notify(db, reviewer, "kyc.submitted", "KYC application to review", f"{reference} — {name} was submitted for review.",
                link=f"/kyc/{application_id}", entity_type="kyc_application", entity_id=application_id)


def notify_kyc_returned(db: Session, user: User, reference: str, note: str, application_id: uuid.UUID) -> None:
    _notify(db, user, "kyc.returned", "Your KYC application needs changes",
            f"{reference} was sent back: {note} Please update it and submit again.",
            link=f"/kyc/{application_id}", entity_type="kyc_application", entity_id=application_id)


def notify_kyc_senior_approval(db: Session, approvers: list[User], reference: str, name: str, application_id: uuid.UUID) -> None:
    for approver in approvers:
        _notify(db, approver, "kyc.senior_approval", "High-risk KYC needs your approval",
                f"{reference} — {name} is rated high risk; compliance recommends approval after enhanced due diligence.",
                link=f"/kyc/{application_id}", entity_type="kyc_application", entity_id=application_id)


def notify_kyc_decided(db: Session, user: User, reference: str, approved: bool, reason: str | None, application_id: uuid.UUID) -> None:
    outcome = "approved" if approved else "not approved"
    _notify(db, user, f"kyc.{'approved' if approved else 'rejected'}", f"KYC application {outcome}",
            f"{reference} was {outcome}." + (f" Reason: {reason}" if reason else ""),
            link=f"/kyc/{application_id}", entity_type="kyc_application", entity_id=application_id)


def notify_kyc_expiring_digest(db: Session, staff: list[User], lines: list[str]) -> None:
    for user in staff:
        _notify(db, user, "kyc.expiring", f"KYC: {len(lines)} item(s) need attention", "\n".join(lines[:30]), link="/kyc?tab=expiring")


def notify_kyc_document_expiring(db: Session, user: User, label: str, when: str) -> None:
    _notify(db, user, "kyc.document_expiring", "Please update your document",
            f"Your {label} expires {when}. Upload a current one so your records stay up to date.")
