"""Contribution schedules (FR-CON-001, FR-CON-003): prefilled template, upload
and manual capture, line checks (member, status, statutory minimum, category
rate, AVC), submit / reopen / cancel, one main schedule per employer-month, access."""
import io
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.models.category import BenefitCategory, BenefitCategoryTerms, BenefitDesign
from app.models.contribution import ScheduleStatus
from app.models.identity import UserRole
from app.models.member import Member, MemberSalary, MemberStatus
from app.models.regulatory import RegulatoryParameterVersion
from app.models.scheme import Scheme
from app.services.io import contribution_schedule as io_schedule
from tests.factories import auth_headers, make_fund, make_user

D = Decimal
MONTH = date(2026, 10, 1)


@pytest.fixture
def officer(db):
    return make_user(db, UserRole.contributions_officer)


@pytest.fixture
def setup(db, officer):
    fund = make_fund(db, officer, fund_type="umbrella_dc")
    for key, value in (("min_employee_contribution_pct", "5"), ("min_employer_contribution_pct", "10")):
        db.add(RegulatoryParameterVersion(key=key, value=D(value), effective_from=date(2000, 1, 1)))
    scheme = Scheme(fund_id=fund.id, code="EMP01", name="Employer Ltd", contribution_day=14)
    other = Scheme(fund_id=fund.id, code="EMP02", name="Other Ltd", contribution_day=14)
    db.add_all([scheme, other])
    db.flush()
    cat = BenefitCategory(scheme_id=scheme.id, fund_id=fund.id, code="STF", name="Staff")
    db.add(cat)
    db.flush()
    db.add(BenefitCategoryTerms(category_id=cat.id, effective_from=date(2020, 1, 1), design=BenefitDesign.dc, employee_rate=D("5"),
                                employer_rate=D("10"), normal_retirement_age=60, avc_allowed=False))
    db.flush()
    people = []
    for i, salary in enumerate(("200000", "350000", None), start=1):
        m = Member(fund_id=fund.id, scheme_id=scheme.id, category_id=cat.id, account_code=f"EMP01{i:04d}", employee_no=f"E{i}",
                   first_name=f"Person{i}", last_name="Test", gender="female", date_of_birth=date(1990, 1, 1), date_joined_fund=date(2024, 1, 1))
        db.add(m)
        db.flush()
        if salary:
            db.add(MemberSalary(member_id=m.id, effective_from=date(2024, 1, 1), basic_salary=D(salary), pensionable_salary=D(salary)))
        people.append(m)
    db.flush()
    return fund, scheme, other, people


def url(fund, suffix=""):
    return f"/api/v1/funds/{fund.id}/schedules{suffix}"


def create(client, officer, fund, scheme, **kw):
    body = {"scheme_id": str(scheme.id), "contribution_month": MONTH.isoformat(), **kw}
    return client.post(url(fund), headers=auth_headers(officer), json=body)


def test_template_is_prefilled_with_expected_amounts(client, officer, setup):
    fund, scheme, _, people = setup
    r = client.get(url(fund, f"/template?scheme_id={scheme.id}&month={MONTH}"), headers=auth_headers(officer))
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content))["Schedule"]
    rows = [[c.value for c in row] for row in ws.iter_rows(min_row=2)]
    assert rows[0][:6] == ["EMP010001", "E1", "Person1 Test", 200000, 10000, 20000]
    assert rows[2][0] == "EMP010003" and rows[2][4] is None  # no salary on record → no expected amount


def test_prefilled_draft_checks_lines(client, officer, setup):
    fund, scheme, _, people = setup
    r = create(client, officer, fund, scheme)
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["reference"] == "EMP01-202610" and s["status"] == "draft" and s["line_count"] == 3
    assert s["total"] == "82500.00"  # (10,000 + 20,000) + (17,500 + 35,000)
    third = s["lines"][2]
    assert third["errors"] == ["The line has no contributions"]
    assert "No salary given or on record" in third["warnings"][0]
    assert s["error_count"] == 1
    # Errors block submission.
    assert client.post(f"/api/v1/schedules/{s['id']}/submit", headers=auth_headers(officer)).status_code == 400


def test_statutory_minimum_and_category_rate(client, officer, setup):
    fund, scheme, _, people = setup
    s = create(client, officer, fund, scheme, prefill=False).json()
    h = auth_headers(officer)
    # 4% of 200,000 is below the 5% minimum → error; 6% is above but not the category's 5% → warning.
    low = client.post(f"/api/v1/schedules/{s['id']}/lines", headers=h,
                      json={"account_code": "emp010001", "employee": "8000", "employer": "20000"}).json()
    line = low["lines"][0]
    assert any("below the statutory minimum of 5%" in e for e in line["errors"])
    fixed = client.put(f"/api/v1/schedules/{s['id']}/lines/{line['id']}", headers=h,
                       json={"account_code": "EMP010001", "employee": "12000", "employer": "20000"}).json()
    line = fixed["lines"][0]
    assert line["errors"] == [] and line["warnings"] == ["Expected employee contribution MWK 10,000.00 (5% of MWK 200,000.00)"]
    assert line["member_name"] == "Person1 Test"


def test_member_errors(client, db, officer, setup):
    fund, scheme, other, people = setup
    people[1].status = MemberStatus.exited
    stranger = Member(fund_id=fund.id, scheme_id=other.id, account_code="EMP020001", first_name="X", last_name="Y", gender="male",
                      date_of_birth=date(1990, 1, 1), date_joined_fund=date(2024, 1, 1))
    db.add(stranger)
    db.flush()
    s = create(client, officer, fund, scheme, prefill=False).json()
    h = auth_headers(officer)
    for body in ({"account_code": "NOPE", "employee": "1"}, {"account_code": "EMP010002", "employee": "17500", "employer": "35000"},
                 {"account_code": "EMP020001", "employee": "1"}, {"account_code": "EMP010001", "employee": "10000", "employer": "20000", "voluntary": "500"},
                 {"employee_no": "E1", "employee": "10000", "employer": "20000"}):
        s = client.post(f"/api/v1/schedules/{s['id']}/lines", headers=h, json=body).json()
    errors = [l["errors"] for l in s["lines"]]
    assert errors[0] == ["No member of this fund has that account code"]
    assert "exited" in errors[1][0]
    assert errors[2] == ["EMP020001 belongs to another employer"]
    assert errors[3] == ["Voluntary contributions aren't allowed in this member's category"]
    assert errors[4] == ["EMP010001 is already on row 5"]


def test_upload_replaces_lines_and_reports_bad_amounts(client, officer, setup):
    fund, scheme, _, people = setup
    content = "Account code,Employee contribution,Employer contribution\nEMP010001,10000,20000\nEMP010002,abc,35000\n,,\n".encode()
    r = client.post(url(fund, "/upload"), headers=auth_headers(officer),
                    data={"scheme_id": str(scheme.id), "contribution_month": MONTH.isoformat()}, files={"file": ("oct.csv", content, "text/csv")})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["source"] == "upload" and s["line_count"] == 2 and [l["row_no"] for l in s["lines"]] == [2, 3]
    assert s["lines"][1]["errors"][0] == "Employee contribution: “abc” isn't an amount"
    # A file without the template's headings is refused and leaves no draft behind.
    bad = client.post(url(fund, "/upload"), headers=auth_headers(officer),
                      data={"scheme_id": str(scheme.id), "contribution_month": "2026-09-01"}, files={"file": ("x.csv", b"Name,Amount\nA,1\n", "text/csv")})
    assert bad.status_code == 400
    assert client.get(url(fund, "?month=2026-09-01"), headers=auth_headers(officer)).json()["total"] == 0


def test_submit_reopen_cancel_and_one_main_schedule(client, officer, setup):
    fund, scheme, _, people = setup
    s = create(client, officer, fund, scheme, prefill=False).json()
    h = auth_headers(officer)
    s = client.post(f"/api/v1/schedules/{s['id']}/lines", headers=h, json={"account_code": "EMP010001", "employee": "10000", "employer": "20000"}).json()
    assert create(client, officer, fund, scheme).status_code == 409
    supp = create(client, officer, fund, scheme, supplementary=True, prefill=False).json()
    assert supp["reference"] == "EMP01-202610-S1"
    supp = client.post(f"/api/v1/schedules/{supp['id']}/lines", headers=h, json={"account_code": "EMP010001", "employee": "500", "employer": "1000"}).json()
    assert "also on schedule EMP01-202610" in supp["lines"][0]["warnings"][-1]
    ready = client.post(f"/api/v1/schedules/{s['id']}/submit", headers=h).json()
    assert ready["status"] == "ready" and ready["can_edit"] is False
    assert client.post(f"/api/v1/schedules/{s['id']}/lines", headers=h, json={"account_code": "EMP010002", "employee": "1"}).status_code == 409
    assert client.post(f"/api/v1/schedules/{s['id']}/reopen", headers=h).json()["status"] == "draft"
    assert client.post(f"/api/v1/schedules/{s['id']}/cancel", headers=h).json()["status"] == "cancelled"
    assert create(client, officer, fund, scheme).status_code == 201  # the month is free again


def test_future_month_refused(client, officer, setup):
    fund, scheme, _, _ = setup
    r = client.post(url(fund), headers=auth_headers(officer), json={"scheme_id": str(scheme.id), "contribution_month": "2099-01-01"})
    assert r.status_code == 400


def test_schedule_access(client, db, officer, setup):
    fund, scheme, _, _ = setup
    s = create(client, officer, fund, scheme).json()
    outsider = make_user(db, UserRole.contributions_officer)
    assert client.get(f"/api/v1/schedules/{s['id']}", headers=auth_headers(outsider)).status_code == 404
    checker = make_user(db, UserRole.contributions_checker)
    from app.services import fund_access
    fund_access.grant(db, checker.id, fund.id, None)
    db.flush()
    assert client.get(f"/api/v1/schedules/{s['id']}", headers=auth_headers(checker)).status_code == 200
    assert client.post(f"/api/v1/schedules/{s['id']}/submit", headers=auth_headers(checker)).status_code == 403
    portal = make_user(db, UserRole.principal_officer)
    assert client.get(url(fund), headers=auth_headers(portal)).status_code == 403


def test_parse_money():
    assert io_schedule.parse_money("1,250.50") == D("1250.50")
    assert io_schedule.parse_money(" ") is None
    with pytest.raises(ValueError):
        io_schedule.parse_money("12a")
