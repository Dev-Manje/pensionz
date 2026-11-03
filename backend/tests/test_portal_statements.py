"""Employer statements from the principal officer portal: statement of contributions,
contribution invoice and arrears statement (PDF). EMP01 has two members on 5% / 10%
of 200,000 and 100,000 = 45,000.00 a month from July 2026; as at 2 Nov 2026."""
from datetime import date
from decimal import Decimal

import pytest
from reportlab import rl_config

from app.models.contribution import ContributionSchedule
from app.models.fee import FeeBasis, FeeFrequency, FeePayer, FeeRule, FeeType
from app.models.identity import UserRole
from app.models.scheme import SchemeOfficer
from app.services import receipts
from app.services.io import employer_statements
from tests.factories import auth_headers, make_user
from tests.test_arrears import AS_AT, paid, staff, world  # noqa: F401 — fixtures

PO = "/api/v1/po"
D = Decimal


@pytest.fixture(autouse=True)
def readable_pdfs(monkeypatch):
    # Uncompressed page streams, so the tests can look for the figures.
    monkeypatch.setattr(rl_config, "pageCompression", 0)
    monkeypatch.setattr(receipts, "today", lambda: AS_AT)


def credited(db, fund, scheme, month, amounts):
    """An allocated schedule for the month, with its totals."""
    paid(db, fund, scheme, month, amounts)
    s = db.query(ContributionSchedule).filter_by(scheme_id=scheme.id, contribution_month=month).one()
    s.total = sum((l.total for l in s.lines), D("0"))
    s.line_count = len(s.lines)
    db.flush()
    return s


@pytest.fixture
def officer(db, world):
    user = make_user(db, UserRole.principal_officer)
    db.add(SchemeOfficer(scheme_id=world[1].id, user_id=user.id))
    db.flush()
    return user


def test_invoice_lists_expected_contributions_and_employer_fees(client, db, world, officer):
    fund, scheme, people = world
    db.add(FeeRule(fund_id=fund.id, scheme_id=None, code="ADM", name="Administration fee", fee_type=FeeType.administration,
                   basis=FeeBasis.pct_contributions, rate=D("2"), payer=FeePayer.employer, frequency=FeeFrequency.monthly,
                   effective_from=date(2020, 1, 1)))
    db.flush()
    response = client.get(f"{PO}/schemes/{scheme.id}/statements/invoice", headers=auth_headers(officer), params={"month": "2026-10-01"})
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    pdf = response.content
    assert b"30,000.00" in pdf and b"15,000.00" in pdf  # member totals (10,000 + 20,000; 5,000 + 10,000)
    assert b"45,000.00" in pdf and b"900.00" in pdf  # contributions; 2% employer fee
    assert b"MWK 45,900.00" in pdf and b"EMP01-202610" in pdf and b"14 November 2026" in pdf


def test_contribution_statement_months_and_members(client, db, world, officer):
    fund, scheme, (a, b) = world
    credited(db, fund, scheme, date(2026, 8, 1), [(a, D("10000"), D("20000")), (b, D("5000"), D("10000"))])
    credited(db, fund, scheme, date(2026, 9, 1), [(a, D("10000"), D("20000"))])
    pdf = employer_statements.contribution_statement(db, scheme, date(2026, 7, 1), date(2026, 10, 1), AS_AT)
    assert b"T08" in pdf and b"T09" in pdf
    assert b"75,000.00" in pdf  # 45,000 + 30,000 credited over the period
    assert b"60,000.00" in pdf  # member a: 2 × 30,000
    response = client.get(f"{PO}/schemes/{scheme.id}/statements/contributions", headers=auth_headers(officer),
                          params={"from_month": "2026-07-01", "to_month": "2026-10-01"})
    assert response.status_code == 200 and response.content[:4] == b"%PDF"
    assert client.get(f"{PO}/schemes/{scheme.id}/statements/contributions", headers=auth_headers(officer),
                      params={"from_month": "2026-10-01", "to_month": "2026-07-01"}).status_code == 400
    assert client.get(f"{PO}/schemes/{scheme.id}/statements/contributions", headers=auth_headers(officer),
                      params={"from_month": "2024-01-01", "to_month": "2026-10-01"}).status_code == 400


def test_arrears_statement_totals(client, db, world, officer):
    fund, scheme, (a, b) = world
    paid(db, fund, scheme, date(2026, 7, 1), [(a, D("10000"), D("20000")), (b, D("5000"), D("10000"))])
    pdf = client.get(f"{PO}/schemes/{scheme.id}/statements/arrears", headers=auth_headers(officer)).content
    # August and September overdue (45,000 each); October not due until 14 Nov.
    assert b"MWK 90,000.00" in pdf and b"Not due yet: Oct" in pdf


def test_statements_access(client, db, world, officer, staff):
    scheme = world[1]
    stranger = make_user(db, UserRole.principal_officer)
    for path, params in (("invoice", {"month": "2026-10-01"}), ("arrears", {})):
        assert client.get(f"{PO}/schemes/{scheme.id}/statements/{path}", headers=auth_headers(stranger), params=params).status_code == 404
        assert client.get(f"{PO}/schemes/{scheme.id}/statements/{path}", headers=auth_headers(staff), params=params).status_code == 403
    assert client.get(f"{PO}/schemes/{scheme.id}/statements/invoice", headers=auth_headers(officer),
                      params={"month": "2027-01-01"}).status_code == 400
