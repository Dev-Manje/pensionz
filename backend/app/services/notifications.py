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
# Events whose body carries a one-time code: never in the inbox, and the body
# is wiped from the outbox once delivered.
PRIVATE_BODY_EVENTS = frozenset({"auth.one_time_code"})


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


def notify_invite(db: Session, user: User, token: str, days: int, *, intro: str | None = None) -> None:
    _email(db, user, "auth.invite", f"You have been given access to {settings.brand_name}",
           (intro or "An account has been created for you.")
           + f" Use the link below to choose your password; it works once, for {days} days.",
           link=f"/reset-password?token={token}")


def notify_one_time_code(db: Session, user: User, code: str, minutes: int, reason: str) -> None:
    """Email only for now; SMS to the user's phone once a gateway is chosen."""
    _email(db, user, "auth.one_time_code", f"Your {settings.brand_name} one-time code",
           f"Your one-time code to {reason} is {code}. It works once, for {minutes} minutes.\n"
           f"Never share it — {settings.brand_administrator} will never ask you for it. "
           "If you didn't try to do this, change your password.")


def notify_officer_funds_added(db: Session, user: User, fund_names: str) -> None:
    _notify(db, user, "portal.officer_funds_added", f"You can now apply to {fund_names}",
            f"You can now apply for an employer to join {fund_names} from your portal.", link="/po")


def notify_portal_scheme_linked(db: Session, user: User, scheme_name: str, fund_name: str) -> None:
    _notify(db, user, "portal.scheme_linked", f"You can now act for {scheme_name}",
            f"You have been linked to {scheme_name} in {fund_name} as a principal officer. "
            "It is now listed under My schemes when you sign in.", link="/po")


def notify_portal_scheme_unlinked(db: Session, user: User, scheme_name: str, fund_name: str) -> None:
    _notify(db, user, "portal.scheme_unlinked", f"You no longer act for {scheme_name}",
            f"You have been removed as a principal officer of {scheme_name} in {fund_name}. "
            f"If this is a mistake, contact {settings.brand_administrator}.")


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
    # Principal officers follow their requests in the portal, not on the staff approvals screen.
    portal_only = not maker.is_staff and maker.has_role(UserRole.principal_officer)
    _notify(db, maker, f"approval.{outcome}", f"Request {outcome}", body,
            link=f"/po/requests/{request_id}" if portal_only else f"/approvals/{request_id}",
            entity_type="approval_request", entity_id=request_id)


# --- KYC ----------------------------------------------------------------------

def notify_kyc_submitted(db: Session, reviewers: list[User], reference: str, name: str, application_id: uuid.UUID) -> None:
    for reviewer in reviewers:
        _notify(db, reviewer, "kyc.submitted", "KYC application to review", f"{reference} — {name} was submitted for review.",
                link=f"/kyc/{application_id}", entity_type="kyc_application", entity_id=application_id)


def notify_kyc_returned(db: Session, user: User, reference: str, note: str, application_id: uuid.UUID, link: str) -> None:
    _notify(db, user, "kyc.returned", "Your KYC application needs changes",
            f"{reference} was sent back: {note} Please update it and submit again.",
            link=link, entity_type="kyc_application", entity_id=application_id)


def notify_kyc_senior_approval(db: Session, approvers: list[User], reference: str, name: str, application_id: uuid.UUID) -> None:
    for approver in approvers:
        _notify(db, approver, "kyc.senior_approval", "High-risk KYC needs your approval",
                f"{reference} — {name} is rated high risk; compliance recommends approval after enhanced due diligence.",
                link=f"/kyc/{application_id}", entity_type="kyc_application", entity_id=application_id)


def notify_kyc_decided(db: Session, user: User, reference: str, approved: bool, reason: str | None, application_id: uuid.UUID,
                       link: str) -> None:
    outcome = "approved" if approved else "not approved"
    _notify(db, user, f"kyc.{'approved' if approved else 'rejected'}", f"KYC application {outcome}",
            f"{reference} was {outcome}." + (f" Reason: {reason}" if reason else ""),
            link=link, entity_type="kyc_application", entity_id=application_id)


def notify_kyc_expiring_digest(db: Session, staff: list[User], lines: list[str]) -> None:
    for user in staff:
        _notify(db, user, "kyc.expiring", f"KYC: {len(lines)} item(s) need attention", "\n".join(lines[:30]), link="/kyc?tab=expiring")


def notify_kyc_document_expiring(db: Session, user: User, label: str, when: str) -> None:
    _notify(db, user, "kyc.document_expiring", "Please update your document",
            f"Your {label} expires {when}. Upload a current one so your records stay up to date.")


# --- employers (principal officers) — FR-NOT-003 ------------------------------


def notify_officers(db: Session, officers: list[User], event: str, title: str, body: str, *, link: str | None,
                    entity_type: str | None = None, entity_id: object | None = None) -> None:
    for officer in officers:
        _notify(db, officer, event, title, body, link=link, entity_type=entity_type, entity_id=entity_id)


def notify_schedule_due(db: Session, officers: list[User], scheme_name: str, month_label: str, due: str, missing: str,
                        scheme_id: uuid.UUID) -> None:
    notify_officers(db, officers, "employer.schedule_due", f"{scheme_name}: {month_label} contributions due {due}",
                    f"{month_label} contributions are due {due}. Still to do: {missing}.",
                    link=f"/po/schemes/{scheme_id}", entity_type="scheme", entity_id=scheme_id)


def notify_arrears(db: Session, officers: list[User], scheme_name: str, total: str, months: str, interest: str | None,
                   scheme_id: uuid.UUID) -> None:
    notify_officers(db, officers, "employer.arrears", f"{scheme_name}: contributions overdue {total}",
                    f"{scheme_name} owes {total} in contributions ({months})." +
                    (f" Late-payment interest so far: {interest}." if interest else "") +
                    " Please send the schedules and pay, or contact us if this is wrong.",
                    link=f"/po/schemes/{scheme_id}?tab=statements", entity_type="scheme", entity_id=scheme_id)


def notify_arrears_escalation(db: Session, staff: list[User], scheme_label: str, total: str, oldest: str, fund_id: uuid.UUID) -> None:
    for user in staff:
        _notify(db, user, "employer.arrears_escalated", f"Arrears: {scheme_label}",
                f"{scheme_label} owes {total}; the oldest unpaid month is {oldest}. The employer has been reminded.",
                link=f"/contributions?fund={fund_id}&tab=arrears", email=False)
