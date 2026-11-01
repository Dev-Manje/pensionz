"""Investment options per fund (FR-CFG-007) — also covers the shared
FundConfig maker-checker in services/config_changes.py."""
import pytest

from app.models.identity import UserRole
from app.models.investment import InvestmentOption
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


def url(fund, suffix=""):
    return f"/api/v1/funds/{fund.id}/investment-options{suffix}"


def body(**overrides):
    return {"code": "gen", "name": "General Pool", "pricing_method": "declared_rate", "description": "", **overrides}


def approve(client, user, request_id):
    return client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(user), json={})


def create(client, db, fund, maker, checker, **overrides) -> InvestmentOption:
    response = client.post(url(fund), headers=auth_headers(maker), json=body(**overrides))
    assert response.status_code == 202, response.text
    assert approve(client, checker, response.json()["id"]).status_code == 200
    return db.query(InvestmentOption).filter_by(fund_id=fund.id, code=overrides.get("code", "gen").upper()).one()


def test_option_created_after_approval(client, db, fund, maker, checker):
    response = client.post(url(fund), headers=auth_headers(maker), json=body())
    assert response.status_code == 202
    assert response.json()["payload"]["code"] == "GEN"
    assert db.query(InvestmentOption).filter_by(fund_id=fund.id).count() == 0
    assert approve(client, maker, response.json()["id"]).status_code == 400
    assert approve(client, checker, response.json()["id"]).status_code == 200
    option = db.query(InvestmentOption).filter_by(fund_id=fund.id).one()
    assert option.description is None and option.pricing_method.value == "declared_rate"


def test_duplicate_code_and_pending_code(client, db, fund, maker, checker):
    create(client, db, fund, maker, checker)
    assert client.post(url(fund), headers=auth_headers(maker), json=body()).status_code == 409
    assert client.post(url(fund), headers=auth_headers(maker), json=body(code="MMK", name="Money Market")).status_code == 202
    assert client.post(url(fund), headers=auth_headers(maker), json=body(code="mmk", name="Again")).status_code == 409


def test_edit_and_close(client, db, fund, maker, checker):
    option = create(client, db, fund, maker, checker)
    response = client.put(url(fund, f"/{option.id}"), headers=auth_headers(maker), json=body(name="General Pool (closed)", status="closed"))
    assert response.status_code == 202, response.text
    assert response.json()["previous"]["status"] == "active"
    assert client.put(url(fund, f"/{option.id}"), headers=auth_headers(maker), json=body(name="Other")).status_code == 409  # one pending
    assert approve(client, checker, response.json()["id"]).status_code == 200
    db.refresh(option)
    assert option.status.value == "closed"
    assert client.put(url(fund, f"/{option.id}"), headers=auth_headers(maker), json=body(name="General Pool (closed)", status="closed")).status_code == 400


def test_rules(client, db, fund, maker, checker):
    assert client.post(url(fund), headers=auth_headers(maker), json=body(status="closed")).status_code == 400
    option = create(client, db, fund, maker, checker)
    assert client.put(url(fund, f"/{option.id}"), headers=auth_headers(maker), json=body(pricing_method="unit_price")).status_code == 400
    db_fund = make_fund(db, maker, checker, fund_type="defined_benefit")
    assert client.post(url(db_fund), headers=auth_headers(maker), json=body()).status_code == 400


def test_access(client, db, fund, maker, checker):
    option = create(client, db, fund, maker, checker)
    outsider = make_user(db, UserRole.scheme_config_maker)
    assert client.get(url(fund), headers=auth_headers(outsider)).status_code == 404
    assert client.put(url(fund, f"/{option.id}"), headers=auth_headers(outsider), json=body(name="X1")).status_code == 404
    finance = make_user(db, UserRole.finance)
    assert client.post(url(fund), headers=auth_headers(finance), json=body(code="NEW")).status_code == 403
    other_fund = make_fund(db, maker, checker)
    assert client.put(url(other_fund, f"/{option.id}"), headers=auth_headers(maker), json=body(name="X1")).status_code == 404
