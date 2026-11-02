"""Principal officer portal access (FR-PRT-006): invitations from the employer
screen, a one-time code at every portal sign-in, and officers who act for
several employers in several funds."""
import re
from datetime import timedelta

import pytest

from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.identity import OneTimeCode, PasswordResetToken, User, UserRole
from app.models.mixins import utcnow
from app.models.notification import NotificationOutbox, OutboxStatus, UserNotification
from app.models.scheme import Scheme
from app.services import notification_delivery, passwords
from tests.factories import PASSWORD, auth_headers, make_fund, make_user
from tests.test_schemes import approve, body


@pytest.fixture
def maker(db):
    return make_user(db, UserRole.scheme_config_maker)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.scheme_config_checker)


@pytest.fixture
def fund(db, maker, checker):
    return make_fund(db, maker, checker, fund_type="umbrella_dc")


def _login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _latest_code(db, user) -> str:
    row = (db.query(NotificationOutbox).filter_by(recipient_user_id=user.id, event="auth.one_time_code")
           .order_by(NotificationOutbox.created_at.desc()).first())
    return re.search(r"\b(\d{6})\b", row.body).group(1)


def _wrong(code: str) -> str:
    return f"{(int(code) + 1) % 10 ** 6:06d}"


def _scheme(client, db, fund, maker, checker, code="EMP01", **overrides) -> Scheme:
    response = client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker), json=body(code=code, **overrides))
    assert response.status_code == 202, response.text
    assert approve(client, checker, response.json()["id"]).status_code == 200, "approval failed"
    return db.query(Scheme).filter_by(fund_id=fund.id, code=code).one()


# ---- one-time code at sign-in ----------------------------------------------------------


def test_principal_officer_sign_in_needs_the_emailed_code(client, db):
    officer = make_user(db, UserRole.principal_officer)
    response = _login(client, officer.email)
    assert response.status_code == 200
    data = response.json()
    assert data["code_required"] is True and data["access_token"] is None
    assert data["code_sent_to"].endswith("@" + officer.email.split("@")[1]) and officer.email not in data["code_sent_to"]
    # Not signed in yet: only the password step is recorded.
    assert db.query(AuditEvent).filter_by(entity_id=str(officer.id), action="signed_in").count() == 0
    # The code never lands in the in-app inbox.
    assert db.query(UserNotification).filter_by(user_id=officer.id, event="auth.one_time_code").count() == 0

    done = client.post("/api/v1/auth/sign-in-code", json={"challenge": data["challenge"], "code": _latest_code(db, officer)})
    assert done.status_code == 200, done.text
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {done.json()['access_token']}"})
    assert me.json()["roles"] == ["principal_officer"]
    assert db.query(AuditEvent).filter_by(entity_id=str(officer.id), action="signed_in").count() == 1


def test_code_is_needed_at_every_sign_in(client, db):
    officer = make_user(db, UserRole.principal_officer)
    for _ in range(2):
        challenge = _login(client, officer.email).json()["challenge"]
        assert client.post("/api/v1/auth/sign-in-code", json={"challenge": challenge, "code": _latest_code(db, officer)}).status_code == 200


def test_staff_sign_in_needs_no_code_even_with_a_portal_role(client, db):
    staff = make_user(db, UserRole.finance, UserRole.principal_officer)
    data = _login(client, staff.email).json()
    assert data["code_required"] is False and data["access_token"]


def test_code_works_once(client, db):
    officer = make_user(db, UserRole.principal_officer)
    challenge = _login(client, officer.email).json()["challenge"]
    code = _latest_code(db, officer)
    assert client.post("/api/v1/auth/sign-in-code", json={"challenge": challenge, "code": code}).status_code == 200
    assert client.post("/api/v1/auth/sign-in-code", json={"challenge": challenge, "code": code}).status_code == 400


def test_wrong_codes_use_up_the_code(client, db):
    officer = make_user(db, UserRole.principal_officer)
    challenge = _login(client, officer.email).json()["challenge"]
    code = _latest_code(db, officer)
    for _ in range(settings.otp_max_attempts):
        assert client.post("/api/v1/auth/sign-in-code", json={"challenge": challenge, "code": _wrong(code)}).status_code == 400
    # Even the right code is refused now; a new one works.
    assert client.post("/api/v1/auth/sign-in-code", json={"challenge": challenge, "code": code}).status_code == 400
    assert client.post("/api/v1/auth/sign-in-code/resend", json={"challenge": challenge}).status_code == 202
    assert client.post("/api/v1/auth/sign-in-code", json={"challenge": challenge, "code": _latest_code(db, officer)}).status_code == 200


def test_expired_code_is_refused(client, db):
    officer = make_user(db, UserRole.principal_officer)
    challenge = _login(client, officer.email).json()["challenge"]
    row = db.query(OneTimeCode).filter_by(user_id=officer.id, used_at=None).one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.flush()
    response = client.post("/api/v1/auth/sign-in-code", json={"challenge": challenge, "code": _latest_code(db, officer)})
    assert response.status_code == 400 and "expired" in response.json()["detail"]


def test_a_new_code_voids_the_old_one(client, db):
    officer = make_user(db, UserRole.principal_officer)
    challenge = _login(client, officer.email).json()["challenge"]
    first = _latest_code(db, officer)
    client.post("/api/v1/auth/sign-in-code/resend", json={"challenge": challenge})
    second = _latest_code(db, officer)
    if first != second:
        assert client.post("/api/v1/auth/sign-in-code", json={"challenge": challenge, "code": first}).status_code == 400
    assert client.post("/api/v1/auth/sign-in-code", json={"challenge": challenge, "code": second}).status_code == 200


def test_too_many_codes_are_refused(client, db):
    officer = make_user(db, UserRole.principal_officer)
    challenge = _login(client, officer.email).json()["challenge"]
    for _ in range(settings.otp_max_sends_per_15_minutes - 1):
        assert client.post("/api/v1/auth/sign-in-code/resend", json={"challenge": challenge}).status_code == 202
    assert client.post("/api/v1/auth/sign-in-code/resend", json={"challenge": challenge}).status_code == 429


def test_a_bad_or_access_token_is_not_a_challenge(client, db):
    officer = make_user(db, UserRole.principal_officer)
    _login(client, officer.email)
    access = auth_headers(officer)["Authorization"].split()[1]
    assert client.post("/api/v1/auth/sign-in-code", json={"challenge": access, "code": _latest_code(db, officer)}).status_code == 401
    assert client.post("/api/v1/auth/sign-in-code", json={"challenge": "nonsense", "code": "123456"}).status_code == 401


def test_code_is_wiped_from_the_outbox_once_sent(client, db):
    officer = make_user(db, UserRole.principal_officer)
    _login(client, officer.email)
    code = _latest_code(db, officer)
    db.commit()
    while notification_delivery.deliver_one(db):
        pass
    row = db.query(NotificationOutbox).filter_by(recipient_user_id=officer.id, event="auth.one_time_code").one()
    assert row.status != OutboxStatus.pending and code not in row.body and code not in row.subject


# ---- invitations from the employer screen -----------------------------------------------


def test_new_officer_is_invited_when_the_employer_is_approved(client, db, fund, maker, checker):
    new = {"full_name": "Grace Banda", "email": "Grace.Banda@kte.mw", "phone": "+265 999 123 456"}
    response = client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker), json=body(new_officers=[new]))
    assert response.status_code == 202
    assert response.json()["payload"]["principal_officers"][0]["invite"] is True
    assert db.query(User).filter_by(email="grace.banda@kte.mw").count() == 0  # nothing until approved
    assert approve(client, checker, response.json()["id"]).status_code == 200

    officer = db.query(User).filter_by(email="grace.banda@kte.mw").one()
    assert officer.roles == [UserRole.principal_officer] and officer.phone == "+265 999 123 456"
    scheme = db.query(Scheme).filter_by(fund_id=fund.id).one()
    assert [o.user_id for o in scheme.officers] == [officer.id]
    invite = db.query(NotificationOutbox).filter_by(recipient_user_id=officer.id, event="auth.invite").one()
    assert scheme.name in invite.body and fund.name in invite.body


def test_invitation_acceptance_asks_portal_users_for_a_code(client, db, fund, maker, checker):
    _scheme(client, db, fund, maker, checker, new_officers=[{"full_name": "Grace Banda", "email": "grace@kte.mw"}])
    officer = db.query(User).filter_by(email="grace@kte.mw").one()
    token = passwords.issue_token(db, officer, "invite", None)
    data = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "NewPass123"}).json()
    assert data["code_required"] is True and data["access_token"] is None
    done = client.post("/api/v1/auth/sign-in-code", json={"challenge": data["challenge"], "code": _latest_code(db, officer)})
    assert done.status_code == 200
    assert db.query(PasswordResetToken).filter_by(user_id=officer.id, used_at=None).count() == 0


def test_inviting_an_existing_officer_links_their_login(client, db, fund, maker, checker):
    """One officer acts for employers in two funds — no second login."""
    first = _scheme(client, db, fund, maker, checker, new_officers=[{"full_name": "Grace Banda", "email": "grace@kte.mw"}])
    officer = db.query(User).filter_by(email="grace@kte.mw").one()
    officer.password_changed_at = utcnow()  # she has set up her login
    db.flush()
    other_fund = make_fund(db, maker, checker)
    second = _scheme(client, db, other_fund, maker, checker, code="EMP02",
                     new_officers=[{"full_name": "G. Banda", "email": "GRACE@kte.mw"}])
    assert db.query(User).filter_by(email="grace@kte.mw").count() == 1
    assert [o.user_id for o in second.officers] == [officer.id]
    assert db.query(NotificationOutbox).filter_by(recipient_user_id=officer.id, event="auth.invite").count() == 1
    assert db.query(UserNotification).filter_by(user_id=officer.id, event="portal.scheme_linked").count() == 1

    mine = client.get("/api/v1/po/schemes", headers=auth_headers(officer)).json()
    assert {(s["id"], s["fund_code"]) for s in mine} == {(str(first.id), fund.code), (str(second.id), other_fund.code)}


def test_two_pending_invitations_for_one_email_make_one_login(client, db, fund, maker, checker):
    new = [{"full_name": "Grace Banda", "email": "grace@kte.mw"}]
    one = client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker), json=body(code="EMP01", new_officers=new))
    two = client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker), json=body(code="EMP02", new_officers=new))
    assert approve(client, checker, one.json()["id"]).status_code == 200
    assert approve(client, checker, two.json()["id"]).status_code == 200
    officer = db.query(User).filter_by(email="grace@kte.mw").one()
    assert db.query(Scheme).join(Scheme.officers).filter_by(user_id=officer.id).count() == 2


def test_staff_email_cannot_be_invited_as_officer(client, db, fund, maker):
    staff = make_user(db, UserRole.finance)
    response = client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker),
                           json=body(new_officers=[{"full_name": "Someone", "email": staff.email}]))
    assert response.status_code == 400 and "principal officer role" in response.json()["detail"]


def test_removed_officer_is_told(client, db, fund, maker, checker):
    officer = make_user(db, UserRole.principal_officer)
    scheme = _scheme(client, db, fund, maker, checker, officer_ids=[str(officer.id)])
    response = client.put(f"/api/v1/schemes/{scheme.id}", headers=auth_headers(maker), json=body(officer_ids=[]))
    assert approve(client, checker, response.json()["id"]).status_code == 200
    assert db.query(UserNotification).filter_by(user_id=officer.id, event="portal.scheme_unlinked").count() == 1
    assert client.get("/api/v1/po/schemes", headers=auth_headers(officer)).json() == []


def test_staff_see_officer_setup_state_and_other_employers(client, db, fund, maker, checker):
    officer = make_user(db, UserRole.principal_officer)
    scheme = _scheme(client, db, fund, maker, checker, officer_ids=[str(officer.id)])
    _scheme(client, db, fund, maker, checker, code="EMP02", officer_ids=[str(officer.id)])
    out = client.get(f"/api/v1/schemes/{scheme.id}", headers=auth_headers(maker)).json()["officers"][0]
    assert out["other_scheme_count"] == 1 and out["awaiting_setup"] is True  # never signed in
    officer.password_changed_at = utcnow()
    db.flush()
    assert client.get(f"/api/v1/schemes/{scheme.id}", headers=auth_headers(maker)).json()["officers"][0]["awaiting_setup"] is False


# ---- portal access limits ---------------------------------------------------------------


def test_officer_sees_only_their_own_employers(client, db, fund, maker, checker):
    mine = make_user(db, UserRole.principal_officer)
    theirs = make_user(db, UserRole.principal_officer)
    _scheme(client, db, fund, maker, checker, officer_ids=[str(mine.id)])
    _scheme(client, db, fund, maker, checker, code="EMP02", officer_ids=[str(theirs.id)])
    listed = client.get("/api/v1/po/schemes", headers=auth_headers(mine)).json()
    assert [s["code"] for s in listed] == ["EMP01"]


def test_staff_cannot_use_the_officer_portal(client, db):
    assert client.get("/api/v1/po/schemes", headers=auth_headers(make_user(db, UserRole.admin))).status_code == 403
    assert client.get("/api/v1/po/schemes").status_code == 401
