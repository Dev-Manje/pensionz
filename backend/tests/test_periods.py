"""Processing month per fund (FR-CFG-002): one open month, close rolls on,
re-open is maker-checker, postings guarded by require_open."""
from datetime import date

import pytest
from fastapi import HTTPException

from app.models.identity import UserRole
from app.models.period import FundPeriod, PeriodStatus
from app.services import fund_access, periods
from tests.factories import auth_headers, make_fund, make_user


@pytest.fixture
def finance(db):
    return make_user(db, UserRole.finance)


@pytest.fixture
def fund(db, finance):
    return make_fund(db, finance)


def url(fund, suffix=""):
    return f"/api/v1/funds/{fund.id}/periods{suffix}"


def open_first(client, fund, user, month="2026-10-01"):
    return client.post(url(fund, "/open"), headers=auth_headers(user), json={"period": month})


def test_open_first_month_once(client, db, fund, finance):
    response = open_first(client, fund, finance, "2026-10-17")
    assert response.status_code == 201
    body = response.json()
    assert body["current"]["period"] == "2026-10-01"  # any day → the month
    assert body["can_close"] is True and body["can_open_first"] is False
    assert open_first(client, fund, finance).status_code == 409


def test_only_finance_opens_and_closes(client, db, fund):
    officer = make_user(db, UserRole.contributions_officer)
    assert open_first(client, fund, officer).status_code == 403


def test_fund_scoping_applies(client, db, fund):
    other_finance = make_user(db, UserRole.finance)
    assert open_first(client, fund, other_finance).status_code == 404
    assert client.get(url(fund), headers=auth_headers(other_finance)).status_code == 404


def test_close_opens_next_month(client, db, fund, finance):
    open_first(client, fund, finance, "2026-12-01")
    response = client.post(url(fund, "/close"), headers=auth_headers(finance), json={"period": "2026-12-01"})
    assert response.status_code == 200
    body = response.json()
    assert body["current"]["period"] == "2027-01-01"  # year rolls over
    assert [p["status"] for p in body["history"]] == ["open", "closed"]
    assert {c["key"]: c["status"] for c in body["checklist"]}["ledger_balanced"] == "passed"  # empty ledger balances
    assert client.get(f"/api/v1/funds/{fund.id}", headers=auth_headers(finance)).json()["current_period"] == "2027-01-01"


def test_close_refuses_a_stale_month(client, db, fund, finance):
    open_first(client, fund, finance, "2026-10-01")
    client.post(url(fund, "/close"), headers=auth_headers(finance), json={"period": "2026-10-01"})
    again = client.post(url(fund, "/close"), headers=auth_headers(finance), json={"period": "2026-10-01"})
    assert again.status_code == 409


def test_close_blocked_by_a_failed_check(client, db, fund, finance, monkeypatch):
    open_first(client, fund, finance)
    monkeypatch.setattr(periods, "checklist", lambda db, fund, period: [periods.Check("x", "Schedules allocated", "failed")])
    response = client.post(url(fund, "/close"), headers=auth_headers(finance), json={"period": "2026-10-01"})
    assert response.status_code == 409
    assert "Schedules allocated" in response.json()["detail"]


def test_require_open_guards_postings(db, fund, finance):
    with pytest.raises(HTTPException) as no_month:
        periods.require_open(db, fund.id, date(2026, 10, 5))
    assert no_month.value.status_code == 409
    periods.open_first(db, finance, fund, date(2026, 10, 1))
    assert periods.require_open(db, fund.id, date(2026, 10, 31)).period == date(2026, 10, 1)
    with pytest.raises(HTTPException) as closed:
        periods.require_open(db, fund.id, date(2026, 9, 30))
    assert closed.value.status_code == 409


def test_reopen_needs_a_finance_checker(client, db, fund, finance):
    open_first(client, fund, finance)
    closed = client.post(url(fund, "/close"), headers=auth_headers(finance), json={"period": "2026-10-01"}).json()
    october = next(p for p in closed["history"] if p["period"] == "2026-10-01")

    assert client.post(url(fund, f"/{october['id']}/reopen"), headers=auth_headers(finance), json={"reason": "no"}).status_code == 422
    request = client.post(url(fund, f"/{october['id']}/reopen"), headers=auth_headers(finance), json={"reason": "Late schedule from employer"})
    assert request.status_code == 202
    request_id = request.json()["id"]
    assert client.get(url(fund), headers=auth_headers(finance)).json()["pending_reopen_approval_id"] == request_id
    # Still November until approved; the maker can't approve their own request.
    assert client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(finance), json={}).status_code == 400

    checker = make_user(db, UserRole.finance_checker)
    assert client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(checker), json={}).status_code == 404  # not their fund
    fund_access.grant(db, checker.id, fund.id, None)
    assert client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(checker), json={}).status_code == 200

    state = client.get(url(fund), headers=auth_headers(finance)).json()
    assert state["current"]["period"] == "2026-10-01"
    assert [p["period"] for p in state["history"]] == ["2026-10-01"]  # the empty November was withdrawn
    assert db.query(FundPeriod).filter_by(fund_id=fund.id, status=PeriodStatus.open).count() == 1


def test_only_latest_closed_month_can_be_reopened(client, db, fund, finance):
    open_first(client, fund, finance)
    client.post(url(fund, "/close"), headers=auth_headers(finance), json={"period": "2026-10-01"})
    state = client.post(url(fund, "/close"), headers=auth_headers(finance), json={"period": "2026-11-01"}).json()
    october = next(p for p in state["history"] if p["period"] == "2026-10-01")
    december = next(p for p in state["history"] if p["period"] == "2026-12-01")
    reason = {"reason": "Correction needed"}
    assert client.post(url(fund, f"/{october['id']}/reopen"), headers=auth_headers(finance), json=reason).status_code == 400
    assert client.post(url(fund, f"/{december['id']}/reopen"), headers=auth_headers(finance), json=reason).status_code == 400  # open, not closed


def test_reopen_refused_when_next_month_has_postings(client, db, fund, finance, monkeypatch):
    open_first(client, fund, finance)
    state = client.post(url(fund, "/close"), headers=auth_headers(finance), json={"period": "2026-10-01"}).json()
    october = next(p for p in state["history"] if p["period"] == "2026-10-01")
    request_id = client.post(url(fund, f"/{october['id']}/reopen"), headers=auth_headers(finance), json={"reason": "Correction needed"}).json()["id"]
    monkeypatch.setattr(periods, "has_postings", lambda db, fund_id, period: True)
    checker = make_user(db, UserRole.finance_checker)
    fund_access.grant(db, checker.id, fund.id, None)
    response = client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(checker), json={})
    assert response.status_code == 409
