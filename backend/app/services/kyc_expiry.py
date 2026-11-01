"""KYC review dates and expiring evidence (FR-ONB-104).

`expiring()` lists what needs attention: approved clients whose periodic KYC
review is due, and the identity documents / immigration permits on their
latest approved application that are about to expire (or have). The daily
job (app/jobs/kyc_expiry_reminders.py) turns it into reminders."""
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kyc import KycApplication, KycDocument, Party
from app.services import kyc_forms

# Reminders go out this many days before the date, on the date, and weekly once overdue.
REMIND_DAYS_BEFORE = (30, 7, 0)
OVERDUE_EVERY_DAYS = 7


@dataclass
class Expiring:
    kind: str  # "review" | "document"
    party_id: uuid.UUID
    party_name: str
    label: str
    due: date
    days_left: int
    application_id: uuid.UUID | None


def expiring(db: Session, as_of: date, within_days: int = 60) -> list[Expiring]:
    horizon = as_of + timedelta(days=within_days)
    out: list[Expiring] = []
    for party in db.execute(select(Party).where(Party.kyc_review_due <= horizon)).scalars():
        out.append(Expiring("review", party.id, party.name, "Periodic KYC review", party.kyc_review_due,
                            (party.kyc_review_due - as_of).days, party.latest_application_id))
    rows = db.execute(
        select(KycDocument, Party, KycApplication)
        .join(KycApplication, KycApplication.id == KycDocument.application_id)
        .join(Party, Party.latest_application_id == KycApplication.id)
        .where(KycDocument.superseded.is_(False), KycDocument.expiry_date.is_not(None), KycDocument.expiry_date <= horizon)
    ).all()
    for doc, party, app in rows:
        slot = next((s for s in kyc_forms.slots(app.client_type, app.data) if s.key == doc.requirement), None)
        label = slot.label if slot else doc.requirement
        out.append(Expiring("document", party.id, party.name, label, doc.expiry_date, (doc.expiry_date - as_of).days, app.id))
    return sorted(out, key=lambda e: (e.due, e.party_name))


def remind_today(item: Expiring) -> bool:
    if item.days_left in REMIND_DAYS_BEFORE:
        return True
    return item.days_left < 0 and (-item.days_left) % OVERDUE_EVERY_DAYS == 0
