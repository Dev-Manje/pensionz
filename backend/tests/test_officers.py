"""Principal officers onboarded by staff (FR-PRT-006, decided 2026-11-03): a
portal login for one or more funds through maker-checker, invitation on
approval, list scoped to the viewer's funds."""
import pytest

from app.models.identity import PasswordResetToken, User, UserRole
from app.models.notification import NotificationOutbox, UserNotification
from app.services import fund_access, officers
from tests.factories import auth_headers, make_fund, make_user
from tests.test_schemes import approve, create


@pytest.fixture
def maker(db):
    return make_user(db, UserRole.scheme_config_maker)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.scheme_config_checker)


@pytest.fixture
def fund(db, maker, checker):
    return make_fund(db, maker, checker, fund_type="umbrella_dc")


def _propose(client, maker, fund_ids, email="chisomo@example.mw", **extra):
    return client.post("/api/v1/officers", headers=auth_headers(maker),
                       json={"email": email, "full_name": "Chisomo Banda", "phone": "0999 123 456",
                             "fund_ids": [str(f) for f in fund_ids], **extra})


def test_officer_created_and_invited_only_after_approval(client, db, fund, maker, checker):
    response = _propose(client, maker, [fund.id])
    assert response.status_code == 202, response.text
    assert db.query(User).filter_by(email="chisomo@example.mw").first() is None
    assert approve(client, checker, response.json()["id"]).status_code == 200

    user = db.query(User).filter_by(email="chisomo@example.mw").one()
    assert user.roles == [UserRole.principal_officer]
    assert fund_access.granted_fund_ids(db, user.id) == [fund.id]
    assert officers.officer_fund_ids(db, user) == {fund.id}
    invite = db.query(NotificationOutbox).filter_by(recipient_user_id=user.id, event="auth.invite").one()
    assert "principal officer with Factory Fund" in invite.body and "apply for your employer" in invite.body
    assert db.query(PasswordResetToken).filter_by(user_id=user.id, purpose="invite").count() == 1

    listed = client.get("/api/v1/officers", headers=auth_headers(maker)).json()
    row = next(r for r in listed if r["email"] == "chisomo@example.mw")
    assert row["awaiting_setup"] is True and [f["code"] for f in row["funds"]] == [fund.code] and row["employers"] == []


def test_maker_cannot_approve_and_other_roles_cannot_propose(client, db, fund, maker, checker):
    request_id = _propose(client, maker, [fund.id]).json()["id"]
    assert approve(client, maker, request_id).status_code == 400
    member_admin = make_user(db, UserRole.member_admin)
    fund_access.grant(db, member_admin.id, fund.id, None)
    assert _propose(client, member_admin, [fund.id], email="x@example.mw").status_code == 403
    assert approve(client, member_admin, request_id).status_code == 403
    officer = make_user(db, UserRole.principal_officer)
    assert client.get("/api/v1/officers", headers=auth_headers(officer)).status_code == 403


def test_funds_must_be_the_makers_and_at_least_one(client, db, fund, maker):
    other = make_fund(db)
    assert _propose(client, maker, [other.id]).status_code == 404
    assert _propose(client, maker, []).status_code == 422


def test_existing_email_is_refused(client, db, fund, maker, checker):
    staff = make_user(db, UserRole.finance)
    assert _propose(client, maker, [fund.id], email=staff.email).status_code == 409
    officer = make_user(db, UserRole.principal_officer)
    assert "change their funds" in _propose(client, maker, [fund.id], email=officer.email).json()["detail"]
    _propose(client, maker, [fund.id], email="twice@example.mw")
    assert _propose(client, maker, [fund.id], email="twice@example.mw").status_code == 409


def test_add_a_fund_later_and_the_officer_is_told(client, db, fund, maker, checker):
    approve(client, checker, _propose(client, maker, [fund.id]).json()["id"])
    user = db.query(User).filter_by(email="chisomo@example.mw").one()
    second = make_fund(db, maker, checker, fund_type="umbrella_dc")
    response = client.patch(f"/api/v1/officers/{user.id}", headers=auth_headers(maker),
                            json={"fund_ids": [str(fund.id), str(second.id)]})
    assert response.status_code == 202, response.text
    assert approve(client, checker, response.json()["id"]).status_code == 200
    assert set(fund_access.granted_fund_ids(db, user.id)) == {fund.id, second.id}
    assert db.query(UserNotification).filter_by(user_id=user.id, event="portal.officer_funds_added").count() == 1
    unchanged = client.patch(f"/api/v1/officers/{user.id}", headers=auth_headers(maker),
                             json={"fund_ids": [str(fund.id), str(second.id)]})
    assert unchanged.status_code == 400


def test_list_is_scoped_to_the_viewers_funds(client, db, fund, maker, checker):
    approve(client, checker, _propose(client, maker, [fund.id]).json()["id"])
    outsider = make_user(db, UserRole.scheme_config_maker)
    make_fund(db, outsider)
    assert all(r["email"] != "chisomo@example.mw" for r in client.get("/api/v1/officers", headers=auth_headers(outsider)).json())
    user = db.query(User).filter_by(email="chisomo@example.mw").one()
    assert client.patch(f"/api/v1/officers/{user.id}", headers=auth_headers(outsider), json={"full_name": "X Y"}).status_code == 404


def test_officers_linked_from_an_employer_count_that_fund(client, db, fund, maker, checker):
    officer = make_user(db, UserRole.principal_officer)
    create(client, db, fund, maker, checker, officer_ids=[str(officer.id)])
    assert officers.officer_fund_ids(db, officer) == {fund.id}
    row = next(r for r in client.get("/api/v1/officers", headers=auth_headers(maker)).json() if r["user_id"] == str(officer.id))
    assert row["funds"][0]["granted"] is False and row["employers"][0]["code"] == "EMP01"


def test_resend_invitation(client, db, fund, maker, checker):
    approve(client, checker, _propose(client, maker, [fund.id]).json()["id"])
    user = db.query(User).filter_by(email="chisomo@example.mw").one()
    assert client.post(f"/api/v1/officers/{user.id}/send-invitation", headers=auth_headers(maker)).status_code == 202
    assert db.query(NotificationOutbox).filter_by(recipient_user_id=user.id, event="auth.invite").count() == 2
