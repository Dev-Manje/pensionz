"""Participating employers / schemes (FR-CFG-003) through maker-checker,
with principal-officer links, scoped by fund."""
import pytest

from app.models.fund import FundStatus
from app.models.identity import UserRole, UserStatus
from app.models.scheme import Scheme
from app.services import fund_access
from tests.factories import auth_headers, make_fund, make_user


@pytest.fixture
def maker(db):
    return make_user(db, UserRole.scheme_config_maker)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.scheme_config_checker)


@pytest.fixture
def fund(db, maker, checker):
    return make_fund(db, maker, checker, fund_type="umbrella_dc")


@pytest.fixture
def officer(db):
    return make_user(db, UserRole.principal_officer)


def body(code="EMP01", **overrides):
    data = {"code": code, "name": "Kamuzu Tea Estates Ltd", "contribution_day": 14, "contact_name": "HR Manager",
            "email": "", "officer_ids": []}
    data.update(overrides)
    return data


def approve(client, user, request_id):
    return client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(user), json={})


def create(client, db, fund, maker, checker, **overrides) -> Scheme:
    response = client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker), json=body(**overrides))
    assert response.status_code == 202, response.text
    assert approve(client, checker, response.json()["id"]).status_code == 200
    return db.query(Scheme).filter_by(fund_id=fund.id, code=overrides.get("code", "EMP01")).one()


def test_employer_created_only_after_approval(client, db, fund, maker, checker, officer):
    response = client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker), json=body(officer_ids=[str(officer.id)]))
    assert response.status_code == 202
    assert response.json()["payload"]["principal_officers"][0]["email"] == officer.email
    assert db.query(Scheme).filter_by(fund_id=fund.id).count() == 0
    assert approve(client, maker, response.json()["id"]).status_code == 400  # own request
    assert approve(client, checker, response.json()["id"]).status_code == 200
    scheme = db.query(Scheme).filter_by(fund_id=fund.id).one()
    assert scheme.contribution_day == 14 and scheme.email is None
    assert [o.user_id for o in scheme.officers] == [officer.id]


def test_only_principal_officers_can_be_linked(client, db, fund, maker):
    not_po = make_user(db, UserRole.finance)
    response = client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker), json=body(officer_ids=[str(not_po.id)]))
    assert response.status_code == 400
    suspended = make_user(db, UserRole.principal_officer)
    suspended.status = UserStatus.suspended
    db.flush()
    assert client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker), json=body(officer_ids=[str(suspended.id)])).status_code == 400


def test_code_unique_within_fund_but_reusable_in_another(client, db, fund, maker, checker):
    create(client, db, fund, maker, checker)
    assert client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker), json=body(code="emp01")).status_code == 409
    other = make_fund(db, maker, checker)
    assert client.post(f"/api/v1/funds/{other.id}/schemes", headers=auth_headers(maker), json=body()).status_code == 202
    # A second request for the same code while the first waits is refused too.
    assert client.post(f"/api/v1/funds/{other.id}/schemes", headers=auth_headers(maker), json=body()).status_code == 409


def test_validation(client, db, fund, maker):
    post = lambda **kw: client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker), json=body(**kw))  # noqa: E731
    assert post(contribution_day=31).status_code == 422  # must exist in every month
    assert post(status="exited").status_code == 422  # exited needs an exit date
    assert post(join_date="2026-05-01", exit_date="2026-01-01").status_code == 422


def test_fund_not_taking_new_employers(client, db, fund, maker):
    fund.status = FundStatus.closed_to_new_members
    db.flush()
    assert client.post(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(maker), json=body()).status_code == 400


def test_edit_changes_officers_after_approval(client, db, fund, maker, checker, officer):
    scheme = create(client, db, fund, maker, checker, officer_ids=[str(officer.id)])
    second = make_user(db, UserRole.principal_officer)
    response = client.put(f"/api/v1/schemes/{scheme.id}", headers=auth_headers(maker),
                          json=body(contribution_day=10, officer_ids=[str(second.id)]))
    assert response.status_code == 202, response.text
    request = response.json()
    assert request["previous"]["contribution_day"] == 14
    assert client.get(f"/api/v1/schemes/{scheme.id}", headers=auth_headers(maker)).json()["pending_approval_id"] == request["id"]
    assert approve(client, checker, request["id"]).status_code == 200
    db.refresh(scheme)
    assert scheme.contribution_day == 10
    assert [o.user_id for o in scheme.officers] == [second.id]


def test_unchanged_edit_refused(client, db, fund, maker, checker):
    scheme = create(client, db, fund, maker, checker)
    response = client.put(f"/api/v1/schemes/{scheme.id}", headers=auth_headers(maker), json=body())
    assert response.status_code == 400


def test_scoped_to_the_fund(client, db, fund, maker, checker):
    scheme = create(client, db, fund, maker, checker)
    outsider = make_user(db, UserRole.member_admin)
    assert client.get(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(outsider)).status_code == 404
    assert client.get(f"/api/v1/schemes/{scheme.id}", headers=auth_headers(outsider)).status_code == 404
    fund_access.grant(db, outsider.id, fund.id, None)
    assert [s["code"] for s in client.get(f"/api/v1/funds/{fund.id}/schemes", headers=auth_headers(outsider)).json()] == ["EMP01"]
    assert client.put(f"/api/v1/schemes/{scheme.id}", headers=auth_headers(outsider), json=body(name="Other")).status_code == 403
    # A checker without the fund can't approve its employers.
    request_id = client.put(f"/api/v1/schemes/{scheme.id}", headers=auth_headers(maker), json=body(name="Renamed Estates")).json()["id"]
    other_checker = make_user(db, UserRole.scheme_config_checker)
    assert approve(client, other_checker, request_id).status_code == 404


def test_officer_candidates(client, db, maker, officer):
    rows = client.get("/api/v1/schemes/officer-candidates", headers=auth_headers(maker)).json()
    assert officer.email in [r["email"] for r in rows]
    finance = make_user(db, UserRole.finance)
    assert client.get("/api/v1/schemes/officer-candidates", headers=auth_headers(finance)).status_code == 403
