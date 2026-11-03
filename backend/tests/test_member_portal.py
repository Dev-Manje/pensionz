"""Member portal (FR-PRT-002, FR-PRT-006): invite, self-registration with the code
sent to the email on record, own memberships only, change requests through the
member checker (bank needs a code), member notifications (FR-NOT-003)."""
import re
from datetime import date

import pytest

from app.models.approval import ApprovalRequest
from app.models.identity import User, UserRole
from app.models.notification import NotificationOutbox
from app.services import members
from tests.factories import auth_headers, make_fund, make_user
from tests.test_ledger import make_member
from tests.test_members import approve, body, create, setup  # noqa: F401 — fixture

API = "/api/v1"


@pytest.fixture
def admin(db):
    return make_user(db, UserRole.member_admin)


@pytest.fixture
def maker(admin):
    return admin


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.member_checker)


@pytest.fixture
def fund(db, admin, checker):
    return make_fund(db, admin, checker, fund_type="umbrella_dc")


@pytest.fixture
def member(db, fund):
    m = make_member(db, fund, "M0001")
    m.email, m.id_type, m.id_number, m.id_number_key = "tiwonge@example.mw", "NATID", "AB12-3456", members.id_key("AB12-3456")
    db.flush()
    return m


def _code(db, address, event="auth.one_time_code"):
    row = (db.query(NotificationOutbox).filter_by(recipient_address=address, event=event)
           .order_by(NotificationOutbox.created_at.desc()).first())
    return re.search(r"\b(\d{6})\b", row.body).group(1)


def test_invite_links_a_member_login(client, db, admin, member):
    response = client.post(f"{API}/members/{member.id}/portal-invite", headers=auth_headers(admin))
    assert response.status_code == 200, response.text
    db.refresh(member)
    user = db.get(User, member.portal_user_id)
    assert user.email == "tiwonge@example.mw" and user.roles == [UserRole.member]
    assert db.query(NotificationOutbox).filter_by(recipient_user_id=user.id, event="auth.invite").count() == 1
    assert client.post(f"{API}/members/{member.id}/portal-invite", headers=auth_headers(admin)).status_code == 409
    mine = client.get(f"{API}/my/members", headers=auth_headers(user)).json()
    assert [m["account_code"] for m in mine] == ["M0001"]


def test_invite_needs_an_email_and_the_role(client, db, admin, fund):
    bare = make_member(db, fund, "M0009")
    assert client.post(f"{API}/members/{bare.id}/portal-invite", headers=auth_headers(admin)).status_code == 400
    finance = make_user(db, UserRole.finance)
    assert client.post(f"{API}/members/{bare.id}/portal-invite", headers=auth_headers(finance)).status_code == 403


def test_self_registration_with_code_to_email_on_record(client, db, member):
    wrong = client.post(f"{API}/auth/member-register/start", json={"member_number": "M0001", "id_number": "XX99", "date_of_birth": "1990-01-01"})
    right = client.post(f"{API}/auth/member-register/start", json={"member_number": "m0001", "id_number": "ab12 3456", "date_of_birth": "1990-01-01"})
    assert wrong.status_code == right.status_code == 200 and wrong.json()["detail"] == right.json()["detail"]
    assert client.post(f"{API}/auth/member-register/finish",
                       json={"challenge": wrong.json()["challenge"], "code": "123456", "new_password": "Str0ng!Passw0rd"}).status_code == 400
    code = _code(db, "tiwonge@example.mw")
    done = client.post(f"{API}/auth/member-register/finish",
                       json={"challenge": right.json()["challenge"], "code": code, "new_password": "Str0ng!Passw0rd"})
    assert done.status_code == 200, done.text
    me = {"Authorization": f"Bearer {done.json()['access_token']}"}
    assert client.get(f"{API}/my/members", headers=me).json()[0]["account_code"] == "M0001"
    # Next sign-in: password + emailed code, as for every portal user.
    login = client.post(f"{API}/auth/login", json={"email": "tiwonge@example.mw", "password": "Str0ng!Passw0rd"}).json()
    assert login["code_required"] is True


def test_only_own_memberships(client, db, admin, member, fund):
    client.post(f"{API}/members/{member.id}/portal-invite", headers=auth_headers(admin))
    db.refresh(member)
    user = db.get(User, member.portal_user_id)
    other = make_member(db, fund, "M0002")
    assert client.get(f"{API}/my/members/{other.id}", headers=auth_headers(user)).status_code == 404
    assert client.get(f"{API}/my/members/{member.id}", headers=auth_headers(admin)).status_code == 403
    detail = client.get(f"{API}/my/members/{member.id}", headers=auth_headers(user)).json()
    assert detail["details"]["id_number"].startswith("••••")
    for kind in ("benefit", "client", "contributions"):
        assert client.get(f"{API}/my/members/{member.id}/documents/{kind}", headers=auth_headers(user)).content[:4] == b"%PDF"


def test_contact_and_bank_changes_go_to_the_checker(client, db, admin, checker, member):
    client.post(f"{API}/members/{member.id}/portal-invite", headers=auth_headers(admin))
    db.refresh(member)
    user = db.get(User, member.portal_user_id)
    me = auth_headers(user)
    contact = client.post(f"{API}/my/members/{member.id}/contact", headers=me,
                          json={"mobile": "+265 888 123 456", "email": "tiwonge@example.mw", "physical_address": "Area 25, Lilongwe"})
    assert contact.status_code == 202, contact.text
    request = db.get(ApprovalRequest, contact.json()["id"])
    assert request.kind == "member_update" and "member portal" in request.summary
    assert approve(client, user, request.id).status_code == 403  # a member can't check
    assert approve(client, checker, request.id).status_code == 200
    db.refresh(member)
    assert member.mobile == "+265 888 123 456"

    from app.models.reference import Bank
    bank = db.query(Bank).first()
    no_code = client.post(f"{API}/my/members/{member.id}/bank", headers=me,
                          json={"bank_id": str(bank.id), "bank_account_name": "T Member", "bank_account_number": "100200300", "code": "000000"})
    assert no_code.status_code == 400
    assert client.post(f"{API}/my/members/{member.id}/bank/code", headers=me).status_code == 202
    code = _code(db, user.email)
    bank_req = client.post(f"{API}/my/members/{member.id}/bank", headers=me,
                           json={"bank_id": str(bank.id), "bank_account_name": "T Member", "bank_account_number": "100200300", "code": code})
    assert bank_req.status_code == 202, bank_req.text
    assert approve(client, checker, bank_req.json()["id"]).status_code == 200
    assert db.query(NotificationOutbox).filter_by(event="member.bank_changed", recipient_address="tiwonge@example.mw").count() == 1
    assert len(client.get(f"{API}/my/members/{member.id}/requests", headers=me).json()) == 2


def test_nomination_and_kyc_from_the_portal(client, db, admin, checker, member):
    client.post(f"{API}/members/{member.id}/portal-invite", headers=auth_headers(admin))
    db.refresh(member)
    me = auth_headers(db.get(User, member.portal_user_id))
    nomination = client.post(f"{API}/my/members/{member.id}/beneficiaries", headers=me, json={
        "signed_date": date.today().isoformat(),
        "beneficiaries": [{"full_name": "Chisomo Member", "relationship": "SPOUSE", "share_pct": "100"}]})
    assert nomination.status_code == 202, nomination.text
    assert db.get(ApprovalRequest, nomination.json()["id"]).kind == "beneficiary_nomination"
    started = client.post(f"{API}/my/members/{member.id}/kyc", headers=me)
    assert started.status_code == 201, started.text
    assert started.json()["client_type"] == "individual"
    assert client.post(f"{API}/my/members/{member.id}/kyc", headers=me).status_code == 409


def test_new_member_gets_a_welcome_email(client, db, maker, checker, setup):  # noqa: F811
    fund, scheme, category = setup
    create(client, db, maker, checker, fund, body(scheme, category, email="new.member@example.mw"))
    row = db.query(NotificationOutbox).filter_by(event="member.joined", recipient_address="new.member@example.mw").one()
    assert "member number" in row.body
