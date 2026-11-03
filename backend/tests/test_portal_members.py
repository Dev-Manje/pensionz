"""Members from the principal officer portal: HR-level list, new members (one by one
and the bulk upload), salary changes and exit notices — each a request a member
checker approves, shown back to the officers under Requests."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.member import Member, MemberSalary, MemberStatus
from app.models.notification import UserNotification
from app.models.scheme import SchemeOfficer
from app.models.identity import UserRole
from tests.factories import auth_headers, make_user
from tests.test_member_import import GOOD, _filled
from tests.test_members import approve, body, checker, create, maker, setup  # noqa: F401 — fixtures

PO = "/api/v1/po"


@pytest.fixture
def officer(db, setup):
    user = make_user(db, UserRole.principal_officer)
    db.add(SchemeOfficer(scheme_id=setup[1].id, user_id=user.id))
    db.flush()
    return user


@pytest.fixture
def member(client, db, maker, checker, setup):
    fund, scheme, category = setup
    m = create(client, db, maker, checker, fund, body(scheme, category, employee_no="E-100", date_joined_employer="2024-01-01"))
    db.add(MemberSalary(member_id=m.id, effective_from=date(2024, 1, 1), basic_salary=Decimal("300000"), pensionable_salary=Decimal("300000")))
    db.flush()
    return m


def new_member_body(category, **overrides):
    b = {"first_name": "Thoko", "last_name": "Phiri", "gender": "male", "date_of_birth": "1995-03-02", "id_type": "NATID",
         "id_number": "PO-7781", "employee_no": "E-200", "category_id": str(category.id), "date_joined_employer": "2026-10-01",
         "date_joined_fund": "2026-10-01", "mobile": "+265 888 111 222", "basic_salary": "420000"}
    b.update(overrides)
    return b


def test_member_list_shows_hr_facts_only(client, db, setup, officer, member):
    response = client.get(f"{PO}/schemes/{setup[1].id}/members", headers=auth_headers(officer))
    assert response.status_code == 200, response.text
    [row] = response.json()
    assert row["account_code"] == member.account_code and row["employee_no"] == "E-100" and row["category"] == "Staff"
    assert Decimal(row["salary"]) == Decimal("300000.00") and row["status"] == "active"
    for private in ("id_number", "bank_account_number", "balance", "beneficiaries", "email", "mobile"):
        assert private not in row
    detail = client.get(f"{PO}/members/{member.id}", headers=auth_headers(officer)).json()
    assert detail["can_change_salary"] and detail["can_give_notice"] and "id_number" not in detail
    assert client.get(f"{PO}/schemes/{setup[1].id}/members", headers=auth_headers(officer), params={"q": "E-100"}).json()[0]["id"] == str(member.id)


def test_new_member_application_with_first_salary(client, db, setup, officer, checker):
    fund, scheme, category = setup
    response = client.post(f"{PO}/schemes/{scheme.id}/members", headers=auth_headers(officer), json=new_member_body(category))
    assert response.status_code == 202, response.text
    req = response.json()
    assert req["kind_label"] == "New member" and req["status"] == "pending"
    assert approve(client, checker, req["id"]).status_code == 200

    m = db.query(Member).filter_by(fund_id=fund.id, id_number="PO-7781").one()
    assert m.scheme_id == scheme.id and m.employee_no == "E-200"
    salary = db.query(MemberSalary).filter_by(member_id=m.id).one()
    assert salary.pensionable_salary == Decimal("420000.00") and salary.effective_from == date(2026, 10, 1)
    # The officer is told, with a link into the portal.
    note = db.query(UserNotification).filter_by(user_id=officer.id, event="approval.approved").one()
    assert note.link == f"/po/requests/{req['id']}"
    listed = client.get(f"{PO}/schemes/{scheme.id}/requests", headers=auth_headers(officer)).json()
    assert [(r["id"], r["status"]) for r in listed] == [(req["id"], "approved")]
    assert client.get(f"{PO}/requests/{req['id']}", headers=auth_headers(officer)).json()["status"] == "approved"


def test_new_member_checks_still_apply(client, db, setup, officer):
    _, scheme, category = setup
    too_old = client.post(f"{PO}/schemes/{scheme.id}/members", headers=auth_headers(officer),
                          json=new_member_body(category, date_of_birth="1960-01-01"))
    assert too_old.status_code == 400  # category entry age 18–55
    no_salary = client.post(f"{PO}/schemes/{scheme.id}/members", headers=auth_headers(officer),
                            json=new_member_body(category, basic_salary="0"))
    assert no_salary.status_code == 422


def test_salary_change_and_exit_notice(client, db, setup, officer, checker, member):
    raise_ = client.post(f"{PO}/members/{member.id}/salary", headers=auth_headers(officer),
                         json={"effective_from": "2026-10-01", "basic_salary": "330000"})
    assert raise_.status_code == 202, raise_.text
    assert client.get(f"{PO}/schemes/{setup[1].id}/members", headers=auth_headers(officer)).json()[0]["has_pending_request"]
    assert approve(client, checker, raise_.json()["id"]).status_code == 200
    assert db.query(MemberSalary).filter_by(member_id=member.id, effective_from=date(2026, 10, 1)).one().pensionable_salary == Decimal("330000.00")

    assert client.post(f"{PO}/members/{member.id}/exit", headers=auth_headers(officer),
                       json={"last_day": "2026-10-31", "reason": "other"}).status_code == 400  # "other" needs a note
    notice = client.post(f"{PO}/members/{member.id}/exit", headers=auth_headers(officer),
                         json={"last_day": "2026-10-31", "reason": "resigned"})
    assert notice.status_code == 202, notice.text
    assert notice.json()["kind_label"] == "Exit notice" and "Active → Inactive" in notice.json()["summary"]
    # Only one change waits on a member at a time.
    assert client.post(f"{PO}/members/{member.id}/exit", headers=auth_headers(officer),
                       json={"last_day": "2026-10-31", "reason": "resigned"}).status_code == 409
    assert approve(client, checker, notice.json()["id"]).status_code == 200
    db.refresh(member)
    assert member.status == MemberStatus.inactive and member.status_effective == date(2026, 10, 31)
    detail = client.get(f"{PO}/members/{member.id}", headers=auth_headers(officer)).json()
    assert {r["kind_label"] for r in detail["requests"]} == {"Salary change", "Exit notice"}
    assert detail["status"] == "inactive"


def test_death_notice_marks_the_member_deceased(client, db, setup, officer, checker, member):
    notice = client.post(f"{PO}/members/{member.id}/exit", headers=auth_headers(officer), json={"last_day": "2026-10-20", "reason": "died"})
    assert notice.status_code == 202, notice.text
    assert approve(client, checker, notice.json()["id"]).status_code == 200
    db.refresh(member)
    assert member.status == MemberStatus.deceased and member.date_of_death == date(2026, 10, 20)


def test_bulk_upload_from_the_portal(client, db, setup, officer, maker, checker):
    fund, scheme, _ = setup
    template = client.get(f"{PO}/schemes/{scheme.id}/members/import-template", headers=auth_headers(officer))
    assert template.status_code == 200 and template.content[:2] == b"PK"
    content = _filled(client, maker, scheme, [GOOD, {**GOOD, "first_name": "Broken", "gender": None, "id_number": "IMP-011"}])
    batch = client.post(f"{PO}/schemes/{scheme.id}/members/imports", headers=auth_headers(officer),
                        files={"file": ("members.xlsx", content, "application/octet-stream")})
    assert batch.status_code == 201, batch.text
    b = batch.json()
    assert (b["total_rows"], b["valid_rows"], b["can_submit"]) == (2, 1, True)
    assert any(r["errors"] for r in b["rows"])
    assert client.get(f"{PO}/member-imports/{b['id']}/errors", headers=auth_headers(officer)).status_code == 200
    sent = client.post(f"{PO}/member-imports/{b['id']}/submit", headers=auth_headers(officer))
    assert sent.status_code == 202, sent.text
    assert approve(client, checker, sent.json()["id"]).status_code == 200
    assert db.query(Member).filter_by(fund_id=fund.id, first_name="Alinafe").count() == 1
    pdf = client.get(f"{PO}/schemes/{scheme.id}/members/application-form", headers=auth_headers(officer))
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_other_employers_and_staff_are_kept_out(client, db, setup, officer, member, maker):
    stranger = make_user(db, UserRole.principal_officer)
    assert client.get(f"{PO}/schemes/{setup[1].id}/members", headers=auth_headers(stranger)).status_code == 404
    assert client.get(f"{PO}/members/{member.id}", headers=auth_headers(stranger)).status_code == 404
    assert client.post(f"{PO}/members/{member.id}/salary", headers=auth_headers(stranger),
                       json={"effective_from": "2026-10-01", "basic_salary": "1"}).status_code == 404
    assert client.get(f"{PO}/schemes/{setup[1].id}/members", headers=auth_headers(maker)).status_code == 403
    req = client.post(f"{PO}/members/{member.id}/salary", headers=auth_headers(officer),
                      json={"effective_from": "2026-10-01", "basic_salary": "310000"}).json()
    assert client.get(f"{PO}/requests/{req['id']}", headers=auth_headers(stranger)).status_code == 404
