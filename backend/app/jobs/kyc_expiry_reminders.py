"""Daily KYC reminders (FR-ONB-104): periodic reviews coming due and identity
documents / permits about to expire — 30 and 7 days before, on the day, and
weekly once overdue. Compliance gets one digest; a portal applicant is told
about their own documents."""
from datetime import date

from sqlalchemy.orm import Session

from app.models.identity import User
from app.models.kyc import KycApplication
from app.services import kyc, kyc_expiry, notifications


def _when(days_left: int) -> str:
    if days_left > 0:
        return f"in {days_left} day{'s' if days_left != 1 else ''}"
    if days_left == 0:
        return "today"
    return f"{-days_left} day{'s' if days_left != -1 else ''} ago"


def run(db: Session, as_of: date) -> str:
    items = [i for i in kyc_expiry.expiring(db, as_of, within_days=31) if kyc_expiry.remind_today(i)]
    if not items:
        return "nothing due"
    lines = [f"{i.party_name}: {i.label} due {_when(i.days_left)}" for i in items]
    compliance = notifications.users_with_roles(db, {kyc.REVIEW_ROLE})
    notifications.notify_kyc_expiring_digest(db, compliance, lines)
    applicants = 0
    for item in items:
        if item.kind != "document" or item.application_id is None:
            continue
        app = db.get(KycApplication, item.application_id)
        user = db.get(User, app.applicant_user_id) if app and app.applicant_user_id else None
        if user is not None:
            applicants += 1
            notifications.notify_kyc_document_expiring(db, user, item.label.lower(), _when(item.days_left))
    db.commit()
    return f"{len(items)} reminder item(s); {len(compliance)} compliance user(s), {applicants} applicant(s) notified"
