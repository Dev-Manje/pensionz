"""Benefit categories (FR-CFG-004): effective-dated terms through
maker-checker, validated against regulatory minimums and the fund."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.category import BenefitCategory
from app.models.identity import UserRole
from app.models.investment import InvestmentOption, InvestmentOptionStatus, PricingMethod
from app.models.regulatory import RegulatoryParameterVersion
from app.models.scheme import Scheme
from app.services import config_resolver
from tests.factories import auth_headers, make_fund, make_user


@pytest.fixture
def maker(db):
    return make_user(db, UserRole.scheme_config_maker)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.scheme_config_checker)


@pytest.fixture
def regulatory(db):
    for key, value in {"min_employee_contribution_pct": "5", "min_employer_contribution_pct": "10",
                       "min_retirement_age": "50", "max_retirement_age": "70"}.items():
        db.add(RegulatoryParameterVersion(key=key, value=Decimal(value), effective_from=date(2023, 1, 1)))
    db.flush()


def _scheme(db, fund):
    scheme = Scheme(fund_id=fund.id, code="EMP01", name="Employer Ltd", contribution_day=14)
    db.add(scheme)
    db.flush()
    return scheme


@pytest.fixture
def dc(db, maker, checker, regulatory):
    fund = make_fund(db, maker, checker, fund_type="umbrella_dc")
    option = InvestmentOption(fund_id=fund.id, code="GEN", name="General Pool", pricing_method=PricingMethod.declared_rate)
    db.add(option)
    db.flush()
    return fund, _scheme(db, fund), option


def terms(option=None, **overrides):
    t = {"effective_from": "2026-01-01", "employee_rate": "5", "employer_rate": "10", "normal_retirement_age": 60,
         "min_entry_age": 18, "max_entry_age": 55, "waiting_period_months": 3,
         "vesting_scale": [{"years": 0, "vested_pct": "0"}, {"years": 5, "vested_pct": "100"}],
         "default_investment_option_id": str(option.id) if option else None, "group_life_multiple": "3"}
    t.update(overrides)
    return t


def propose(client, maker, scheme, t, code="STF"):
    return client.post(f"/api/v1/schemes/{scheme.id}/categories", headers=auth_headers(maker), json={"code": code, "name": "Staff", "terms": t})


def approve(client, user, request_id):
    return client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(user), json={})


def create(client, db, maker, checker, scheme, t) -> BenefitCategory:
    response = propose(client, maker, scheme, t)
    assert response.status_code == 202, response.text
    assert approve(client, checker, response.json()["id"]).status_code == 200
    return db.query(BenefitCategory).filter_by(scheme_id=scheme.id, code="STF").one()


def test_category_created_after_approval_with_readable_payload(client, db, maker, checker, dc):
    fund, scheme, option = dc
    response = propose(client, maker, scheme, terms(option))
    assert response.status_code == 202, response.text
    payload = response.json()["payload"]
    assert payload["employee_contribution"] == "5% of pensionable salary"
    assert payload["default_investment_option"] == "GEN — General Pool"
    assert payload["vesting_scale"][1] == "5 years' service: 100% vested"
    assert db.query(BenefitCategory).filter_by(scheme_id=scheme.id).count() == 0
    assert approve(client, maker, response.json()["id"]).status_code == 400
    assert approve(client, checker, response.json()["id"]).status_code == 200
    category = db.query(BenefitCategory).filter_by(scheme_id=scheme.id).one()
    current = config_resolver.category_terms(db, category.id, date(2026, 6, 1))
    assert current.employer_rate == Decimal("10") and current.design.value == "dc"
    assert config_resolver.category_terms(db, category.id, date(2025, 12, 31)) is None


def test_rates_below_statutory_minimum_refused(client, db, maker, dc):
    fund, scheme, option = dc
    response = propose(client, maker, scheme, terms(option, employer_rate="8"))
    assert response.status_code == 400
    assert "statutory minimum of 10%" in response.json()["detail"]
    # Fixed amounts can't be compared with a % minimum, so they're allowed.
    assert propose(client, maker, scheme, terms(option, employee_rate_type="fixed", employee_rate="2500")).status_code == 202


def test_retirement_age_band_and_fund_rules(client, db, maker, checker, dc):
    fund, scheme, option = dc
    assert propose(client, maker, scheme, terms(option, normal_retirement_age=72)).status_code == 400
    assert propose(client, maker, scheme, terms(None)).status_code == 400  # DC needs a default option
    assert propose(client, maker, scheme, terms(option, accrual_denominator=60, final_salary_months=36)).status_code == 400
    other = make_fund(db, maker, checker)
    foreign = InvestmentOption(fund_id=other.id, code="GEN", name="Other fund pool", pricing_method=PricingMethod.declared_rate)
    db.add(foreign)
    db.flush()
    assert propose(client, maker, scheme, terms(foreign)).status_code == 400
    option.status = InvestmentOptionStatus.closed
    db.flush()
    assert propose(client, maker, scheme, terms(option)).status_code == 400


def test_input_shape_rules(client, db, maker, dc):
    fund, scheme, option = dc
    assert propose(client, maker, scheme, terms(option, vesting_scale=[{"years": 5, "vested_pct": "100"}, {"years": 2, "vested_pct": "50"}])).status_code == 422
    assert propose(client, maker, scheme, terms(option, vesting_scale=[{"years": 2, "vested_pct": "60"}, {"years": 5, "vested_pct": "40"}])).status_code == 422
    assert propose(client, maker, scheme, terms(option, min_entry_age=40, max_entry_age=30)).status_code == 422
    assert propose(client, maker, scheme, terms(option, employee_rate="120")).status_code == 422


def test_db_category(client, db, maker, checker, regulatory):
    fund = make_fund(db, maker, checker, fund_type="defined_benefit")
    scheme = _scheme(db, fund)
    t = terms(None, employer_rate=None, vesting_scale=[])
    assert propose(client, maker, scheme, t).status_code == 400  # needs accrual + averaging
    response = propose(client, maker, scheme, {**t, "accrual_denominator": 60, "final_salary_months": 36})
    assert response.status_code == 202, response.text
    assert response.json()["payload"]["db_accrual"] == "1/60 of final salary per year of service"
    assert approve(client, checker, response.json()["id"]).status_code == 200
    category = db.query(BenefitCategory).filter_by(scheme_id=scheme.id).one()
    assert category.terms[0].design.value == "db" and category.terms[0].employer_rate is None


def test_new_terms_from_a_later_date_keep_history(client, db, maker, checker, dc):
    fund, scheme, option = dc
    category = create(client, db, maker, checker, scheme, terms(option))
    change = {"name": "Staff", "status": "active", "terms": terms(option, effective_from="2027-01-01", employer_rate="12")}
    early = {**change, "terms": terms(option, effective_from="2025-06-01", employer_rate="12")}
    assert client.put(f"/api/v1/categories/{category.id}", headers=auth_headers(maker), json=early).status_code == 400
    response = client.put(f"/api/v1/categories/{category.id}", headers=auth_headers(maker), json=change)
    assert response.status_code == 202, response.text
    request = response.json()
    assert request["previous"]["employer_contribution"] == "10% of pensionable salary"
    assert request["payload"]["employer_contribution"] == "12% of pensionable salary"
    assert approve(client, checker, request["id"]).status_code == 200
    assert config_resolver.category_terms(db, category.id, date(2026, 12, 31)).employer_rate == Decimal("10")
    assert config_resolver.category_terms(db, category.id, date(2027, 1, 1)).employer_rate == Decimal("12")
    detail = client.get(f"/api/v1/categories/{category.id}", headers=auth_headers(maker)).json()
    assert detail["upcoming"]["employer_rate"] == "12.000000" and len(detail["history"]) == 2


def test_rename_or_close_without_new_terms(client, db, maker, checker, dc):
    fund, scheme, option = dc
    category = create(client, db, maker, checker, scheme, terms(option))
    same = {"name": "Staff", "status": "active"}
    assert client.put(f"/api/v1/categories/{category.id}", headers=auth_headers(maker), json=same).status_code == 400
    response = client.put(f"/api/v1/categories/{category.id}", headers=auth_headers(maker), json={"name": "Staff", "status": "closed"})
    assert response.status_code == 202
    assert approve(client, checker, response.json()["id"]).status_code == 200
    db.refresh(category)
    assert category.status.value == "closed"


def test_duplicate_code_and_access(client, db, maker, checker, dc):
    fund, scheme, option = dc
    create(client, db, maker, checker, scheme, terms(option))
    assert propose(client, maker, scheme, terms(option)).status_code == 409
    outsider = make_user(db, UserRole.scheme_config_maker)
    assert propose(client, outsider, scheme, terms(option), code="NEW").status_code == 404
    assert client.get(f"/api/v1/schemes/{scheme.id}/categories", headers=auth_headers(outsider)).status_code == 404
    finance = make_user(db, UserRole.finance)
    assert propose(client, finance, scheme, terms(option), code="NEW").status_code == 403


def test_raising_a_minimum_lists_categories_that_fall_below(client, db, maker, checker, dc):
    fund, scheme, option = dc
    create(client, db, maker, checker, scheme, terms(option))
    response = client.post("/api/v1/regulatory/parameters/min_employer_contribution_pct/versions", headers=auth_headers(maker),
                           json={"value": "12", "effective_from": "2027-07-01"})
    assert response.status_code == 202
    assert response.json()["payload"]["categories_below_new_minimum"] == ["EMP01/STF (10% from 1 Jan 2026)"]
