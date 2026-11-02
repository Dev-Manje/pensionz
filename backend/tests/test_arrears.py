"""Expected contributions, arrears, ageing and late-payment interest
(FR-CON-002, FR-CON-008, FR-MEM-012) — known answers as at 2 Nov 2026."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.category import BenefitCategory, BenefitCategoryTerms, BenefitDesign
from app.models.contribution import ContributionSchedule, ContributionScheduleLine, ScheduleSource, ScheduleStatus
from app.models.identity import UserRole
from app.models.member import Member, MemberSalary, MemberStatus
from app.models.regulatory import RegulatoryParameterVersion
from app.models.scheme import Scheme
from app.services import arrears
from tests.factories import auth_headers, make_fund, make_user

D = Decimal
AS_AT = date(2026, 11, 2)


@pytest.fixture
def staff(db):
    return make_user(db, UserRole.contributions_officer)


@pytest.fixture
def world(db, staff):
    fund = make_fund(db, staff, fund_type="umbrella_dc")
    scheme = Scheme(fund_id=fund.id, code="EMP01", name="Employer Ltd", contribution_day=14, join_date=date(2026, 7, 1))
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
                   gender="male", date_of_birth=date(1990, 1, 1), date_joined_fund=date(2026, 7, 1))
        db.add(m)
        db.flush()
        db.add(MemberSalary(member_id=m.id, effective_from=date(2026, 7, 1), basic_salary=D(salary), pensionable_salary=D(salary)))
        people.append(m)
    db.flush()
    return fund, scheme, people


def paid(db, fund, scheme, month, amounts):
    s = ContributionSchedule(fund_id=fund.id, scheme_id=scheme.id, contribution_month=month, reference=f"T{month:%m}",
                             status=ScheduleStatus.allocated, source=ScheduleSource.manual)
    s.lines = [ContributionScheduleLine(row_no=i + 2, member_id=m.id, employee=ee, employer=er) for i, (m, ee, er) in enumerate(amounts)]
    db.add(s)
    db.flush()


def test_due_date_and_buckets(world):
    fund, scheme, _ = world
    assert arrears.due_date(scheme, date(2026, 1, 1)) == date(2026, 2, 14)
    scheme.contribution_day = 31
    assert arrears.due_date(scheme, date(2026, 1, 1)) == date(2026, 2, 28)
    assert [arrears.bucket(d) for d in (0, 1, 30, 31, 150, 151)] == ["Not yet due", "1–30 days", "1–30 days", "31–60 days", "121–150 days", "Over 150 days"]


def test_scheme_arrears_known_answers(db, world):
    fund, scheme, people = world
    db.add(RegulatoryParameterVersion(key="late_payment_interest_pct", value=D("12"), effective_from=date(2000, 1, 1)))
    paid(db, fund, scheme, date(2026, 8, 1), [(people[0], D("10000"), D("20000")), (people[1], D("5000"), D("10000"))])
    paid(db, fund, scheme, date(2026, 9, 1), [(people[0], D("10000"), D("20000"))])
    result = arrears.scheme_arrears(db, scheme, AS_AT)
    by = {m.month: m for m in result.months}
    jul, aug, sep, octo = (by[date(2026, k, 1)] for k in (7, 8, 9, 10))
    assert (jul.expected, jul.paid, jul.arrears, jul.status, jul.days_overdue, jul.bucket) == (D("45000.00"), D("0.00"), D("45000.00"), "unpaid", 80, "61–90 days")
    assert jul.interest == D("1183.56")  # 45,000 × 12% × 80 / 365
    assert (aug.arrears, aug.status) == (D("0.00"), "paid")
    assert (sep.arrears, sep.status, sep.bucket) == (D("15000.00"), "part_paid", "1–30 days")
    assert (octo.status, octo.days_overdue) == ("not_due", 0)
    assert result.total_arrears == D("60000.00")  # July + the rest of September; October isn't due yet
    ageing = {b["label"]: b["amount"] for b in arrears.ageing([result])}
    assert ageing["61–90 days"] == D("45000.00") and ageing["1–30 days"] == D("15000.00")


def test_no_interest_without_a_rate(db, world):
    fund, scheme, people = world
    result = arrears.scheme_arrears(db, scheme, AS_AT)
    assert all(m.interest is None for m in result.months) and result.total_interest is None


def test_members_out_of_service_are_not_expected(db, world):
    fund, scheme, people = world
    people[1].status, people[1].exit_date = MemberStatus.exited, date(2026, 8, 31)
    result = arrears.scheme_arrears(db, scheme, AS_AT)
    by = {m.month: m for m in result.months}
    assert by[date(2026, 8, 1)].expected == D("45000.00")
    assert by[date(2026, 9, 1)].expected == D("30000.00") and by[date(2026, 9, 1)].members_expected == 1


def test_member_arrears(db, world):
    fund, scheme, people = world
    paid(db, fund, scheme, date(2026, 8, 1), [(people[0], D("10000"), D("20000"))])
    months = {m.month: m for m in arrears.member_arrears(db, people[0], AS_AT)}
    assert months[date(2026, 8, 1)].arrears == D("0.00")
    assert (months[date(2026, 7, 1)].arrears, months[date(2026, 7, 1)].bucket) == (D("30000.00"), "61–90 days")


def test_arrears_api_and_access(client, db, staff, world):
    fund, scheme, people = world
    h = auth_headers(staff)
    r = client.get(f"/api/v1/funds/{fund.id}/arrears?as_at=2026-11-02", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_arrears"] == "135000.00" and body["interest_rate_set"] is False  # Jul–Sep unpaid
    assert body["employers"][0]["months_in_arrears"] == 3 and body["employers"][0]["months"][0]["month"] == "2026-11-01"
    exp = client.get(f"/api/v1/funds/{fund.id}/expected-contributions?scheme_id={scheme.id}&month=2026-10-15", headers=h).json()
    assert (exp["total"], exp["due_date"], len(exp["lines"])) == ("45000.00", "2026-11-14", 2)
    m = client.get(f"/api/v1/members/{people[0].id}/arrears?as_at=2026-11-02", headers=h).json()
    assert m["total_arrears"] == "90000.00"
    outsider = make_user(db, UserRole.contributions_officer)
    assert client.get(f"/api/v1/funds/{fund.id}/arrears", headers=auth_headers(outsider)).status_code == 404
    assert client.get(f"/api/v1/funds/{fund.id}/arrears", headers=auth_headers(make_user(db, UserRole.principal_officer))).status_code == 403
