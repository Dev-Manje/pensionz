"""Organisation KYC from the principal officer portal (FR-PRT-002): the employer's
first KYC and later changes to its details, reviewed by compliance as usual."""
from datetime import date, timedelta

import pytest

from app.models.audit import AuditEvent
from app.models.identity import UserRole
from app.models.kyc import KycDocument
from app.models.notification import UserNotification
from app.models.scheme import SchemeOfficer
from tests.factories import auth_headers, make_user
from tests.test_arrears import staff, world  # noqa: F401 — fixtures
from tests.test_kyc import BASE, corporate, memory_storage, recent, review_periods, reviewer, submit, upload  # noqa: F401 — fixtures

PO = "/api/v1/po"
LATER = (date.today() + timedelta(days=900)).isoformat()


@pytest.fixture
def scheme(world):
    return world[1]


def officer_of(db, *schemes):
    user = make_user(db, UserRole.principal_officer)
    for s in schemes:
        db.add(SchemeOfficer(scheme_id=s.id, user_id=user.id))
    db.flush()
    return user


def start(client, user, scheme):
    return client.post(f"{PO}/schemes/{scheme.id}/kyc", headers=auth_headers(user))


def fill_and_submit(client, user, app_id, data):
    assert client.put(f"{BASE}/applications/{app_id}", headers=auth_headers(user), json={"data": data}).status_code == 200
    for requirement, doc_type, expiry in (
        ("identification", "registration_certificate", None), ("proof_of_address", "utility_bill", None),
        ("supporting_document", "articles", None), ("director_id:0", "national_id", LATER),
        ("source_of_funds", "bank_statements", None), ("proof_of_bank_account", "bank_letter", None),
    ):
        assert upload(client, user, app_id, requirement, doc_type, recent(), expiry).status_code == 201, requirement
    response = submit(client, user, app_id, "corporate")
    assert response.status_code == 200, response.text
    return response.json()


def approve_all(client, compliance, app_id):
    headers = auth_headers(compliance)
    assert client.post(f"{BASE}/applications/{app_id}/start-review", headers=headers).status_code == 200
    app = client.get(f"{BASE}/applications/{app_id}", headers=headers).json()
    for slot in app["slots"]:
        if slot["document"]:
            assert client.post(f"{BASE}/applications/{app_id}/documents/{slot['document']['id']}/review", headers=headers,
                               json={"accept": True}).status_code == 200
    response = client.post(f"{BASE}/applications/{app_id}/approve", headers=headers, json={})
    assert response.status_code == 200, response.text
    return response.json()


def test_first_kyc_from_the_portal_links_the_employer(client, db, scheme, reviewer):
    officer = officer_of(db, scheme)
    response = start(client, officer, scheme)
    assert response.status_code == 201, response.text
    app = response.json()
    assert app["client_type"] == "corporate" and app["data"] == {"entity_name": "Employer Ltd"} and app["scheme_id"] == str(scheme.id)
    # One application at a time per employer.
    assert start(client, officer, scheme).status_code == 409

    submitted = fill_and_submit(client, officer, app["id"], corporate(entity_name="Employer Ltd"))
    # The risk rating is compliance's working — not shown in the portal.
    assert submitted["risk_rating"] is None and submitted["risk_reasons"] == [] and submitted["party"] is None
    approve_all(client, reviewer, app["id"])

    db.refresh(scheme)
    assert scheme.party_id is not None
    assert db.query(AuditEvent).filter_by(entity_type="scheme", entity_id=str(scheme.id), action="client_linked").count() == 1
    # The officer is told, with a link into the portal rather than the staff KYC screen.
    note = db.query(UserNotification).filter_by(user_id=officer.id, event="kyc.approved").one()
    assert note.link == f"/po/kyc/{app['id']}"

    org = client.get(f"{PO}/schemes/{scheme.id}/organisation", headers=auth_headers(officer)).json()
    assert org["has_client"] and org["review_state"] == "current" and org["in_progress"] is None
    assert {"label": "Registration number", "value": "COY-1234"} in org["details"]
    assert org["people"] == [{"name": "Peter Phiri", "role": "Managing Director"}]
    assert {d["label"] for d in org["documents"]} >= {"Identification document", "ID — Peter Phiri"}
    assert [h["reference"] for h in org["history"]] == [app["reference"]]


def test_change_request_starts_from_approved_details(client, db, scheme, reviewer):
    officer = officer_of(db, scheme)
    first = start(client, officer, scheme).json()
    fill_and_submit(client, officer, first["id"], corporate(entity_name="Employer Ltd"))
    approve_all(client, reviewer, first["id"])

    # Another officer of the same employer asks for a change.
    colleague = officer_of(db, scheme)
    change = start(client, colleague, scheme).json()
    assert change["data"]["registration_number"] == "COY-1234" and change["changed_fields"] == [] and change["is_change"]
    # Accepted documents come across, pending review again — nothing to re-upload unless it changed.
    carried = [s["document"] for s in change["slots"] if s["document"]]
    assert len(carried) == 6 and all(d["review_status"] == "pending" for d in carried)
    assert change["problems"] == []

    data = {**change["data"], "physical_address": "Plot 22, Lilongwe", "contact_name": "Finance Manager"}
    assert client.put(f"{BASE}/applications/{change['id']}", headers=auth_headers(colleague), json={"data": data}).status_code == 200
    # The first officer can see and finish it too.
    seen = client.get(f"{BASE}/applications/{change['id']}", headers=auth_headers(officer)).json()
    assert seen["can_edit"]
    assert submit(client, officer, change["id"], "corporate").status_code == 200

    staff_view = client.get(f"{BASE}/applications/{change['id']}", headers=auth_headers(reviewer)).json()
    assert staff_view["changed_fields"] == ["contact_name", "physical_address"]
    approve_all(client, reviewer, change["id"])

    party_id = scheme.party_id
    db.refresh(scheme)
    assert scheme.party_id == party_id  # same client, refreshed
    org = client.get(f"{PO}/schemes/{scheme.id}/organisation", headers=auth_headers(officer)).json()
    assert {"label": "Physical address", "value": "Plot 22, Lilongwe"} in org["details"]
    assert org["approved_reference"] == change["reference"]
    assert [(h["reference"], h["is_change"]) for h in org["history"]] == [(change["reference"], True), (first["reference"], False)]
    # Superseding a carried document on the change doesn't touch the approved original.
    assert db.query(KycDocument).filter_by(application_id=first["id"], superseded=False).count() == 6


def test_portal_kyc_access(client, db, world, scheme, staff):
    officer = officer_of(db, scheme)
    stranger = officer_of(db)
    app = start(client, officer, scheme).json()
    # Officers of other employers: as if it doesn't exist.
    assert start(client, stranger, scheme).status_code == 404
    assert client.get(f"{PO}/schemes/{scheme.id}/organisation", headers=auth_headers(stranger)).status_code == 404
    assert client.get(f"{BASE}/applications/{app['id']}", headers=auth_headers(stranger)).status_code == 404
    assert client.get(f"{BASE}/applications", headers=auth_headers(stranger)).json() == []
    # Staff use the staff KYC screens, not the portal.
    assert client.get(f"{PO}/schemes/{scheme.id}/organisation", headers=auth_headers(staff)).status_code == 403
    # An unlinked officer loses access when the link is removed.
    db.query(SchemeOfficer).filter_by(user_id=officer.id).delete()
    db.flush()
    assert client.get(f"{BASE}/applications/{app['id']}", headers=auth_headers(officer)).status_code == 200  # still the applicant


def test_portal_users_read_only_the_form_lists(client, db, scheme):
    officer = officer_of(db, scheme)
    assert client.get("/api/v1/setup/lists/countries", headers=auth_headers(officer)).status_code == 200
    assert client.get("/api/v1/setup/lists/transaction_types", headers=auth_headers(officer)).status_code == 403
    assert client.get("/api/v1/setup/lists", headers=auth_headers(officer)).status_code == 403

