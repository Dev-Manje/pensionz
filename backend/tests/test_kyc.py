"""KYC onboarding (FR-ONB): drafts, documents, declaration, compliance review,
risk & EDD, approval → party. Files are kept in memory instead of MinIO."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core import storage
from app.models.audit import AuditEvent
from app.models.identity import UserRole
from app.models.kyc import KycApplication, Party
from app.models.notification import UserNotification
from app.models.regulatory import RegulatoryParameterVersion
from tests.factories import auth_headers, make_user

PDF = b"%PDF-1.4 test document"
BASE = "/api/v1/kyc"


@pytest.fixture(autouse=True)
def memory_storage(monkeypatch):
    files: dict[str, bytes] = {}

    def upload(content, content_type, prefix):
        key = f"{prefix}/{len(files)}"
        files[key] = content
        return key

    monkeypatch.setattr(storage, "upload_file", upload)
    monkeypatch.setattr(storage, "download_file", lambda key: files[key])
    return files


@pytest.fixture(autouse=True)
def review_periods(db):
    for rating, years in (("high", 1), ("medium", 2), ("low", 3)):
        db.add(RegulatoryParameterVersion(key=f"kyc_review_years_{rating}", value=Decimal(years), effective_from=date(2020, 1, 1)))
    db.flush()


@pytest.fixture
def capturer(db):
    return make_user(db, UserRole.relationship_manager)


@pytest.fixture
def reviewer(db):
    return make_user(db, UserRole.compliance)


def individual(**overrides):
    data = {
        "first_name": "Chisomo", "last_name": "Banda", "gender": "female", "marital_status": "single", "date_of_birth": "1990-05-04",
        "id_type": "national_id", "id_number": "AB12CD34", "physical_address": "Area 47, Lilongwe", "nationality": "MW",
        "country_of_residence": "MW", "mobile": "0999123456", "preferred_contact": "sms", "income_source": "employment",
        "employer_name": "Chikwawa Tea Estates", "source_of_funds": "Salary", "is_pep": False, "related_to_pep": False,
        "next_of_kin": {"name": "Grace Banda", "relationship": "PARENT"},
    }
    data.update(overrides)
    return data


def corporate(**overrides):
    data = {
        "entity_name": "Lakeshore Logistics Ltd", "entity_form": "private_ltd", "registration_number": "COY-1234", "office_phone": "01820000",
        "email": "info@lakeshore.example", "physical_address": "Plot 10, Blantyre", "contact_name": "HR Manager",
        "contact_phone": "0888000000", "contact_email": "hr@lakeshore.example", "is_pep": False,
        "directors": [{"full_name": "Peter Phiri", "position": "Managing Director", "nationality": "MW"}],
    }
    data.update(overrides)
    return data


def create(client, user, client_type, data):
    response = client.post(f"{BASE}/applications", headers=auth_headers(user), json={"client_type": client_type, "data": data})
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, user, app_id, requirement, doc_type, issue=None, expiry=None, content=PDF):
    form = {"requirement": requirement, "doc_type": doc_type}
    if issue:
        form["issue_date"] = issue
    if expiry:
        form["expiry_date"] = expiry
    return client.post(f"{BASE}/applications/{app_id}/documents", headers=auth_headers(user), data=form,
                       files={"file": ("doc.pdf", content, "application/pdf")})


def recent(days=20):
    return (date.today() - timedelta(days=days)).isoformat()


def complete_individual(client, user, **overrides):
    app = create(client, user, "individual", individual(**overrides))
    assert upload(client, user, app["id"], "identity_document", "national_id", recent(400), (date.today() + timedelta(days=900)).isoformat()).status_code == 201
    assert upload(client, user, app["id"], "proof_of_address", "electricity_bill", recent()).status_code == 201
    return app


def submit(client, user, app_id, client_type="individual"):
    declaration = client.get(f"{BASE}/declarations/{client_type}", headers=auth_headers(user)).json()
    return client.post(f"{BASE}/applications/{app_id}/submit", headers=auth_headers(user),
                       json={"declaration_version_id": declaration["id"], "accepted_by": "Chisomo Banda"})


def test_draft_lists_what_is_missing(client, db, capturer):
    app = create(client, capturer, "individual", {"first_name": "Chisomo"})
    assert app["status"] == "draft" and app["reference"].startswith("KYC-")
    assert "Last name is required" in app["problems"]
    assert "Upload the identity document" in app["problems"]
    assert [s["key"] for s in app["slots"]] == ["identity_document", "proof_of_address"]
    assert submit(client, capturer, app["id"]).status_code == 400


def test_foreign_national_needs_a_permit(client, db, capturer):
    app = create(client, capturer, "individual", individual(nationality="ZM"))
    assert "immigration_permit" in [s["key"] for s in app["slots"]]
    assert "Immigration permit type is required for foreign nationals" in app["problems"]


def test_documents_are_checked(client, db, capturer):
    app = create(client, capturer, "individual", individual())
    assert upload(client, capturer, app["id"], "proof_of_address", "electricity_bill", content=b"not a real file").status_code == 400
    assert upload(client, capturer, app["id"], "proof_of_address", "passport", recent()).status_code == 400  # wrong type list
    assert upload(client, capturer, app["id"], "director_id:0", "passport", recent()).status_code == 400  # not asked for
    stale = upload(client, capturer, app["id"], "proof_of_address", "electricity_bill", recent(200)).json()
    slot = next(s for s in stale["slots"] if s["key"] == "proof_of_address")
    assert slot["problems"] == ["Proof of address: must be issued within the last 3 months"]
    # Re-upload replaces it; the old file stays for the record.
    fresh = upload(client, capturer, app["id"], "proof_of_address", "electricity_bill", recent()).json()
    assert next(s for s in fresh["slots"] if s["key"] == "proof_of_address")["problems"] == []
    assert len(db.get(KycApplication, app["id"]).documents) == 2


def test_submit_records_the_declaration_and_risk(client, db, capturer, reviewer):
    app = complete_individual(client, capturer)
    response = submit(client, capturer, app["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "submitted" and body["risk_rating"] == "low"
    assert body["declaration_accepted_by"] == "Chisomo Banda" and body["declaration_version"] == 1
    assert db.query(UserNotification).filter_by(user_id=reviewer.id, event="kyc.submitted").count() == 1
    # It can't be changed while compliance has it.
    assert client.put(f"{BASE}/applications/{app['id']}", headers=auth_headers(capturer), json={"data": {}}).status_code == 409


def test_stale_declaration_is_refused(client, db, capturer):
    app = complete_individual(client, capturer)
    response = client.post(f"{BASE}/applications/{app['id']}/submit", headers=auth_headers(capturer),
                           json={"declaration_version_id": "00000000-0000-0000-0000-000000000000", "accepted_by": "Chisomo Banda"})
    assert response.status_code == 409


def test_review_return_resubmit_approve(client, db, capturer, reviewer):
    app = complete_individual(client, capturer)
    submit(client, capturer, app["id"])
    # The capturer can't review their own application.
    both = make_user(db, UserRole.compliance, UserRole.relationship_manager)
    own = create(client, both, "individual", individual(first_name="Own"))
    assert client.post(f"{BASE}/applications/{own['id']}/start-review", headers=auth_headers(both)).status_code == 400  # captured it themselves
    finance = make_user(db, UserRole.finance)
    assert client.post(f"{BASE}/applications/{app['id']}/start-review", headers=auth_headers(finance)).status_code == 404  # can't even see it

    state = client.post(f"{BASE}/applications/{app['id']}/start-review", headers=auth_headers(reviewer)).json()
    assert state["status"] == "in_review" and state["can_review"]
    docs = {s["key"]: s["document"]["id"] for s in state["slots"]}
    url = f"{BASE}/applications/{app['id']}/documents"
    assert client.post(f"{url}/{docs['proof_of_address']}/review", headers=auth_headers(reviewer), json={"accept": False}).status_code == 400
    client.post(f"{url}/{docs['proof_of_address']}/review", headers=auth_headers(reviewer), json={"accept": False, "reason": "Name doesn't match"})
    client.post(f"{url}/{docs['identity_document']}/review", headers=auth_headers(reviewer), json={"accept": True})
    assert client.post(f"{BASE}/applications/{app['id']}/approve", headers=auth_headers(reviewer), json={}).status_code == 400  # not all accepted
    returned = client.post(f"{BASE}/applications/{app['id']}/return", headers=auth_headers(reviewer), json={"note": "Upload a bill in your name."}).json()
    assert returned["status"] == "returned"
    assert db.query(UserNotification).filter_by(user_id=capturer.id, event="kyc.returned").count() == 1

    assert upload(client, capturer, app["id"], "proof_of_address", "water_bill", recent()).status_code == 201
    again = submit(client, capturer, app["id"]).json()
    assert again["status"] == "submitted" and again["reviewer"] is not None
    client.post(f"{BASE}/applications/{app['id']}/start-review", headers=auth_headers(reviewer))
    state = client.get(f"{BASE}/applications/{app['id']}", headers=auth_headers(reviewer)).json()
    new_doc = next(s["document"]["id"] for s in state["slots"] if s["key"] == "proof_of_address")
    client.post(f"{url}/{new_doc}/review", headers=auth_headers(reviewer), json={"accept": True})
    approved = client.post(f"{BASE}/applications/{app['id']}/approve", headers=auth_headers(reviewer), json={}).json()
    assert approved["status"] == "approved"
    party = db.query(Party).filter_by(identifier="AB12CD34").one()
    assert party.risk_rating.value == "low"
    assert party.kyc_review_due.year == date.today().year + 3


def test_high_risk_needs_senior_approval(client, db, capturer, reviewer):
    app = complete_individual(client, capturer, is_pep=True)
    body = submit(client, capturer, app["id"]).json()
    assert body["risk_rating"] == "high" and body["edd_required"]
    client.post(f"{BASE}/applications/{app['id']}/start-review", headers=auth_headers(reviewer))
    state = client.get(f"{BASE}/applications/{app['id']}", headers=auth_headers(reviewer)).json()
    for s in state["slots"]:
        client.post(f"{BASE}/applications/{app['id']}/documents/{s['document']['id']}/review", headers=auth_headers(reviewer), json={"accept": True})
    admin = make_user(db, UserRole.admin)
    recommended = client.post(f"{BASE}/applications/{app['id']}/approve", headers=auth_headers(reviewer), json={"note": "EDD done"}).json()
    assert recommended["status"] == "awaiting_senior_approval"
    assert db.query(UserNotification).filter_by(user_id=admin.id, event="kyc.senior_approval").count() == 1
    assert client.post(f"{BASE}/applications/{app['id']}/senior-decision", headers=auth_headers(reviewer), json={"approve": True}).status_code == 403
    assert client.post(f"{BASE}/applications/{app['id']}/senior-decision", headers=auth_headers(admin), json={"approve": False}).status_code == 400
    decided = client.post(f"{BASE}/applications/{app['id']}/senior-decision", headers=auth_headers(admin), json={"approve": True}).json()
    assert decided["status"] == "approved" and decided["party"]["risk_rating"] == "high"
    assert decided["party"]["kyc_review_due"].startswith(str(date.today().year + 1))


def test_risk_override_needs_a_reason(client, db, capturer, reviewer):
    app = complete_individual(client, capturer, income_source="business", business_type="Retail shop")
    assert submit(client, capturer, app["id"]).json()["risk_rating"] == "medium"
    client.post(f"{BASE}/applications/{app['id']}/start-review", headers=auth_headers(reviewer))
    state = client.get(f"{BASE}/applications/{app['id']}", headers=auth_headers(reviewer)).json()
    for s in state["slots"]:
        client.post(f"{BASE}/applications/{app['id']}/documents/{s['document']['id']}/review", headers=auth_headers(reviewer), json={"accept": True})
    url = f"{BASE}/applications/{app['id']}/approve"
    assert client.post(url, headers=auth_headers(reviewer), json={"risk_override": "low"}).status_code == 400
    done = client.post(url, headers=auth_headers(reviewer), json={"risk_override": "low", "note": "Registered business, bank-paid income"}).json()
    assert done["status"] == "approved" and done["risk_rating"] == "low"
    assert any("Rating changed from medium to low" in r for r in done["risk_reasons"])


def test_corporate_directors_drive_documents_and_risk(client, db, capturer):
    data = corporate(directors=[{"full_name": "Peter Phiri", "position": "MD", "nationality": "MW"},
                                {"full_name": "Jane Doe", "position": "CFO", "nationality": "ZA", "is_pep": True}])
    app = create(client, capturer, "corporate", data)
    keys = [s["key"] for s in app["slots"]]
    assert "director_id:0" in keys and "director_id:1" in keys
    assert "director_permit:1" in keys and "director_permit:0" not in keys
    from app.models.kyc import ClientType
    from app.services import kyc_forms
    rating, reasons = kyc_forms.risk(ClientType.corporate, data)
    assert rating.value == "high" and "Director Jane Doe is a politically exposed person" in reasons


def test_portal_applicant_owns_their_draft(client, db, capturer):
    individual_user = make_user(db, UserRole.individual)
    other = make_user(db, UserRole.individual)
    app = create(client, individual_user, "individual", individual())
    assert app["can_edit"]
    assert client.get(f"{BASE}/applications/{app['id']}", headers=auth_headers(other)).status_code == 404
    assert [a["id"] for a in client.get(f"{BASE}/applications", headers=auth_headers(individual_user)).json()] == [app["id"]]
    assert app["possible_duplicates"] == []  # never shown to applicants
    # Staff can see it, but only the applicant edits their own draft.
    assert client.put(f"{BASE}/applications/{app['id']}", headers=auth_headers(capturer), json={"data": individual()}).status_code == 403
    assert client.post(f"{BASE}/applications", headers=auth_headers(individual_user), json={"client_type": "corporate"}).status_code == 403
    assert client.get(f"{BASE}/parties", headers=auth_headers(individual_user)).status_code == 403


def test_document_views_are_logged(client, db, capturer, reviewer):
    app = complete_individual(client, capturer)
    state = client.get(f"{BASE}/applications/{app['id']}", headers=auth_headers(reviewer)).json()
    doc_id = state["slots"][0]["document"]["id"]
    response = client.get(f"{BASE}/applications/{app['id']}/documents/{doc_id}/file", headers=auth_headers(reviewer))
    assert response.status_code == 200 and response.content == PDF
    assert db.query(AuditEvent).filter_by(entity_type="kyc_document", entity_id=doc_id, action="viewed", actor_user_id=reviewer.id).count() == 1


def test_staff_see_possible_duplicates(client, db, capturer, reviewer):
    from datetime import datetime, timezone
    db.add(Party(client_type="individual", name="Someone Else", identifier="AB12CD34", risk_rating="low",
                 kyc_approved_at=datetime.now(timezone.utc), kyc_review_due=date(2030, 1, 1)))
    db.flush()
    app = create(client, capturer, "individual", individual())
    assert [p["identifier"] for p in app["possible_duplicates"]] == ["AB12CD34"]
