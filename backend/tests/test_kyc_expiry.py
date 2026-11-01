"""KYC review dates and expiring documents (FR-ONB-104)."""
from datetime import date, datetime, timedelta, timezone

from app.jobs import kyc_expiry_reminders
from app.models.identity import UserRole
from app.models.kyc import ClientType, KycApplication, KycDocument, Party, RiskRating
from app.models.notification import UserNotification
from app.services import kyc_expiry
from tests.factories import auth_headers, make_user

TODAY = date(2026, 11, 2)


def make_party(db, *, review_due: date, id_expiry: date | None = None, applicant=None):
    app = KycApplication(reference=f"KYC-T-{review_due.isoformat()}", client_type=ClientType.individual, status="approved",
                         data={"first_name": "Ann", "last_name": "Phiri", "nationality": "MW"}, display_name="Ann Phiri",
                         applicant_user_id=applicant.id if applicant else None)
    db.add(app)
    db.flush()
    party = Party(client_type=ClientType.individual, name="Ann Phiri", risk_rating=RiskRating.low, kyc_approved_at=datetime.now(timezone.utc),
                  kyc_review_due=review_due, latest_application_id=app.id)
    db.add(party)
    if id_expiry:
        db.add(KycDocument(application_id=app.id, requirement="identity_document", doc_type="national_id", expiry_date=id_expiry,
                           storage_key="k", filename="id.pdf", content_type="application/pdf", size_bytes=1, sha256="0" * 64,
                           uploaded_at=datetime.now(timezone.utc)))
    db.flush()
    return party


def test_expiring_lists_reviews_and_documents(db):
    make_party(db, review_due=TODAY + timedelta(days=7), id_expiry=TODAY + timedelta(days=30))
    make_party(db, review_due=TODAY + timedelta(days=400))  # not yet
    items = kyc_expiry.expiring(db, TODAY, within_days=60)
    assert [(i.kind, i.days_left) for i in items] == [("review", 7), ("document", 30)]
    assert items[1].label == "Identity document"


def test_reminder_days():
    item = lambda d: kyc_expiry.Expiring("review", None, "x", "y", TODAY, d, None)  # noqa: E731
    assert [d for d in range(-15, 35) if kyc_expiry.remind_today(item(d))] == [-14, -7, 0, 7, 30]


def test_job_notifies_compliance_and_the_applicant(db):
    compliance = make_user(db, UserRole.compliance)
    applicant = make_user(db, UserRole.individual)
    make_party(db, review_due=TODAY + timedelta(days=30), id_expiry=TODAY + timedelta(days=7), applicant=applicant)
    make_party(db, review_due=TODAY + timedelta(days=12))  # not a reminder day
    summary = kyc_expiry_reminders.run(db, TODAY)
    assert summary.startswith("2 reminder item(s)")
    digest = db.query(UserNotification).filter_by(user_id=compliance.id, event="kyc.expiring").one()
    assert "Periodic KYC review due in 30 days" in digest.body and "Identity document due in 7 days" in digest.body
    assert db.query(UserNotification).filter_by(user_id=applicant.id, event="kyc.document_expiring").count() == 1


def test_job_quiet_when_nothing_due(db):
    assert kyc_expiry_reminders.run(db, TODAY) == "nothing due"


def test_expiring_endpoint_staff_only(client, db):
    make_party(db, review_due=date.today() + timedelta(days=10))
    staff = make_user(db, UserRole.compliance)
    rows = client.get("/api/v1/kyc/expiring", headers=auth_headers(staff)).json()
    assert rows and rows[0]["kind"] == "review"
    member = make_user(db, UserRole.member)
    assert client.get("/api/v1/kyc/expiring", headers=auth_headers(member)).status_code == 403
