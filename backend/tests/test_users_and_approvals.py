"""User administration goes through maker-checker (FR-SEC-002)."""
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.audit import AuditEvent
from app.models.identity import User, UserRole, UserStatus
from app.models.notification import NotificationOutbox, UserNotification
from tests.factories import auth_headers, make_user

NEW_USER = {"email": "new.officer@test.dev", "full_name": "New Officer", "roles": ["contributions_officer"]}


def _propose(client, maker, body=NEW_USER):
    return client.post("/api/v1/users", headers=auth_headers(maker), json=body)


def test_creating_a_user_waits_for_a_second_admin(client, db):
    maker = make_user(db, UserRole.admin)
    response = _propose(client, maker)
    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert db.query(User).filter_by(email=NEW_USER["email"]).first() is None


def test_checkers_are_notified_of_pending_request(client, db):
    maker = make_user(db, UserRole.admin)
    checker = make_user(db, UserRole.admin)
    _propose(client, maker)
    assert db.query(UserNotification).filter_by(user_id=checker.id, event="approval.needed").count() == 1
    assert db.query(UserNotification).filter_by(user_id=maker.id, event="approval.needed").count() == 0


def test_admin_cannot_approve_own_request(client, db):
    maker = make_user(db, UserRole.admin)
    request_id = _propose(client, maker).json()["id"]
    response = client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(maker), json={})
    assert response.status_code == 400


def test_second_admin_approves_and_user_is_invited(client, db):
    maker = make_user(db, UserRole.admin)
    checker = make_user(db, UserRole.admin)
    request_id = _propose(client, maker).json()["id"]
    response = client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(checker), json={})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    created = db.query(User).filter_by(email=NEW_USER["email"]).one()
    assert created.roles == [UserRole.contributions_officer]
    assert db.query(NotificationOutbox).filter_by(recipient_address=NEW_USER["email"], event="auth.invite").count() == 1
    assert db.query(AuditEvent).filter_by(entity_type="user", entity_id=str(created.id), action="created").count() == 1


def test_double_approve_is_409(client, db):
    maker = make_user(db, UserRole.admin)
    checker = make_user(db, UserRole.admin)
    request_id = _propose(client, maker).json()["id"]
    client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(checker), json={})
    again = client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(checker), json={})
    assert again.status_code == 409


def test_non_admin_cannot_approve_user_access(client, db):
    maker = make_user(db, UserRole.admin)
    other = make_user(db, UserRole.finance_checker)
    request_id = _propose(client, maker).json()["id"]
    assert client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(other), json={}).status_code == 403


def test_reject_needs_a_reason_and_tells_the_maker(client, db):
    maker = make_user(db, UserRole.admin)
    checker = make_user(db, UserRole.admin)
    request_id = _propose(client, maker).json()["id"]
    assert client.post(f"/api/v1/approvals/{request_id}/reject", headers=auth_headers(checker), json={}).status_code == 400
    response = client.post(f"/api/v1/approvals/{request_id}/reject", headers=auth_headers(checker), json={"comment": "Wrong role"})
    assert response.json()["status"] == "rejected"
    assert db.query(UserNotification).filter_by(user_id=maker.id, event="approval.rejected").count() == 1


def test_role_change_applies_only_after_approval(client, db):
    maker = make_user(db, UserRole.admin)
    checker = make_user(db, UserRole.admin)
    target = make_user(db, UserRole.finance)
    response = client.patch(f"/api/v1/users/{target.id}", headers=auth_headers(maker), json={"roles": ["finance", "finance_checker"]})
    assert response.status_code == 202
    assert response.json()["previous"] == {"roles": ["finance"]}
    db.refresh(target)
    assert target.roles == [UserRole.finance]
    client.post(f"/api/v1/approvals/{response.json()['id']}/approve", headers=auth_headers(checker), json={})
    db.refresh(target)
    assert set(target.roles) == {UserRole.finance, UserRole.finance_checker}


def test_only_one_pending_change_per_user(client, db):
    maker = make_user(db, UserRole.admin)
    target = make_user(db, UserRole.finance)
    client.patch(f"/api/v1/users/{target.id}", headers=auth_headers(maker), json={"status": "suspended"})
    second = client.patch(f"/api/v1/users/{target.id}", headers=auth_headers(maker), json={"full_name": "Someone Else"})
    assert second.status_code == 409


def test_suspending_signs_the_user_out(client, db):
    maker = make_user(db, UserRole.admin)
    checker = make_user(db, UserRole.admin)
    target = make_user(db, UserRole.finance)
    headers = auth_headers(target)
    request_id = client.patch(f"/api/v1/users/{target.id}", headers=auth_headers(maker), json={"status": "suspended"}).json()["id"]
    client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(checker), json={})
    db.refresh(target)
    assert target.status == UserStatus.suspended
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_non_admin_cannot_list_or_propose_users(client, db):
    officer = make_user(db, UserRole.contributions_officer)
    assert client.get("/api/v1/users", headers=auth_headers(officer)).status_code == 403
    assert _propose(client, officer).status_code == 403


def test_portal_users_cannot_reach_approvals(client, db):
    po = make_user(db, UserRole.principal_officer)
    assert client.get("/api/v1/approvals", headers=auth_headers(po)).status_code == 403


def test_maker_sees_own_request_and_can_cancel(client, db):
    maker = make_user(db, UserRole.admin)
    request_id = _propose(client, maker).json()["id"]
    mine = client.get("/api/v1/approvals", headers=auth_headers(maker)).json()
    assert any(r["id"] == request_id and r["can_cancel"] and not r["can_review"] for r in mine)
    response = client.post(f"/api/v1/approvals/{request_id}/cancel", headers=auth_headers(maker))
    assert response.json()["status"] == "cancelled"
    assert db.get(ApprovalRequest, response.json()["id"]).status == ApprovalStatus.cancelled


def test_notification_inbox_is_private(client, db):
    maker = make_user(db, UserRole.admin)
    checker = make_user(db, UserRole.admin)
    _propose(client, maker)
    checker_items = client.get("/api/v1/me/notifications", headers=auth_headers(checker)).json()["items"]
    assert len(checker_items) == 1
    item_id = checker_items[0]["id"]
    assert client.post(f"/api/v1/me/notifications/{item_id}/read", headers=auth_headers(maker)).status_code == 404
    assert client.post(f"/api/v1/me/notifications/{item_id}/read", headers=auth_headers(checker)).status_code == 204
    assert client.get("/api/v1/me/notifications/unread-count", headers=auth_headers(checker)).json() == {"unread": 0}
