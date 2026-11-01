"""Regulatory parameters and tax tables (FR-CFG-009): effective-dated
versions through maker-checker, resolved by date."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.identity import UserRole
from app.models.regulatory import RegulatoryParameterVersion, TaxBand, TaxTable, TaxTableKind
from app.services import config_resolver
from tests.factories import auth_headers, make_user

KEY = "min_employer_contribution_pct"


@pytest.fixture
def maker(db):
    return make_user(db, UserRole.scheme_config_maker)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.scheme_config_checker)


def approve(client, user, request_id):
    return client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(user), json={})


def propose(client, maker, value="10", effective_from="2026-01-01", key=KEY):
    return client.post(f"/api/v1/regulatory/parameters/{key}/versions", headers=auth_headers(maker),
                       json={"value": value, "effective_from": effective_from, "source": "Pension Act 2023"})


def test_resolver_picks_the_version_in_force(db):
    db.add_all([
        RegulatoryParameterVersion(key="max_lump_sum_pct", value=Decimal("40"), effective_from=date(2011, 1, 1)),
        RegulatoryParameterVersion(key="max_lump_sum_pct", value=Decimal("50"), effective_from=date(2023, 7, 1)),
    ])
    db.flush()
    assert config_resolver.regulatory(db, "max_lump_sum_pct", date(2010, 12, 31)) is None
    assert config_resolver.regulatory(db, "max_lump_sum_pct", date(2023, 6, 30)) == Decimal("40")
    assert config_resolver.regulatory(db, "max_lump_sum_pct", date(2023, 7, 1)) == Decimal("50")


def test_new_value_applies_only_after_approval(client, db, maker, checker):
    response = propose(client, maker, "12.5", "2027-01-01")
    assert response.status_code == 202, response.text
    request = response.json()
    assert request["payload"]["value"] == "12.5%"
    assert config_resolver.regulatory(db, KEY, date(2027, 6, 1)) is None
    assert approve(client, maker, request["id"]).status_code == 400  # own request
    assert approve(client, checker, request["id"]).status_code == 200
    assert config_resolver.regulatory(db, KEY, date(2027, 6, 1)) == Decimal("12.5")

    listed = {p["key"]: p for p in client.get("/api/v1/regulatory/parameters", headers=auth_headers(maker)).json()}
    assert listed[KEY]["upcoming"]["display"] == "12.5%"
    assert listed[KEY]["pending_approval_id"] is None


def test_validation(client, db, maker, checker):
    assert propose(client, maker, "150").status_code == 400  # above 100%
    assert propose(client, maker, "3.5", key="unemployment_access_wait_months").status_code == 400  # whole months
    assert propose(client, maker, "5", key="no_such_parameter").status_code == 404
    assert approve(client, checker, propose(client, maker, "10", "2026-01-01").json()["id"]).status_code == 200
    assert propose(client, maker, "11", "2026-01-01").status_code == 409  # same date again


def test_one_pending_change_per_parameter(client, db, maker):
    assert propose(client, maker, "10", "2026-01-01").status_code == 202
    assert propose(client, maker, "11", "2026-06-01").status_code == 409


def test_back_dated_change_is_flagged_for_the_checker(client, db, maker):
    past = (date.today() - timedelta(days=30)).isoformat()
    assert "(back-dated)" in propose(client, maker, "10", past).json()["summary"]


def test_only_config_roles_propose_and_approve(client, db, maker):
    finance = make_user(db, UserRole.finance)
    assert propose(client, finance).status_code == 403
    request_id = propose(client, maker).json()["id"]
    assert approve(client, make_user(db, UserRole.finance_checker), request_id).status_code == 403
    assert client.get("/api/v1/regulatory/parameters", headers=auth_headers(finance)).status_code == 200
    po = make_user(db, UserRole.principal_officer)
    assert client.get("/api/v1/regulatory/parameters", headers=auth_headers(po)).status_code == 403


def make_table(db, effective_from=date(2024, 4, 1)):
    table = TaxTable(kind=TaxTableKind.paye_monthly, effective_from=effective_from)
    table.bands = [TaxBand(position=i, lower=Decimal(lo), rate_pct=Decimal(r))
                   for i, (lo, r) in enumerate([("0", "0"), ("150000", "25"), ("500000", "30"), ("2550000", "35")])]
    db.add(table)
    db.flush()
    return table


def test_progressive_tax_known_answers(db):
    table = make_table(db)
    assert config_resolver.tax_on(table, Decimal("100000")) == Decimal("0.00")
    # 350,000 × 25% = 87,500
    assert config_resolver.tax_on(table, Decimal("500000")) == Decimal("87500.00")
    # 87,500 + 2,050,000 × 30% + 450,000 × 35% = 87,500 + 615,000 + 157,500
    assert config_resolver.tax_on(table, Decimal("3000000")) == Decimal("860000.00")
    # 0.01 into the 25% band → 0.0025 → rounds half-up to 0.00
    assert config_resolver.tax_on(table, Decimal("150000.01")) == Decimal("0.00")


def test_tax_table_version_through_approval(client, db, maker, checker):
    make_table(db)
    bands = [{"lower": "0", "rate_pct": "0"}, {"lower": "200000", "rate_pct": "25"}, {"lower": "600000", "rate_pct": "30"}]
    response = client.post("/api/v1/regulatory/tax-tables/paye_monthly", headers=auth_headers(maker),
                           json={"effective_from": "2027-04-01", "bands": bands})
    assert response.status_code == 202, response.text
    assert response.json()["payload"]["bands"][1] == "MWK 200,000.00 – 600,000.00 at 25%"
    assert approve(client, checker, response.json()["id"]).status_code == 200
    calc = client.get("/api/v1/regulatory/tax-tables/paye_monthly/calculate?amount=500000&as_of=2027-05-01", headers=auth_headers(maker)).json()
    assert calc["tax"] == "75000.00" and calc["table_effective_from"] == "2027-04-01"
    old = client.get("/api/v1/regulatory/tax-tables/paye_monthly/calculate?amount=500000&as_of=2026-05-01", headers=auth_headers(maker)).json()
    assert old["tax"] == "87500.00"


def test_tax_table_validation(client, db, maker):
    post = lambda bands: client.post("/api/v1/regulatory/tax-tables/paye_monthly", headers=auth_headers(maker),  # noqa: E731
                                     json={"effective_from": "2027-04-01", "bands": bands})
    assert post([{"lower": "100", "rate_pct": "0"}]).status_code == 400  # must start at 0
    assert post([{"lower": "0", "rate_pct": "0"}, {"lower": "0", "rate_pct": "10"}]).status_code == 400  # not ascending
    assert post([{"lower": "0", "rate_pct": "120"}]).status_code == 422
