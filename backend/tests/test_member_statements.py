"""Member enquiries and statements (FR-ENQ-001, 003, 008) with known answers, PDFs,
bulk statements and access."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.identity import UserRole
from app.models.ledger import Component
from app.models.notification import NotificationOutbox
from app.services import member_statements as ms
from app.services.ledger import MemberPosting
from app.services import ledger
from tests.factories import auth_headers, make_fund, make_user
from tests.test_bonus import open_month
from tests.test_ledger import make_member

D = Decimal
API = "/api/v1"


@pytest.fixture
def staff(db):
    return make_user(db, UserRole.member_admin)


@pytest.fixture
def fund(db, staff):
    return make_fund(db, staff, fund_type="umbrella_dc")


def post(db, fund, member, on, *postings):
    open_month(db, fund, on)
    ledger.post_member_transactions(db, fund.id, entity_type="test", entity_id=None, entry_date=on, description="test",
                                    postings=[MemberPosting(member, code, comp, D(amount), contribution_month=month,
                                                            description=desc) for code, comp, amount, month, desc in postings],
                                    user=None)


@pytest.fixture
def history(db, fund):
    member = make_member(db, fund)
    post(db, fund, member, date(2026, 1, 20),
         (1, Component.employee, "1000", date(2026, 1, 1), "Contributions for Jan 2026"),
         (1, Component.employer, "2000", date(2026, 1, 1), "Contributions for Jan 2026"),
         (1, Component.voluntary, "300", date(2026, 1, 1), "AVC Jan 2026"),
         (1, Component.severance, "500", date(2026, 1, 1), "Severance"))
    post(db, fund, member, date(2026, 7, 10),
         (6, Component.employee, "50", date(2026, 6, 1), "Bonus H1"),
         (6, Component.employer, "100", date(2026, 6, 1), "Bonus H1"),
         (6, Component.voluntary, "15", date(2026, 6, 1), "Bonus H1"))
    post(db, fund, member, date(2026, 9, 5), (3, Component.employee, "200", None, "Partial withdrawal"))
    return member


def test_benefit_statement_layout_known_answer(db, history):
    s = ms.benefit_statement(db, history, date(2026, 10, 31))
    assert dict(s.employee_lines) == {"Employee contributions": D("1000"), "Bonus on employee contributions": D("50"),
                                      "Employee voluntary contributions": D("300"), "Bonus on voluntary contributions": D("15"),
                                      "Less employee withdrawals": D("-200")}
    assert (s.employee_total, s.employer_total, s.total) == (D("1165"), D("2600"), D("3765"))
    assert s.contributions_up_to == date(2026, 1, 1)
    # As at a date before the bonus: only the contributions.
    assert ms.benefit_statement(db, history, date(2026, 6, 30)).total == D("3800")


def test_client_statement_running_balance_and_trails(db, history):
    s = ms.client_statement(db, history, date(2026, 7, 1), date(2026, 12, 31))
    assert s.opening == D("3800") and [l.balance for l in s.lines] == [D("3850"), D("3950"), D("3965"), D("3765")]
    assert s.lines[-1].debit == D("200") and s.closing == D("3765")
    trail = ms.transaction_trail(db, history, date(2026, 1, 1), date(2026, 12, 31))
    assert trail.totals[Component.employee] == (D("200"), D("1050"))
    months = {m.month: m for m in ms.contributions_trail(db, history, date(2026, 1, 1), date(2026, 12, 31))}
    assert (months[date(2026, 1, 1)].employee, months[date(2026, 1, 1)].company, months[date(2026, 1, 1)].voluntary) == (D("1000"), D("2500"), D("300"))
    assert (months[date(2026, 6, 1)].employee_earning, months[date(2026, 6, 1)].company_earning) == (D("50"), D("100"))


def test_enquiry_endpoints_and_pdfs(client, db, staff, history):
    headers = auth_headers(staff)
    summary = client.get(f"{API}/members/{history.id}/enquiry", headers=headers).json()
    assert summary["balance"] == "3765.00" and summary["employee_total"] == "1165.00" and summary["has_portal_login"] is False
    statement = client.get(f"{API}/members/{history.id}/statement?start=2026-07-01&end=2026-12-31", headers=headers).json()
    assert statement["opening"] == "3800.00" and len(statement["lines"]) == 4
    for kind in ("benefit", "client", "trail", "contributions", "voluntary"):
        pdf = client.get(f"{API}/members/{history.id}/documents/{kind}?start=2026-01-01&end=2026-12-31", headers=headers)
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF", kind
    assert client.get(f"{API}/members/{history.id}/statement?start=2026-12-01&end=2026-01-01", headers=headers).status_code == 400


def test_enquiry_access(client, db, history):
    outsider = make_user(db, UserRole.member_admin)
    make_fund(db, outsider)
    assert client.get(f"{API}/members/{history.id}/enquiry", headers=auth_headers(outsider)).status_code == 404
    officer = make_user(db, UserRole.principal_officer)
    assert client.get(f"{API}/members/{history.id}/enquiry", headers=auth_headers(officer)).status_code == 403


def test_bulk_statements_and_publish(client, db, staff, fund, history):
    other = make_member(db, fund, "M0002")
    other.email = "m2@example.mw"
    db.flush()
    pdf = client.get(f"{API}/funds/{fund.id}/benefit-statements?as_at=2026-10-31", headers=auth_headers(staff))
    assert pdf.status_code == 200 and pdf.content.count(b"/Type /Page\n") + pdf.content.count(b"/Type /Page ") >= 1
    done = client.post(f"{API}/funds/{fund.id}/benefit-statements/publish", headers=auth_headers(staff), json={"as_at": "2026-10-31"})
    assert done.json() == {"members": 2, "notified": 1}
    assert db.query(NotificationOutbox).filter_by(event="member.statement_ready", recipient_address="m2@example.mw").count() == 1
    finance = make_user(db, UserRole.finance)
    assert client.post(f"{API}/funds/{fund.id}/benefit-statements/publish", headers=auth_headers(finance), json={"as_at": "2026-10-31"}).status_code == 403
