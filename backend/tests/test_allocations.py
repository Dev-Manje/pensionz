"""Allocation (FR-CON-005, FR-CON-006): fees by payer, receipts must cover the
schedule exactly (hold until resolved), maker-checker, Initial Allocation
posting with known answers, holds on receipt money, re-checks at approval."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.approval import ApprovalRequest
from app.models.category import BenefitCategory, BenefitCategoryTerms, BenefitDesign
from app.models.contribution import AllocationStatus, ContributionAllocation, PaymentMethod, ScheduleSource, ScheduleStatus
from app.models.fee import FeeBasis, FeeFrequency, FeePayer, FeeRule, FeeType
from app.models.fund import FundBankAccount
from app.models.identity import UserRole
from app.models.ledger import Component
from app.models.member import Member, MemberSalary, MemberStatus
from app.models.mixins import utcnow
from app.models.period import FundPeriod, PeriodStatus
from app.models.reference import Bank
from app.models.scheme import Scheme
from app.services import allocations, approvals, ledger, receipts, schedules
from sqlalchemy import select
from tests.factories import auth_headers, make_fund, make_user

D = Decimal
TODAY = date.today()
MONTH = periods_month = date(TODAY.year - (TODAY.month == 1), (TODAY.month - 2) % 12 + 1, 1)  # last month


@pytest.fixture
def officer(db):
    return make_user(db, UserRole.contributions_officer)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.contributions_checker)


@pytest.fixture
def world(db, officer, checker):
    fund = make_fund(db, officer, checker, fund_type="umbrella_dc")
    db.add(FundPeriod(fund_id=fund.id, period=TODAY.replace(day=1), status=PeriodStatus.open, opened_at=utcnow()))
    scheme = Scheme(fund_id=fund.id, code="EMP01", name="Employer Ltd", contribution_day=14)
    db.add(scheme)
    db.flush()
    cat = BenefitCategory(scheme_id=scheme.id, fund_id=fund.id, code="STF", name="Staff")
    db.add(cat)
    db.flush()
    db.add(BenefitCategoryTerms(category_id=cat.id, effective_from=date(2020, 1, 1), design=BenefitDesign.dc, employee_rate=D("5"),
                                employer_rate=D("10"), normal_retirement_age=60))
    people = []
    for i, salary in enumerate(("200000", "100000"), start=1):
        m = Member(fund_id=fund.id, scheme_id=scheme.id, category_id=cat.id, account_code=f"EMP01{i:04d}", first_name=f"P{i}", last_name="T",
                   gender="male", date_of_birth=date(1990, 1, 1), date_joined_fund=date(2024, 1, 1))
        db.add(m)
        db.flush()
        db.add(MemberSalary(member_id=m.id, effective_from=date(2024, 1, 1), basic_salary=D(salary), pensionable_salary=D(salary)))
        people.append(m)
    for code, ftype, payer, rate in (("ADM", FeeType.administration, FeePayer.member, "1"), ("GLA", FeeType.risk_premium, FeePayer.employer, "2"),
                                     ("AUM", FeeType.investment_management, FeePayer.fund, "0.5")):
        db.add(FeeRule(fund_id=fund.id, code=code, name=f"{code} fee", fee_type=ftype, basis=FeeBasis.pct_contributions, rate=D(rate),
                       payer=payer, frequency=FeeFrequency.per_contribution, effective_from=date(2020, 1, 1)))
    bank = db.execute(select(Bank).limit(1)).scalar_one()
    account = FundBankAccount(fund_id=fund.id, bank_id=bank.id, account_name="Collections", account_number="1")
    db.add(account)
    db.flush()
    db.refresh(scheme)
    return fund, scheme, people, account


def confirmed_receipt(db, officer, checker, fund, scheme, account, amount):
    values = receipts.ConfirmValues(amount=D(amount), value_date=TODAY, bank_account_id=account.id, bank_reference=None,
                                    scheme_id=scheme.id, contribution_month=None, notes=None)
    receipt, request = receipts.capture(db, officer, fund, payment_method=PaymentMethod.eft, payment_date=TODAY, payer_name=None,
                                        payer_reference=None, values=values)
    approvals.approve(db, request.id, checker)
    db.refresh(receipt)
    return receipt


def ready_schedule(db, officer, fund, scheme, supplementary=False):
    s = schedules.create(db, officer, fund, scheme.id, MONTH, supplementary=supplementary, source=ScheduleSource.manual, prefill=True)
    return schedules.submit(db, officer, s)


def test_plan_applies_fees_by_payer(db, officer, world):
    fund, scheme, people, account = world
    s = ready_schedule(db, officer, fund, scheme)
    plan = allocations.plan_for(db, s)
    assert s.total == D("45000.00")  # (10,000 + 20,000) + (5,000 + 10,000)
    assert plan.member_fees == D("450.00")  # 1% of each member's contributions
    assert plan.employer_fees == D("900.00")  # 2% of the schedule, on top
    assert plan.needed == D("45900.00") and plan.net_to_members == D("44550.00")
    assert {f.code for f in plan.fees} == {"ADM", "GLA"}  # the fund-paid rule isn't charged at allocation


def test_allocation_posts_known_answers(client, db, officer, checker, world):
    fund, scheme, people, account = world
    r1 = confirmed_receipt(db, officer, checker, fund, scheme, account, "30000")
    r2 = confirmed_receipt(db, officer, checker, fund, scheme, account, "20000")
    s = ready_schedule(db, officer, fund, scheme)
    preview = client.get(f"/api/v1/schedules/{s.id}/allocation", headers=auth_headers(officer)).json()
    assert preview["blocker"] is None and preview["needed"] == "45900.00"
    assert [c["suggested"] for c in preview["candidates"]] == ["30000.00", "15900.00"]
    r = client.post(f"/api/v1/schedules/{s.id}/allocate", headers=auth_headers(officer), json={})
    assert r.status_code == 202, r.text
    assert client.post(f"/api/v1/approvals/{r.json()['id']}/approve", headers=auth_headers(officer), json={}).status_code in (400, 403)
    ok = client.post(f"/api/v1/approvals/{r.json()['id']}/approve", headers=auth_headers(checker), json={})
    assert ok.status_code == 200, ok.text
    db.refresh(s), db.refresh(r1), db.refresh(r2)
    assert s.status == ScheduleStatus.allocated
    assert (r1.unallocated, r2.unallocated) == (D("0.00"), D("4100.00"))
    assert ledger.gl_balance(db, fund.id, "2000") == D("44550.00")
    assert ledger.gl_balance(db, fund.id, "2500") == D("450.00")
    assert ledger.gl_balance(db, fund.id, "2400") == D("900.00")
    assert ledger.gl_balance(db, fund.id, "2100") == D("4100.00")
    assert ledger.member_balance(db, people[0].id) == D("29700.00")  # 9,900 + 19,800
    assert ledger.member_balances_by_component(db, people[1].id)[Component.employer] == {1: D("9900.00")}
    t = ledger.tie_out(db, fund.id)
    assert t.balanced and t.ties


def test_short_money_is_held(client, db, officer, checker, world):
    fund, scheme, people, account = world
    confirmed_receipt(db, officer, checker, fund, scheme, account, "45000")
    s = ready_schedule(db, officer, fund, scheme)
    preview = client.get(f"/api/v1/schedules/{s.id}/allocation", headers=auth_headers(officer)).json()
    assert preview["blocker"].startswith("Hold:")
    r = client.post(f"/api/v1/schedules/{s.id}/allocate", headers=auth_headers(officer), json={})
    assert r.status_code == 409 and "900.00 short" in r.json()["detail"]


def test_picks_must_cover_exactly(client, db, officer, checker, world):
    fund, scheme, people, account = world
    big = confirmed_receipt(db, officer, checker, fund, scheme, account, "50000")
    s = ready_schedule(db, officer, fund, scheme)
    too_much = client.post(f"/api/v1/schedules/{s.id}/allocate", headers=auth_headers(officer),
                           json={"receipts": [{"receipt_id": str(big.id), "amount": "46000"}]})
    assert too_much.status_code == 409 and "too much" in too_much.json()["detail"]
    over_available = client.post(f"/api/v1/schedules/{s.id}/allocate", headers=auth_headers(officer),
                                 json={"receipts": [{"receipt_id": str(big.id), "amount": "50000.01"}]})
    assert over_available.status_code == 400
    exact = client.post(f"/api/v1/schedules/{s.id}/allocate", headers=auth_headers(officer),
                        json={"receipts": [{"receipt_id": str(big.id), "amount": "45900"}]})
    assert exact.status_code == 202


def test_pending_allocation_holds_money_and_schedule(client, db, officer, checker, world):
    fund, scheme, people, account = world
    confirmed_receipt(db, officer, checker, fund, scheme, account, "50000")
    s = ready_schedule(db, officer, fund, scheme)
    assert client.post(f"/api/v1/schedules/{s.id}/allocate", headers=auth_headers(officer), json={}).status_code == 202
    assert client.post(f"/api/v1/schedules/{s.id}/allocate", headers=auth_headers(officer), json={}).status_code == 409
    assert client.post(f"/api/v1/schedules/{s.id}/reopen", headers=auth_headers(officer)).status_code == 409
    supp = ready_schedule(db, officer, fund, scheme, supplementary=True)
    # Only 4,100 of the receipt is free while the first allocation waits.
    preview = client.get(f"/api/v1/schedules/{supp.id}/allocation", headers=auth_headers(officer)).json()
    assert preview["available_total"] == "4100.00" and preview["blocker"].startswith("Hold:")


def test_rejection_releases_the_money(client, db, officer, checker, world):
    fund, scheme, people, account = world
    receipt = confirmed_receipt(db, officer, checker, fund, scheme, account, "45900")
    s = ready_schedule(db, officer, fund, scheme)
    req = client.post(f"/api/v1/schedules/{s.id}/allocate", headers=auth_headers(officer), json={}).json()
    assert allocations.available(db, receipt) == D("0.00")
    assert client.post(f"/api/v1/approvals/{req['id']}/reject", headers=auth_headers(checker), json={"comment": "Wrong month"}).status_code == 200
    assert allocations.available(db, receipt) == D("45900.00")
    allocation = db.get(ContributionAllocation, uuid.UUID(req["entity_id"]))
    assert allocation.status == AllocationStatus.rejected
    assert client.post(f"/api/v1/schedules/{s.id}/allocate", headers=auth_headers(officer), json={}).status_code == 202


def test_member_status_change_blocks_approval(client, db, officer, checker, world):
    fund, scheme, people, account = world
    confirmed_receipt(db, officer, checker, fund, scheme, account, "45900")
    s = ready_schedule(db, officer, fund, scheme)
    req = client.post(f"/api/v1/schedules/{s.id}/allocate", headers=auth_headers(officer), json={}).json()
    people[1].status = MemberStatus.exited
    db.flush()
    r = client.post(f"/api/v1/approvals/{req['id']}/approve", headers=auth_headers(checker), json={})
    assert r.status_code == 409
    assert ledger.gl_balance(db, fund.id, "2000") == D("0")


def test_db_fund_and_access(client, db, officer, checker, world):
    fund, scheme, people, account = world
    s = ready_schedule(db, officer, fund, scheme)
    member_admin = make_user(db, UserRole.member_admin)
    from app.services import fund_access
    fund_access.grant(db, member_admin.id, fund.id, None)
    db.flush()
    assert client.post(f"/api/v1/schedules/{s.id}/allocate", headers=auth_headers(member_admin), json={}).status_code == 403
    outsider = make_user(db, UserRole.contributions_officer)
    assert client.get(f"/api/v1/schedules/{s.id}/allocation", headers=auth_headers(outsider)).status_code == 404
    fund.fund_type = "defined_benefit"
    db.flush()
    with pytest.raises(HTTPException) as exc:
        allocations.propose(db, officer, s, None)
    assert exc.value.status_code == 409
