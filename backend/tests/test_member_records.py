"""Beneficiaries (FR-MEM-008), salary and service history (FR-MEM-009)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.identity import UserRole
from app.models.member import BeneficiaryNomination, MemberSalary, MemberServicePeriod, MemberStatus
from app.services import member_records
from tests.factories import auth_headers, make_user
from tests.test_members import approve, body, checker, create, maker, setup  # noqa: F401 — fixtures


@pytest.fixture
def member(client, db, maker, checker, setup):
    fund, scheme, category = setup
    return create(client, db, maker, checker, fund, body(scheme, category))


def kid_born():
    return (date.today() - timedelta(days=365 * 8)).isoformat()


def nominate(client, user, member, beneficiaries, signed="2025-01-10"):
    return client.post(f"/api/v1/members/{member.id}/beneficiaries", headers=auth_headers(user),
                       json={"signed_date": signed, "beneficiaries": beneficiaries})


SPOUSE = {"full_name": "John Banda", "relationship": "SPOUSE", "date_of_birth": "1988-02-01", "share_pct": "60", "phone": "+265 888 1"}
CHILD = {"full_name": "Kim Banda", "relationship": "CHILD", "share_pct": "40"}
GUARDIAN = {"guardian_name": "John Banda", "guardian_relationship": "PARENT", "guardian_phone": "+265 888 1"}


def test_nomination_shares_must_total_100(client, maker, member):
    response = nominate(client, maker, member, [SPOUSE, {**CHILD, "share_pct": "30"}])
    assert response.status_code == 400 and "add up to 100%" in response.json()["detail"]


def test_minor_needs_guardian(client, maker, member):
    response = nominate(client, maker, member, [SPOUSE, {**CHILD, "date_of_birth": kid_born()}])
    assert response.status_code == 400 and "under 18" in response.json()["detail"]
    assert nominate(client, maker, member, [SPOUSE, {**CHILD, "date_of_birth": kid_born(), **GUARDIAN}]).status_code == 202


def test_new_nomination_replaces_current_and_keeps_history(client, db, maker, checker, member):
    first = nominate(client, maker, member, [SPOUSE, {**CHILD, "date_of_birth": kid_born(), **GUARDIAN}])
    assert approve(client, checker, first.json()["id"]).status_code == 200
    second = nominate(client, maker, member, [{**SPOUSE, "share_pct": "100"}], signed="2025-06-01")
    assert second.json()["previous"]["beneficiaries"][0].startswith("John Banda (Spouse) — 60.00%")
    assert approve(client, checker, second.json()["id"]).status_code == 200
    rows = db.query(BeneficiaryNomination).filter_by(member_id=member.id).order_by(BeneficiaryNomination.version).all()
    assert [(n.version, n.is_current) for n in rows] == [(1, False), (2, True)]
    data = client.get(f"/api/v1/members/{member.id}/beneficiaries", headers=auth_headers(maker)).json()
    assert data["current"]["version"] == 2 and data["history"][0]["beneficiaries"][1]["is_minor"] is True


def test_beneficiary_contacts_hidden_from_roles_without_need(client, db, maker, checker, setup, member):
    approve(client, checker, nominate(client, maker, member, [{**SPOUSE, "share_pct": "100", "id_number": "ZX998877"}]).json()["id"])
    finance = make_user(db, UserRole.finance)
    from app.services import fund_access
    fund_access.grant(db, finance.id, setup[0].id, None)
    b = client.get(f"/api/v1/members/{member.id}/beneficiaries", headers=auth_headers(finance)).json()["current"]["beneficiaries"][0]
    assert b["phone"] is None and b["id_number"] == "•••• 8877" and b["share_pct"] == "100.00"


def test_deceased_member_cannot_nominate(client, db, maker, member):
    member.status = MemberStatus.deceased
    db.flush()
    assert nominate(client, maker, member, [{**SPOUSE, "share_pct": "100"}]).status_code == 400


def test_salary_versions_and_correction(client, db, maker, checker, member):
    url, h = f"/api/v1/members/{member.id}/salaries", auth_headers(maker)
    assert client.post(url, headers=h, json={"effective_from": "2023-01-01", "basic_salary": "500000"}).status_code == 400  # before joining
    r = client.post(url, headers=h, json={"effective_from": "2024-01-01", "basic_salary": "500000"})
    assert r.status_code == 202 and r.json()["payload"]["pensionable_salary"] == "MWK 500,000.00"
    approve(client, checker, r.json()["id"])
    r = client.post(url, headers=h, json={"effective_from": "2025-04-01", "basic_salary": "650000", "pensionable_salary": "600000"})
    approve(client, checker, r.json()["id"])
    assert member_records.salary_on(db, member.id, date(2025, 3, 31)).pensionable_salary == Decimal("500000.00")
    assert member_records.salary_on(db, member.id, date(2025, 4, 1)).pensionable_salary == Decimal("600000.00")
    # Same date again corrects that version.
    r = client.post(url, headers=h, json={"effective_from": "2025-04-01", "basic_salary": "650000", "pensionable_salary": "610000"})
    assert r.json()["payload"]["action"] == "correct"
    approve(client, checker, r.json()["id"])
    assert db.query(MemberSalary).filter_by(member_id=member.id).count() == 2
    assert client.get(f"/api/v1/members/{member.id}/employment", headers=h).json()["current_salary"]["pensionable_salary"] == "610000.00"


def test_salary_refused_for_exited_member(client, db, maker, member):
    member.status = MemberStatus.exited
    db.flush()
    r = client.post(f"/api/v1/members/{member.id}/salaries", headers=auth_headers(maker), json={"effective_from": "2025-01-01", "basic_salary": "1"})
    assert r.status_code == 400


@pytest.mark.parametrize("start, end, factor, years", [
    (date(2000, 1, 1), date(2024, 12, 31), "1", "25.0000"),
    (date(2020, 1, 1), date(2021, 12, 31), "0.5", "1.0000"),
    (date(2024, 1, 15), date(2024, 2, 14), "1", "0.0833"),
    (date(2024, 3, 1), date(2024, 3, 15), "1", "0.0411"),
])
def test_service_years_known_answers(start, end, factor, years):
    assert member_records.period_years(start, end, Decimal(factor)) == Decimal(years)


def test_service_history_rules_and_total(client, db, maker, checker, member):
    url, h = f"/api/v1/members/{member.id}/service", auth_headers(maker)
    overlap = [{"start_date": "2010-01-01", "end_date": "2015-06-30"}, {"start_date": "2015-01-01"}]
    assert client.put(url, headers=h, json={"periods": overlap, "reason": "From HR file"}).status_code == 400
    two_open = [{"start_date": "2010-01-01"}, {"start_date": "2016-01-01"}]
    assert client.put(url, headers=h, json={"periods": two_open, "reason": "From HR file"}).status_code == 400
    periods = [{"start_date": "2010-01-01", "end_date": "2014-12-31"},
               {"start_date": "2016-01-01", "end_date": "2017-12-31", "part_time_factor": "0.5", "note": "Part-time"}]
    r = client.put(url, headers=h, json={"periods": periods, "reason": "From HR file"})
    assert r.status_code == 202 and r.json()["payload"]["periods"][1].endswith("at 50% part-time (Part-time)")
    approve(client, checker, r.json()["id"])
    assert db.query(MemberServicePeriod).filter_by(member_id=member.id).count() == 2
    assert client.get(f"/api/v1/members/{member.id}/employment", headers=h).json()["pensionable_service_years"] == "6.0000"
    assert client.put(url, headers=h, json={"periods": periods, "reason": "Again"}).status_code == 400  # nothing changed


def test_records_hidden_outside_fund_and_wrong_role(client, db, maker, member):
    outsider = make_user(db, UserRole.member_admin)
    assert client.get(f"/api/v1/members/{member.id}/beneficiaries", headers=auth_headers(outsider)).status_code == 404
    viewer = make_user(db, UserRole.contributions_officer)
    r = client.post(f"/api/v1/members/{member.id}/salaries", headers=auth_headers(viewer), json={"effective_from": "2025-01-01", "basic_salary": "1"})
    assert r.status_code == 403
