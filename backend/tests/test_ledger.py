"""Fund ledger (FR-ACC-001…003): balanced posts per fund, open-month guard,
member transactions by component, exact reversals, immutability, access."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.identity import UserRole
from app.models.ledger import Component, LedgerLine
from app.models.member import Member
from app.models.period import FundPeriod, PeriodStatus
from app.models.mixins import utcnow
from app.services import ledger, periods
from app.services.ledger import MemberPosting, cr, dr
from tests.factories import auth_headers, make_fund, make_user

D = Decimal
TODAY = date(2026, 11, 2)


@pytest.fixture
def staff(db):
    return make_user(db, UserRole.contributions_officer)


@pytest.fixture
def fund(db, staff):
    fund = make_fund(db, staff)
    db.add(FundPeriod(fund_id=fund.id, period=date(2026, 11, 1), status=PeriodStatus.open, opened_at=utcnow()))
    db.flush()
    return fund


def make_member(db, fund, code="M0001") -> Member:
    member = Member(fund_id=fund.id, account_code=code, first_name="Test", last_name="Member", gender="female",
                    date_of_birth=date(1990, 1, 1), date_joined_fund=date(2024, 1, 1))
    db.add(member)
    db.flush()
    return member


def allocate(db, fund, member, ee="400.00", er="800.00", fee="12.00"):
    return ledger.post_member_transactions(
        db, fund.id, entity_type="test_allocation", entity_id="T1", entry_date=TODAY, description="Allocation",
        postings=[MemberPosting(member, 1, Component.employee, D(ee), contribution_month=date(2026, 10, 1)),
                  MemberPosting(member, 1, Component.employer, D(er), contribution_month=date(2026, 10, 1))],
        other_lines=[dr("2100", fee), cr("2500", fee)], user=None,
    )


def test_chart_is_created_once_per_fund(db, fund):
    first = ledger.ensure_chart(db, fund.id)
    assert {"1000", "2000", "2100", "2500", "4300"} <= set(first)
    assert ledger.ensure_chart(db, fund.id)["2000"].id == first["2000"].id
    assert set(ledger.ensure_chart(db, None)) == {"1500", "1510", "4500"}


def test_post_balanced_entry_numbers_per_fund(db, fund, staff):
    other = make_fund(db, staff)
    db.add(FundPeriod(fund_id=other.id, period=date(2026, 11, 1), status=PeriodStatus.open, opened_at=utcnow()))
    e1 = ledger.post(db, fund.id, entity_type="t", entity_id=None, entry_date=TODAY, description="x", lines=[dr("1000", "10"), cr("1200", "10")], user=None)
    e2 = ledger.post(db, fund.id, entity_type="t", entity_id=None, entry_date=TODAY, description="x", lines=[dr("1000", "5"), cr("1200", "5")], user=None)
    e3 = ledger.post(db, other.id, entity_type="t", entity_id=None, entry_date=TODAY, description="x", lines=[dr("1000", "5"), cr("1200", "5")], user=None)
    assert (e1.number, e2.number, e3.number) == (1, 2, 1)
    assert ledger.gl_balance(db, fund.id, "1000") == D("15.00")
    assert ledger.gl_balance(db, fund.id, "1200") == D("-15.00")


def test_unbalanced_post_is_refused(db, fund):
    with pytest.raises(HTTPException) as exc:
        ledger.post(db, fund.id, entity_type="t", entity_id=None, entry_date=TODAY, description="x",
                    lines=[dr("1000", "10.00"), cr("1200", "9.99")], user=None)
    assert exc.value.status_code == 500


def test_amounts_round_half_up_per_line(db, fund):
    entry = ledger.post(db, fund.id, entity_type="t", entity_id=None, entry_date=TODAY, description="x",
                        lines=[dr("1000", "10.005"), cr("1200", "10.005")], user=None)
    assert [l.debit + l.credit for l in entry.lines] == [D("10.01"), D("10.01")]


def test_unknown_gl_code_is_refused(db, fund):
    with pytest.raises(HTTPException) as exc:
        ledger.post(db, fund.id, entity_type="t", entity_id=None, entry_date=TODAY, description="x", lines=[dr("9999", "1"), cr("1200", "1")], user=None)
    assert exc.value.status_code == 409


def test_posting_outside_the_open_month_is_refused(db, fund):
    with pytest.raises(HTTPException) as exc:
        ledger.post(db, fund.id, entity_type="t", entity_id=None, entry_date=date(2026, 10, 31), description="x",
                    lines=[dr("1000", "1"), cr("1200", "1")], user=None)
    assert exc.value.status_code == 409


def test_member_transactions_post_by_type_and_tie_out(db, fund):
    member = make_member(db, fund)
    entry, rows = allocate(db, fund, member)
    assert [(r.transaction_code, r.component, r.amount) for r in rows] == [(1, Component.employee, D("400.00")), (1, Component.employer, D("800.00"))]
    # Type 1 maps to Dr 2100 / Cr 2000; the fee line rides in the same entry.
    assert ledger.gl_balance(db, fund.id, "2000") == D("1200.00")
    assert ledger.gl_balance(db, fund.id, "2100") == D("-1212.00")
    assert ledger.gl_balance(db, fund.id, "2500") == D("12.00")
    assert ledger.member_balance(db, member.id) == D("1200.00")
    by = ledger.member_balances_by_component(db, member.id)
    assert by[Component.employee] == {1: D("400.00")} and by[Component.employer] == {1: D("800.00")}
    t = ledger.tie_out(db, fund.id)
    assert t.balanced and t.ties
    assert periods.has_postings(db, fund.id, date(2026, 11, 1))
    check = next(c for c in periods.checklist(db, fund, periods.current(db, fund.id)) if c.key == "ledger_balanced")
    assert check.status == "passed"


def test_reversal_restores_exact_balances_and_pairs_types(db, fund):
    member = make_member(db, fund)
    before = {b.account.code: b.balance for b in ledger.account_balances(db, fund.id)}
    entry, _ = allocate(db, fund, member, ee="333.33", er="666.67", fee="10.00")
    reversal = ledger.reverse(db, entry, user=None, entry_date=TODAY, reason="Wrong month")
    assert reversal.reverses_entry_id == entry.id
    after = {b.account.code: b.balance for b in ledger.account_balances(db, fund.id)}
    assert all(after[c] == before[c] for c in before)
    assert ledger.member_balance(db, member.id) == D("0.00")
    codes = ledger.member_balances_by_component(db, member.id)[Component.employee]
    assert codes == {1: D("333.33"), 2: D("-333.33")}
    assert ledger.tie_out(db, fund.id).ties


def test_entry_reversed_only_once_and_reversal_not_reversed(db, fund):
    member = make_member(db, fund)
    entry, _ = allocate(db, fund, member)
    reversal = ledger.reverse(db, entry, user=None, entry_date=TODAY, reason="Wrong")
    with pytest.raises(HTTPException) as again:
        ledger.reverse(db, entry, user=None, entry_date=TODAY, reason="Again")
    assert again.value.status_code == 409
    with pytest.raises(HTTPException) as of_reversal:
        ledger.reverse(db, reversal, user=None, entry_date=TODAY, reason="Undo")
    assert of_reversal.value.status_code == 409


def test_ledger_rows_are_immutable(db, fund):
    member = make_member(db, fund)
    entry, _ = allocate(db, fund, member)
    line_id = entry.lines[0].id
    savepoint = db.begin_nested()
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE ledger_line SET debit = 1 WHERE id = :id"), {"id": line_id})
    savepoint.rollback()
    assert db.get(LedgerLine, line_id) is not None


def test_ledger_api_chart_entries_and_member_account(client, db, fund, staff):
    member = make_member(db, fund)
    allocate(db, fund, member)
    h = auth_headers(staff)
    chart = client.get(f"/api/v1/funds/{fund.id}/ledger/accounts", headers=h)
    assert chart.status_code == 200, chart.text
    body = chart.json()
    assert body["tie_out"]["balanced"] and body["tie_out"]["ties"]
    assert next(a for a in body["accounts"] if a["code"] == "2000")["balance"] == "1200.00"
    page = client.get(f"/api/v1/funds/{fund.id}/ledger/entries?account=2500", headers=h).json()
    assert page["total"] == 1 and page["items"][0]["reference"] == "JE-000001"
    assert page["items"][0]["lines"][0]["member_code"] == "M0001"
    account = client.get(f"/api/v1/members/{member.id}/transactions", headers=h).json()
    assert account["balance"] == "1200.00"
    assert {c["component"]: c["contributions"] for c in account["components"]} == {"employee": "400.00", "employer": "800.00"}


def test_ledger_api_access(client, db, fund):
    outsider = make_user(db, UserRole.contributions_officer)
    assert client.get(f"/api/v1/funds/{fund.id}/ledger/accounts", headers=auth_headers(outsider)).status_code == 404
    member = make_member(db, fund)
    assert client.get(f"/api/v1/members/{member.id}/transactions", headers=auth_headers(outsider)).status_code == 404
    portal = make_user(db, UserRole.principal_officer)
    assert client.get(f"/api/v1/funds/{fund.id}/ledger/accounts", headers=auth_headers(portal)).status_code == 403
