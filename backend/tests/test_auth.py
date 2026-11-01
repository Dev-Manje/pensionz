from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.identity import UserRole, UserStatus
from app.models.notification import NotificationOutbox
from tests.factories import PASSWORD, auth_headers, make_user


def _login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_login_returns_tokens_and_me_lists_roles(client, db):
    user = make_user(db, UserRole.finance, UserRole.auditor)
    response = _login(client, user.email)
    assert response.status_code == 200
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}).json()
    assert set(me["roles"]) == {"finance", "auditor"}
    assert me["is_staff"] is True


def test_login_is_audited(client, db):
    user = make_user(db, UserRole.finance)
    _login(client, user.email)
    assert db.query(AuditEvent).filter_by(entity_id=str(user.id), action="signed_in").count() == 1


def test_wrong_password_is_401(client, db):
    user = make_user(db, UserRole.finance)
    assert _login(client, user.email, "wrong-password1").status_code == 401


def test_account_locks_after_repeated_wrong_passwords(client, db):
    user = make_user(db, UserRole.finance)
    for _ in range(settings.max_failed_logins):
        assert _login(client, user.email, "wrong-password1").status_code == 401
    # Locked: even the right password is refused for now.
    assert _login(client, user.email).status_code == 423


def test_suspended_user_cannot_sign_in(client, db):
    user = make_user(db, UserRole.finance)
    user.status = UserStatus.suspended
    db.flush()
    assert _login(client, user.email).status_code == 403


def test_portal_user_is_not_staff(client, db):
    user = make_user(db, UserRole.member)
    me = client.get("/api/v1/auth/me", headers=auth_headers(user)).json()
    assert me["is_staff"] is False


def test_forgot_password_queues_email_but_never_reveals_accounts(client, db):
    user = make_user(db, UserRole.member)
    known = client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@test.dev"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert db.query(NotificationOutbox).filter_by(recipient_address=user.email, event="auth.password_reset_link").count() == 1


def test_changing_password_signs_out_old_tokens(client, db):
    user = make_user(db, UserRole.finance)
    old = auth_headers(user)
    response = client.post("/api/v1/auth/change-password", headers=old,
                           json={"current_password": PASSWORD, "new_password": "NewPassword9"})
    assert response.status_code == 200
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401
    new = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=new).status_code == 200


def test_weak_password_is_rejected(client, db):
    user = make_user(db, UserRole.finance)
    response = client.post("/api/v1/auth/change-password", headers=auth_headers(user),
                           json={"current_password": PASSWORD, "new_password": "short"})
    assert response.status_code == 400
