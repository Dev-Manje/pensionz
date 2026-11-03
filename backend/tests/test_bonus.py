"""Declared bonus (FR-EAR-001…004) with known answers — method decided 2026-11-03:
opening × rate × days/365 + each movement × rate × days to period end/365,
2 dp half-up per member per component; interim → final true-up; reversal."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.bonus import BonusDeclaration, BonusRun
from app.models.identity import UserRole
from app.models.ledger import Component, MemberTransaction
from app.models.mixins import utcnow
from app.models.period import FundPeriod, PeriodStatus
from app.services import ledger
from app.services.ledger import MemberPosting
from tests.factories import auth_headers, make_fund, make_user
from tests.test_ledger import make_member

D = Decimal
API = "/api/v1"


@pytest.fixture
def finance(db):
    return make_user(db, UserRole.finance)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.finance_checker)


@pytest.fixture
def fund(db, finance, checker):
    return make_fund(db, finance, checker, fund_type="umbrella_dc")


def open_month(db, fund, on: date) -> None:
    """Moves the fund's open processing month (tests post history directly)."""
    month = on.replace(day=1)
    for p in db.execute(select(FundPeriod).where(FundPeriod.fund_id == fund.id)).scalars():
        if p.status == PeriodStatus.open and p.period != month:
            p.status = PeriodStatus.closed
    db.flush()
    row = db.execute(select(FundPeriod).where(FundPeriod.fund_id == fund.id, FundPeriod.period == month)).scalar_one_or_none()
    if row is None:
        db.add(FundPeriod(fund_id=fund.id, period=month, status=PeriodStatus.open, opened_at=utcnow()))
    else:
        row.status = PeriodStatus.open
    db.flush()


def credit(db, fund, member, on: date, ee="0", er="0", code=1):
    open_month(db, fund, on)
    postings = [MemberPosting(member, code, c, D(v)) for c, v in ((Component.employee, ee), (Component.employer, er)) if D(v)]
    ledger.post_member_transactions(db, fund.id, entity_type="test", entity_id=None, entry_date=on, description="test",
                                    postings=postings, user=None)


def declare(client, db, finance, checker, fund, kind, start, end, rate):
    response = client.post(f"{API}/funds/{fund.id}/bonus-declarations", headers=auth_headers(finance),
                           json={"kind": kind, "period_start": start, "period_end": end, "rate": rate})
    assert response.status_code == 202, response.text
    assert client.post(f"{API}/approvals/{response.json()['id']}/approve", headers=auth_headers(checker), json={}).status_code == 200
    return db.query(BonusDeclaration).filter_by(fund_id=fund.id, kind=kind, period_start=date.fromisoformat(start)).one()


def run(client, finance, declaration, **body):
    response = client.post(f"{API}/bonus-declarations/{declaration.id}/runs", headers=auth_headers(finance), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def post(client, db, finance, checker, run_id):
    request = client.post(f"{API}/bonus-runs/{run_id}/submit", headers=auth_headers(finance))
    assert request.status_code == 202, request.text
    approved = client.post(f"{API}/approvals/{request.json()['id']}/approve", headers=auth_headers(checker), json={})
    assert approved.status_code == 200, approved.text
    return client.get(f"{API}/bonus-runs/{run_id}", headers=auth_headers(finance)).json()


def bonus_rows(db, member, code=6):
    return db.query(MemberTransaction).filter_by(member_id=member.id, transaction_code=code).all()


def test_opening_balance_full_year_known_answer(client, db, fund, finance, checker):
    member = make_member(db, fund)
    credit(db, fund, member, date(2024, 12, 15), ee="400000", er="800000")
    declaration = declare(client, db, finance, checker, fund, "final", "2025-01-01", "2025-12-31", "8")
    open_month(db, fund, date(2026, 11, 3))
    preview = run(client, finance, declaration, posting_date="2026-11-03")
    lines = {l["component"]: l for l in preview["lines"]}
    assert lines["employee"]["calculated"] == "32000.00" and lines["employer"]["calculated"] == "64000.00"
    assert lines["employee"]["days"] == 365 and preview["total_credit"] == "96000.00"
    done = post(client, db, finance, checker, preview["id"])
    assert done["status"] == "posted"
    rows = {r.component: r for r in bonus_rows(db, member)}
    assert rows[Component.employee].amount == D("32000.00") and rows[Component.employee].contribution_month == date(2025, 12, 1)
    tie = ledger.tie_out(db, fund.id)
    assert tie.balanced and tie.ties and ledger.gl_balance(db, fund.id, "2600") == D("-96000.00")
    # Idempotent: one final run per declaration.
    again = client.post(f"{API}/bonus-declarations/{declaration.id}/runs", headers=auth_headers(finance), json={})
    assert again.status_code == 409


def test_contribution_in_period_is_time_weighted(client, db, fund, finance, checker):
    member = make_member(db, fund)
    credit(db, fund, member, date(2025, 12, 20), ee="100000")
    credit(db, fund, member, date(2026, 3, 31), ee="10000")
    declaration = declare(client, db, finance, checker, fund, "final", "2026-01-01", "2026-06-30", "6.5")
    open_month(db, fund, date(2026, 11, 3))
    preview = run(client, finance, declaration, posting_date="2026-11-03")
    line = preview["lines"][0]
    # 100,000 × 6.5% × 181/365 + 10,000 × 6.5% × 92/365 = 3,223.29 + 163.84
    assert (line["days"], line["opening_balance"], line["movements"], line["calculated"]) == (181, "100000.00", "10000.00", "3387.12")


def test_interim_then_final_true_up(client, db, fund, finance, checker):
    leaver, stayer = make_member(db, fund, "M0001"), make_member(db, fund, "M0002")
    credit(db, fund, leaver, date(2025, 12, 20), ee="100000")
    credit(db, fund, stayer, date(2025, 12, 20), ee="100000")
    leaver.exit_date = date(2026, 4, 30)
    db.flush()
    interim = declare(client, db, finance, checker, fund, "interim", "2026-01-01", "2026-06-30", "5")
    open_month(db, fund, date(2026, 11, 3))
    preview = run(client, finance, interim, member_ids=[str(leaver.id)], posting_date="2026-11-03")
    assert [(l["account_code"], l["days"], l["calculated"]) for l in preview["lines"]] == [("M0001", 120, "1643.84")]
    post(client, db, finance, checker, preview["id"])

    final = declare(client, db, finance, checker, fund, "final", "2026-01-01", "2026-06-30", "6.5")
    lines = {l["account_code"]: l for l in run(client, finance, final, posting_date="2026-11-03")["lines"]}
    # Leaver: to the exit date at the final rate, less the interim already credited.
    assert (lines["M0001"]["calculated"], lines["M0001"]["already_credited"], lines["M0001"]["amount"]) == ("2136.99", "1643.84", "493.15")
    assert lines["M0002"]["amount"] == "3223.29"


def test_final_below_interim_takes_bonus_back(client, db, fund, finance, checker):
    leaver = make_member(db, fund)
    credit(db, fund, leaver, date(2025, 12, 20), ee="100000")
    leaver.exit_date = date(2026, 4, 30)
    db.flush()
    interim = declare(client, db, finance, checker, fund, "interim", "2026-01-01", "2026-06-30", "5")
    open_month(db, fund, date(2026, 11, 3))
    post(client, db, finance, checker, run(client, finance, interim, member_ids=[str(leaver.id)], posting_date="2026-11-03")["id"])
    final = declare(client, db, finance, checker, fund, "final", "2026-01-01", "2026-06-30", "4")
    done = post(client, db, finance, checker, run(client, finance, final, posting_date="2026-11-03")["id"])
    assert done["total_debit"] == "328.77"
    assert [r.amount for r in bonus_rows(db, leaver, code=5)] == [D("328.77")]
    assert ledger.member_balance(db, leaver.id) == D("101315.07")


def test_earlier_bonus_counts_in_the_next_opening_balance(client, db, fund, finance, checker):
    member = make_member(db, fund)
    credit(db, fund, member, date(2025, 12, 20), ee="100000")
    h1 = declare(client, db, finance, checker, fund, "final", "2026-01-01", "2026-06-30", "6.5")
    open_month(db, fund, date(2026, 7, 15))  # H1 bonus posted in July, inside H2
    post(client, db, finance, checker, run(client, finance, h1, posting_date="2026-07-15")["id"])
    h2 = declare(client, db, finance, checker, fund, "interim", "2026-07-01", "2026-12-31", "6")
    preview = run(client, finance, h2, member_ids=[str(member.id)], as_at="2026-07-31", posting_date="2026-07-31")
    line = preview["lines"][0]
    assert line["opening_balance"] == "103223.29" and line["movements"] == "0.00"


def test_reversal_whole_run_and_individual(client, db, fund, finance, checker):
    a, b = make_member(db, fund, "M0001"), make_member(db, fund, "M0002")
    for m in (a, b):
        credit(db, fund, m, date(2024, 12, 15), ee="400000", er="800000")
    declaration = declare(client, db, finance, checker, fund, "final", "2025-01-01", "2025-12-31", "8")
    open_month(db, fund, date(2026, 11, 3))
    done = post(client, db, finance, checker, run(client, finance, declaration, posting_date="2026-11-03")["id"])
    one = client.post(f"{API}/bonus-runs/{done['id']}/reverse", headers=auth_headers(finance),
                      json={"reason": "Wrong member", "member_ids": [str(a.id)]})
    assert one.status_code == 202, one.text
    assert client.post(f"{API}/approvals/{one.json()['id']}/approve", headers=auth_headers(checker), json={}).status_code == 200
    assert ledger.member_balance(db, a.id) == D("1200000.00") and ledger.member_balance(db, b.id) == D("1296000.00")
    assert client.get(f"{API}/bonus-runs/{done['id']}", headers=auth_headers(finance)).json()["status"] == "posted"
    rest = client.post(f"{API}/bonus-runs/{done['id']}/reverse", headers=auth_headers(finance), json={"reason": "Rate corrected"})
    assert client.post(f"{API}/approvals/{rest.json()['id']}/approve", headers=auth_headers(checker), json={}).status_code == 200
    assert client.get(f"{API}/bonus-runs/{done['id']}", headers=auth_headers(finance)).json()["status"] == "reversed"
    assert ledger.member_balance(db, b.id) == D("1200000.00") and ledger.gl_balance(db, fund.id, "2600") == D("0.00")
    # Once reversed, the declaration can be run again.
    assert client.post(f"{API}/bonus-declarations/{declaration.id}/runs", headers=auth_headers(finance), json={}).status_code == 201


def test_checks_and_access(client, db, fund, finance, checker):
    member = make_member(db, fund)
    credit(db, fund, member, date(2024, 12, 15), ee="1000")
    bad = client.post(f"{API}/funds/{fund.id}/bonus-declarations", headers=auth_headers(finance),
                      json={"kind": "final", "period_start": "2025-06-30", "period_end": "2025-01-01", "rate": "5"})
    assert bad.status_code == 400
    member_admin = make_user(db, UserRole.member_admin)
    assert client.post(f"{API}/funds/{fund.id}/bonus-declarations", headers=auth_headers(member_admin),
                       json={"kind": "final", "period_start": "2025-01-01", "period_end": "2025-12-31", "rate": "5"}).status_code == 403
    request = client.post(f"{API}/funds/{fund.id}/bonus-declarations", headers=auth_headers(finance),
                          json={"kind": "final", "period_start": "2025-01-01", "period_end": "2025-12-31", "rate": "5"})
    assert client.post(f"{API}/approvals/{request.json()['id']}/approve", headers=auth_headers(finance), json={}).status_code == 400
    assert client.post(f"{API}/approvals/{request.json()['id']}/approve", headers=auth_headers(checker), json={}).status_code == 200
    declaration = db.query(BonusDeclaration).filter_by(fund_id=fund.id).one()
    overlap = client.post(f"{API}/funds/{fund.id}/bonus-declarations", headers=auth_headers(finance),
                          json={"kind": "final", "period_start": "2025-06-01", "period_end": "2026-05-31", "rate": "5"})
    assert overlap.status_code == 409
    outsider = make_user(db, UserRole.finance)
    make_fund(db, outsider)
    assert client.get(f"{API}/funds/{fund.id}/bonus-declarations", headers=auth_headers(outsider)).status_code == 404
    # Balances that change after the preview stop the posting.
    open_month(db, fund, date(2026, 11, 3))
    preview = run(client, finance, declaration, posting_date="2026-11-03")
    request = client.post(f"{API}/bonus-runs/{preview['id']}/submit", headers=auth_headers(finance)).json()
    # A back-dated correction lands in the period: simulate with a transaction dated inside 2025.
    open_month(db, fund, date(2025, 6, 15))
    credit(db, fund, member, date(2025, 6, 15), ee="5000")
    open_month(db, fund, date(2026, 11, 3))
    stale = client.post(f"{API}/approvals/{request['id']}/approve", headers=auth_headers(checker), json={})
    assert stale.status_code == 409 and "changed since the preview" in stale.json()["detail"]
    assert db.get(BonusRun, preview["id"]).status.value == "pending_approval"
