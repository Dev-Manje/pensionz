"""Fee rules per fund (FR-CFG-008): maker-checker, basis/frequency rules,
no overlapping rules, employer rules override fund-wide ones."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.fee import FeeRule
from app.models.identity import UserRole
from app.models.scheme import Scheme
from app.services.fee_rules import rules_in_force
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
def scheme(db, fund):
    s = Scheme(fund_id=fund.id, code="EMP01", name="Employer Ltd", contribution_day=14)
    db.add(s)
    db.flush()
    return s


def body(**overrides):
    return {"code": "ADM", "name": "Administration fee", "fee_type": "administration", "basis": "pct_contributions", "rate": "1.5",
            "payer": "member", "frequency": "per_contribution", "effective_from": "2026-01-01", **overrides}


def url(fund, suffix=""):
    return f"/api/v1/funds/{fund.id}/fee-rules{suffix}"


def approve(client, user, request_id):
    return client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(user), json={})


def create(client, maker, checker, fund, **overrides):
    response = client.post(url(fund), headers=auth_headers(maker), json=body(**overrides))
    assert response.status_code == 202, response.text
    assert approve(client, checker, response.json()["id"]).status_code == 200
    return response.json()


def test_rule_created_after_approval(client, db, maker, checker, fund, scheme):
    response = client.post(url(fund), headers=auth_headers(maker), json=body(scheme_id=str(scheme.id), code="ADM-E"))
    assert response.status_code == 202, response.text
    assert response.json()["payload"]["employer"] == "EMP01 — Employer Ltd"
    assert db.query(FeeRule).filter_by(fund_id=fund.id).count() == 0
    assert approve(client, maker, response.json()["id"]).status_code == 400
    assert approve(client, checker, response.json()["id"]).status_code == 200
    rule = db.query(FeeRule).filter_by(fund_id=fund.id).one()
    assert rule.rate == Decimal("1.5") and rule.scheme_id == scheme.id


def test_basis_frequency_and_limits(client, db, maker, fund):
    post = lambda **kw: client.post(url(fund), headers=auth_headers(maker), json=body(**kw))  # noqa: E731
    assert post(frequency="monthly").status_code == 400
    assert post(basis="pct_assets", rate="0.75").status_code == 400  # per contribution only for % of contributions
    assert post(basis="pct_assets", rate="15", frequency="monthly").status_code == 400  # above 10% a year
    assert post(rate="120").status_code == 400
    assert post(effective_to="2025-12-31").status_code == 400
    other = make_fund(db, maker)
    foreign = Scheme(fund_id=other.id, code="X", name="Other", contribution_day=1)
    db.add(foreign)
    db.flush()
    assert post(scheme_id=str(foreign.id)).status_code == 400


def test_no_overlap_for_same_type_and_scope(client, db, maker, checker, fund, scheme):
    create(client, maker, checker, fund, effective_to="2026-12-31")
    assert client.post(url(fund), headers=auth_headers(maker), json=body(code="ADM2", effective_from="2026-06-01")).status_code == 409
    # Starting after the first ends is fine; so is an employer-specific rule over the same period.
    create(client, maker, checker, fund, code="ADM2", effective_from="2027-01-01", rate="1.75")
    create(client, maker, checker, fund, code="ADM-E", scheme_id=str(scheme.id), rate="1.25", payer="employer")


def test_employer_rule_overrides_fund_rule(client, db, maker, checker, fund, scheme):
    create(client, maker, checker, fund)
    create(client, maker, checker, fund, code="ADM-E", scheme_id=str(scheme.id), rate="1.25", payer="employer")
    create(client, maker, checker, fund, code="IMF", fee_type="investment_management", basis="pct_assets", rate="0.75",
           payer="fund", frequency="monthly")
    for_employer = {r.fee_type.value: r.rate for r in rules_in_force(db, fund.id, scheme.id, date(2026, 6, 1))}
    assert for_employer == {"administration": Decimal("1.25"), "investment_management": Decimal("0.75")}
    for_others = {r.fee_type.value: r.rate for r in rules_in_force(db, fund.id, None, date(2026, 6, 1))}
    assert for_others["administration"] == Decimal("1.5")
    assert rules_in_force(db, fund.id, None, date(2025, 6, 1)) == []


def test_change_and_access(client, db, maker, checker, fund):
    create(client, maker, checker, fund)
    rule = db.query(FeeRule).filter_by(fund_id=fund.id).one()
    assert client.put(url(fund, f"/{rule.id}"), headers=auth_headers(maker), json=body()).status_code == 400  # nothing changed
    response = client.put(url(fund, f"/{rule.id}"), headers=auth_headers(maker), json=body(effective_to="2026-12-31"))
    assert response.status_code == 202, response.text
    assert response.json()["previous"]["employer"] == "Whole fund"
    outsider = make_user(db, UserRole.scheme_config_maker)
    assert client.get(url(fund), headers=auth_headers(outsider)).status_code == 404
    finance = make_user(db, UserRole.finance)
    assert client.post(url(fund), headers=auth_headers(finance), json=body(code="NEW")).status_code == 403
