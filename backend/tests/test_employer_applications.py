"""Employer onboarding by the principal officer (decided 2026-11-03): the officer
applies into a fund staff gave them, with proposed categories and the
organisation KYC; compliance approves the KYC; scheme setup sets the final
terms; a checker approves and the employer goes live with the officer linked."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.category import BenefitCategory
from app.models.identity import UserRole
from app.models.investment import InvestmentOption, PricingMethod
from app.models.notification import UserNotification
from app.models.regulatory import RegulatoryParameterVersion
from app.models.scheme import EmployerApplication, Scheme, SchemeOfficer
from app.services import fund_access
from tests.factories import auth_headers, make_fund, make_user
from tests.test_kyc import corporate, memory_storage, review_periods  # noqa: F401 — fixtures
from tests.test_portal_kyc import approve_all, fill_and_submit
from tests.test_schemes import approve

PO = "/api/v1/po/employer-applications"
STAFF = "/api/v1/employer-applications"


@pytest.fixture
def maker(db):
    return make_user(db, UserRole.scheme_config_maker)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.scheme_config_checker)


@pytest.fixture
def compliance(db):
    return make_user(db, UserRole.compliance)


@pytest.fixture
def fund(db, maker, checker):
    for key, value in {"min_employee_contribution_pct": "5", "min_employer_contribution_pct": "10",
                       "min_retirement_age": "50", "max_retirement_age": "70"}.items():
        db.add(RegulatoryParameterVersion(key=key, value=Decimal(value), effective_from=date(2023, 1, 1)))
    fund = make_fund(db, maker, checker, fund_type="umbrella_dc")
    db.add(InvestmentOption(fund_id=fund.id, code="GEN", name="General Pool", pricing_method=PricingMethod.declared_rate))
    db.flush()
    return fund


@pytest.fixture
def officer(db, fund):
    user = make_user(db, UserRole.principal_officer)
    fund_access.grant(db, user.id, fund.id, None)
    db.flush()
    return user


def body(fund, **details):
    d = {"name": "Lakeshore Logistics Ltd", "registration_number": "COY-1234", "address_line1": "Plot 10, Blantyre",
         "contact_name": "HR Manager", "contact_email": "hr@lakeshore.example", "contribution_day": 14, "join_date": "2026-11-01"}
    d.update(details)
    return {"fund_id": str(fund.id), "details": d,
            "categories": [{"name": "Staff", "employee_rate": "5", "employer_rate": "10", "normal_retirement_age": 60},
                           {"name": "Management", "employee_rate": "7.5", "employer_rate": "15", "normal_retirement_age": 60}]}


def _create(client, officer, fund, **details):
    response = client.post(PO, headers=auth_headers(officer), json=body(fund, **details))
    assert response.status_code == 201, response.text
    return response.json()


def _with_kyc(client, officer, fund):
    app = _create(client, officer, fund)
    kyc = client.post(f"{PO}/{app['id']}/kyc", headers=auth_headers(officer))
    assert kyc.status_code == 201, kyc.text
    assert kyc.json()["data"]["entity_name"] == "Lakeshore Logistics Ltd"
    fill_and_submit(client, officer, kyc.json()["id"], corporate())
    return app, kyc.json()["id"]


def _final(client, maker, app_id):
    terms = client.get(f"{STAFF}/{app_id}/suggested-terms", headers=auth_headers(maker))
    assert terms.status_code == 200, terms.text
    return terms.json()


def test_full_onboarding(client, db, fund, officer, maker, checker, compliance):
    assert [f["code"] for f in client.get("/api/v1/po/application-funds", headers=auth_headers(officer)).json()] == [fund.code]
    app, kyc_id = _with_kyc(client, officer, fund)
    sent = client.post(f"{PO}/{app['id']}/submit", headers=auth_headers(officer))
    assert sent.status_code == 200, sent.text and sent.json()["status"] == "submitted"
    assert db.query(UserNotification).filter_by(user_id=maker.id, event="employer_application.submitted").count() == 1

    # Scheme setup can't send the terms before compliance approves the KYC.
    final = _final(client, maker, app["id"])
    assert final["code"] == "LAKES01" and [c["code"] for c in final["categories"]] == ["STAFF", "MANAGE"]
    early = client.post(f"{STAFF}/{app['id']}/propose", headers=auth_headers(maker), json=final)
    assert early.status_code == 409 and "KYC" in early.json()["detail"]

    approve_all(client, compliance, kyc_id)
    assert db.query(UserNotification).filter_by(user_id=maker.id, event="employer_application.kyc_approved").count() == 1

    # Staff raise the management employer rate before approving.
    final["categories"][1]["terms"]["employer_rate"] = "17.5"
    final["note"] = "Management employer rate set at 17.5% as agreed."
    request = client.post(f"{STAFF}/{app['id']}/propose", headers=auth_headers(maker), json=final)
    assert request.status_code == 202, request.text
    assert db.query(Scheme).filter_by(fund_id=fund.id).count() == 0
    assert approve(client, maker, request.json()["id"]).status_code == 400  # not their own
    assert approve(client, checker, request.json()["id"]).status_code == 200

    scheme = db.query(Scheme).filter_by(fund_id=fund.id, code="LAKES01").one()
    assert scheme.name == "Lakeshore Logistics Ltd" and scheme.contribution_day == 14 and scheme.party_id is not None
    assert db.query(SchemeOfficer).filter_by(scheme_id=scheme.id, user_id=officer.id).count() == 1
    cats = {c.code: c for c in db.query(BenefitCategory).filter_by(scheme_id=scheme.id)}
    assert cats["MANAGE"].terms[0].employer_rate == Decimal("17.5")
    mine = client.get(f"{PO}/{app['id']}", headers=auth_headers(officer)).json()
    assert mine["status"] == "approved" and mine["scheme_id"] == str(scheme.id) and mine["final_terms"]["categories"][1]["terms"]["employer_rate"]
    assert db.query(UserNotification).filter_by(user_id=officer.id, event="employer_application.approved").count() == 1
    # The officer now acts for the employer.
    assert [s["code"] for s in client.get("/api/v1/po/schemes", headers=auth_headers(officer)).json()] == ["LAKES01"]


def test_officer_problems_block_sending(client, db, fund, officer):
    app = _create(client, officer, fund, contribution_day=None)
    response = client.post(f"{PO}/{app['id']}/submit", headers=auth_headers(officer))
    assert response.status_code == 400
    assert "contribution due day" in response.json()["detail"] and "KYC" in response.json()["detail"]
    low = body(fund)
    low["categories"][0]["employer_rate"] = "8"
    saved = client.put(f"{PO}/{app['id']}", headers=auth_headers(officer), json=low).json()
    assert any("below the statutory minimum of 10%" in p for p in saved["problems"])


def test_only_granted_funds_and_own_applications(client, db, fund, officer, maker):
    other = make_fund(db, maker, fund_type="umbrella_dc")
    assert client.post(PO, headers=auth_headers(officer), json=body(other)).status_code == 404
    app = _create(client, officer, fund)
    stranger = make_user(db, UserRole.principal_officer)
    assert client.get(f"{PO}/{app['id']}", headers=auth_headers(stranger)).status_code == 404
    assert client.get(PO, headers=auth_headers(maker)).status_code == 403
    # Drafts aren't shown to staff.
    assert client.get(f"{STAFF}/{app['id']}", headers=auth_headers(maker)).status_code == 404
    outsider = make_user(db, UserRole.scheme_config_maker)
    assert client.get(STAFF, headers=auth_headers(outsider)).json() == []


def test_return_resubmit_and_checker_rejection(client, db, fund, officer, maker, checker, compliance):
    app, kyc_id = _with_kyc(client, officer, fund)
    client.post(f"{PO}/{app['id']}/submit", headers=auth_headers(officer))
    returned = client.post(f"{STAFF}/{app['id']}/return", headers=auth_headers(maker), json={"note": "Add the TPIN."})
    assert returned.json()["status"] == "returned"
    assert db.query(UserNotification).filter_by(user_id=officer.id, event="employer_application.returned").count() == 1
    assert client.put(f"{PO}/{app['id']}", headers=auth_headers(officer), json=body(fund, tpin="20012345")).status_code == 200
    assert client.post(f"{PO}/{app['id']}/submit", headers=auth_headers(officer)).json()["status"] == "submitted"

    approve_all(client, compliance, kyc_id)
    request = client.post(f"{STAFF}/{app['id']}/propose", headers=auth_headers(maker), json=_final(client, maker, app["id"]))
    assert client.put(f"{PO}/{app['id']}", headers=auth_headers(officer), json=body(fund)).status_code == 409
    rejected = client.post(f"/api/v1/approvals/{request.json()['id']}/reject", headers=auth_headers(checker), json={"comment": "Use code LLL01"})
    assert rejected.status_code == 200
    assert db.get(EmployerApplication, app["id"]).status.value == "submitted"  # back with scheme setup
    final = _final(client, maker, app["id"])
    final["code"] = "LLL01"
    again = client.post(f"{STAFF}/{app['id']}/propose", headers=auth_headers(maker), json=final)
    assert again.status_code == 202
    assert approve(client, checker, again.json()["id"]).status_code == 200
    assert db.query(Scheme).filter_by(fund_id=fund.id, code="LLL01").one().tpin == "20012345"


def test_staff_terms_are_validated(client, db, fund, officer, maker, compliance):
    app, kyc_id = _with_kyc(client, officer, fund)
    client.post(f"{PO}/{app['id']}/submit", headers=auth_headers(officer))
    approve_all(client, compliance, kyc_id)
    final = _final(client, maker, app["id"])
    final["categories"][0]["terms"]["employee_rate"] = "3"
    response = client.post(f"{STAFF}/{app['id']}/propose", headers=auth_headers(maker), json=final)
    assert response.status_code == 400 and "statutory minimum" in response.json()["detail"]
    member_admin = make_user(db, UserRole.member_admin)
    fund_access.grant(db, member_admin.id, fund.id, None)
    assert client.post(f"{STAFF}/{app['id']}/return", headers=auth_headers(member_admin), json={"note": "x"}).status_code == 403
