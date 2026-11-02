"""Members (FR-MEM-001…005, 011, FR-ONB-105): maker-checker record, eligibility,
duplicates, status lifecycle, KYC link and the benefit-payment block."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.approval import ApprovalRequest
from app.models.category import BenefitCategory, BenefitCategoryTerms, BenefitDesign
from app.models.identity import UserRole
from app.models.kyc import ClientType, Party, RiskRating
from app.models.member import Member, MemberAssignment, MemberStatus, MemberStatusChange
from app.models.scheme import Scheme
from app.services import members as member_service
from tests.factories import auth_headers, make_fund, make_user


@pytest.fixture
def maker(db):
    return make_user(db, UserRole.member_admin)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.member_checker)


def _category(db, scheme, code="STF", **terms):
    category = BenefitCategory(scheme_id=scheme.id, fund_id=scheme.fund_id, code=code, name="Staff")
    db.add(category)
    db.flush()
    values = {"effective_from": date(2020, 1, 1), "design": BenefitDesign.dc, "employee_rate": Decimal("5"), "employer_rate": Decimal("10"),
              "normal_retirement_age": 60, "min_entry_age": 18, "max_entry_age": 55}
    values.update(terms)
    db.add(BenefitCategoryTerms(category_id=category.id, **values))
    db.flush()
    return category


@pytest.fixture
def setup(db, maker, checker):
    fund = make_fund(db, maker, checker, fund_type="umbrella_dc")
    scheme = Scheme(fund_id=fund.id, code="EMP01", name="Employer Ltd", contribution_day=14)
    db.add(scheme)
    db.flush()
    return fund, scheme, _category(db, scheme)


def body(scheme=None, category=None, **overrides):
    b = {"first_name": "Chikondi", "last_name": "Banda", "gender": "female", "date_of_birth": "1990-05-01",
         "id_type": "NATID", "id_number": "AB12-3456", "date_joined_fund": "2024-01-01", "mobile": "+265 999 000 111",
         "scheme_id": str(scheme.id) if scheme else None, "category_id": str(category.id) if category else None}
    b.update(overrides)
    return b


def propose(client, user, fund, b):
    return client.post(f"/api/v1/funds/{fund.id}/members", headers=auth_headers(user), json=b)


def approve(client, user, request_id):
    return client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(user), json={})


def create(client, db, maker, checker, fund, b) -> Member:
    response = propose(client, maker, fund, b)
    assert response.status_code == 202, response.text
    assert approve(client, checker, response.json()["id"]).status_code == 200
    request = db.get(ApprovalRequest, uuid.UUID(response.json()["id"]))
    db.refresh(request)
    return db.get(Member, uuid.UUID(request.entity_id))


def test_member_created_on_approval_with_generated_code_and_history(client, db, maker, checker, setup):
    fund, scheme, category = setup
    response = propose(client, maker, fund, body(scheme, category))
    assert response.status_code == 202, response.text
    payload = response.json()["payload"]
    assert payload["employer"] == "EMP01 — Employer Ltd"
    assert payload["account_code"] == "Generated on approval"
    assert db.query(Member).filter_by(fund_id=fund.id).count() == 0
    assert approve(client, checker, response.json()["id"]).status_code == 200

    member = db.query(Member).filter_by(fund_id=fund.id).one()
    assert member.account_code.startswith(fund.code) and len(member.account_code) == len(fund.code) + 6
    assert member.status == MemberStatus.active
    assert member.id_number_key == "AB123456"
    assert db.query(MemberAssignment).filter_by(member_id=member.id).one().scheme_id == scheme.id
    assert db.query(MemberStatusChange).filter_by(member_id=member.id).one().to_status == MemberStatus.active


def test_maker_cannot_approve_own_member(client, db, setup):
    fund, scheme, category = setup
    both = make_user(db, UserRole.member_admin, UserRole.member_checker)
    from app.services import fund_access
    fund_access.grant(db, both.id, fund.id, None)
    request = propose(client, both, fund, body(scheme, category)).json()
    assert approve(client, both, request["id"]).status_code == 400


def test_wrong_role_and_other_fund_are_refused(client, db, maker, setup):
    fund, scheme, category = setup
    viewer = make_user(db, UserRole.contributions_officer)
    assert propose(client, viewer, fund, body(scheme, category)).status_code == 403
    outsider = make_user(db, UserRole.member_admin)
    assert propose(client, outsider, fund, body(scheme, category)).status_code == 404


def test_member_record_hidden_outside_fund_and_sensitive_fields_masked(client, db, maker, checker, setup):
    fund, scheme, category = setup
    member = create(client, db, maker, checker, fund, body(scheme, category, bank_account_number=None))
    outsider = make_user(db, UserRole.member_admin)
    assert client.get(f"/api/v1/members/{member.id}", headers=auth_headers(outsider)).status_code == 404

    contributions = make_user(db, UserRole.contributions_officer)
    from app.services import fund_access
    fund_access.grant(db, contributions.id, fund.id, None)
    detail = client.get(f"/api/v1/members/{member.id}", headers=auth_headers(contributions)).json()
    assert detail["fields"]["id_number"] == "•••• 3456"
    assert client.get(f"/api/v1/members/{member.id}", headers=auth_headers(maker)).json()["fields"]["id_number"] == "AB12-3456"
    listing = client.get("/api/v1/members", headers=auth_headers(contributions), params={"q": "chikondi banda"}).json()
    assert listing["total"] == 1 and listing["items"][0]["id_number_masked"] == "•••• 3456"
    assert client.get("/api/v1/members", headers=auth_headers(outsider)).json()["total"] == 0


@pytest.mark.parametrize("overrides, message", [
    ({"date_of_birth": "2010-01-01"}, "accepts members from age 18"),
    ({"date_of_birth": "1960-01-01"}, "up to age 55"),
    ({"date_joined_fund": "2099-01-01"}, "future"),
    ({"id_type": None}, "ID type"),
    ({"scheme_id": None}, "employer and benefit category"),
])
def test_eligibility_and_detail_rules(client, maker, setup, overrides, message):
    fund, scheme, category = setup
    response = propose(client, maker, fund, body(scheme, category, **overrides))
    assert response.status_code == 400 and message in response.json()["detail"]


def test_category_from_another_employer_is_refused(client, db, maker, setup):
    fund, scheme, category = setup
    other = Scheme(fund_id=fund.id, code="EMP02", name="Other Ltd", contribution_day=14)
    db.add(other)
    db.flush()
    response = propose(client, maker, fund, body(other, category))
    assert response.status_code == 400 and "doesn't belong" in response.json()["detail"]


def test_same_id_number_in_same_fund_blocks_and_pending_blocks(client, db, maker, checker, setup):
    fund, scheme, category = setup
    first = propose(client, maker, fund, body(scheme, category))
    assert first.status_code == 202
    # Another request for the same person while the first waits.
    assert propose(client, maker, fund, body(scheme, category, id_number="ab 12 3456")).status_code == 409
    approve(client, checker, first.json()["id"])
    assert propose(client, maker, fund, body(scheme, category, id_number="AB123456")).status_code == 409


def test_duplicates_across_funds_are_flagged_not_blocked(client, db, maker, checker, setup):
    fund, scheme, category = setup
    create(client, db, maker, checker, fund, body(scheme, category))
    other_fund = make_fund(db, maker, checker, fund_type="umbrella_dc")
    other_scheme = Scheme(fund_id=other_fund.id, code="EMP09", name="Elsewhere", contribution_day=10)
    db.add(other_scheme)
    db.flush()
    other_category = _category(db, other_scheme)
    response = propose(client, maker, other_fund, body(other_scheme, other_category, id_number="X999"))
    assert response.status_code == 202
    lines = response.json()["payload"]["possible_duplicates"]
    assert len(lines) == 1 and lines[0].startswith("Same name and date of birth")
    found = client.get("/api/v1/members/duplicates", headers=auth_headers(maker), params={"id_number": "ab12 3456"}).json()
    assert found[0]["match"] == "Same ID number"


def test_data_correction_through_approval_and_nothing_changed(client, db, maker, checker, setup):
    fund, scheme, category = setup
    member = create(client, db, maker, checker, fund, body(scheme, category))
    details = {k: v for k, v in body().items() if k not in ("scheme_id", "category_id")}
    assert client.put(f"/api/v1/members/{member.id}", headers=auth_headers(maker), json=details).status_code == 400
    response = client.put(f"/api/v1/members/{member.id}", headers=auth_headers(maker), json={**details, "last_name": "Phiri", "maiden_name": "Banda"})
    assert response.status_code == 202, response.text
    assert response.json()["previous"]["last_name"] == "Banda"
    assert approve(client, checker, response.json()["id"]).status_code == 200
    db.refresh(member)
    assert member.last_name == "Phiri" and member.maiden_name == "Banda"


def test_status_lifecycle_rules_and_history(client, db, maker, checker, setup):
    fund, scheme, category = setup
    member = create(client, db, maker, checker, fund, body(scheme, category))
    url = f"/api/v1/members/{member.id}/status"
    h = auth_headers(maker)
    assert client.post(url, headers=h, json={"to_status": "active", "effective_date": "2025-01-01", "reason": "n/a"}).status_code == 400
    assert client.post(url, headers=h, json={"to_status": "deferred", "effective_date": "2023-01-01", "reason": "Resigned"}).status_code == 400
    response = client.post(url, headers=h, json={"to_status": "deferred", "effective_date": "2025-06-30", "reason": "Resigned"})
    assert response.status_code == 202, response.text
    assert approve(client, checker, response.json()["id"]).status_code == 200
    db.refresh(member)
    assert member.status == MemberStatus.deferred and member.exit_date == date(2025, 6, 30)
    assert not member_service.allows(member.status, "contributions")
    assert member_service.allows(member.status, "benefit_claims")

    response = client.post(url, headers=h, json={"to_status": "deceased", "effective_date": "2025-08-01", "reason": "Death certificate seen"})
    approve(client, checker, response.json()["id"])
    db.refresh(member)
    assert member.status == MemberStatus.deceased and member.date_of_death == date(2025, 8, 1)
    # Final: nothing further allowed.
    assert client.post(url, headers=h, json={"to_status": "active", "effective_date": "2025-09-01", "reason": "Mistake"}).status_code == 400
    history = client.get(f"/api/v1/members/{member.id}", headers=h).json()["status_history"]
    assert [c["to_status"] for c in history] == ["deceased", "deferred", "active"]


def test_status_request_is_stale_when_status_changed_meanwhile(client, db, maker, checker, setup):
    fund, scheme, category = setup
    member = create(client, db, maker, checker, fund, body(scheme, category))
    request = client.post(f"/api/v1/members/{member.id}/status", headers=auth_headers(maker),
                          json={"to_status": "inactive", "effective_date": "2025-01-01", "reason": "Unpaid leave"}).json()
    member.status = MemberStatus.exited
    db.flush()
    assert approve(client, checker, request["id"]).status_code == 409


def _party(db, client_type=ClientType.individual, review_due=None):
    party = Party(client_type=client_type, name="Chikondi Banda", identifier="AB12-3456", risk_rating=RiskRating.low,
                  kyc_approved_at=datetime.now(timezone.utc), kyc_review_due=review_due or date.today() + timedelta(days=365))
    db.add(party)
    db.flush()
    return party


def test_personal_pension_needs_individual_kyc_client(client, db, maker, checker):
    fund = make_fund(db, maker, checker, fund_type="personal_pension")
    response = propose(client, maker, fund, body())
    assert response.status_code == 400 and "KYC client" in response.json()["detail"]
    corporate = _party(db, ClientType.corporate)
    assert propose(client, maker, fund, body(party_id=str(corporate.id))).status_code == 400
    person = _party(db)
    member = create(client, db, maker, checker, fund, body(party_id=str(person.id)))
    assert member.scheme_id is None and member.party_id == person.id
    # One membership per client per fund.
    assert propose(client, maker, fund, body(party_id=str(person.id), id_number="ZZ1")).status_code == 409


def test_benefit_payments_blocked_without_current_kyc(client, db, maker, checker, setup):
    fund, scheme, category = setup
    member = create(client, db, maker, checker, fund, body(scheme, category))
    assert "no approved KYC" in member_service.payment_block(db, member)
    party = _party(db)
    member.party_id = party.id
    db.flush()
    assert member_service.payment_block(db, member) is None
    party.kyc_review_due = date.today() - timedelta(days=1)
    db.flush()
    assert "review was due" in member_service.payment_block(db, member)
    assert client.get(f"/api/v1/members/{member.id}", headers=auth_headers(maker)).json()["kyc"]["state"] == "review_overdue"


def test_fund_code_locks_once_it_has_members(client, db, maker, checker, setup):
    from app.services import funds as fund_service
    fund, scheme, category = setup
    assert fund_service.locked_fields(db, fund) == []
    create(client, db, maker, checker, fund, body(scheme, category))
    assert fund_service.locked_fields(db, fund)


def test_employer_links_only_corporate_kyc_client(client, db):
    config_maker = make_user(db, UserRole.scheme_config_maker)
    fund = make_fund(db, config_maker, fund_type="umbrella_dc")
    person, company = _party(db), _party(db, ClientType.corporate)
    base = {"code": "NEW01", "name": "New Employer", "contribution_day": 10}
    h = auth_headers(config_maker)
    assert client.post(f"/api/v1/funds/{fund.id}/schemes", headers=h, json={**base, "party_id": str(person.id)}).status_code == 400
    response = client.post(f"/api/v1/funds/{fund.id}/schemes", headers=h, json={**base, "party_id": str(company.id)})
    assert response.status_code == 202 and response.json()["payload"]["party_id"] == str(company.id)


# ---- moves and transfers (FR-MEM-010)


def _move(client, user, member, scheme, category, when="2025-07-01", **extra):
    return client.post(f"/api/v1/members/{member.id}/move", headers=auth_headers(user),
                       json={"scheme_id": str(scheme.id), "category_id": str(category.id), "effective_date": when, "reason": "Promotion", **extra})


def test_category_move_closes_old_assignment(client, db, maker, checker, setup):
    fund, scheme, category = setup
    member = create(client, db, maker, checker, fund, body(scheme, category))
    mgt = _category(db, scheme, code="MGT")
    assert _move(client, maker, member, scheme, category).status_code == 400  # same place
    assert _move(client, maker, member, scheme, mgt, when="2023-12-31").status_code == 400  # before current start
    response = _move(client, maker, member, scheme, mgt)
    assert response.status_code == 202 and response.json()["payload"]["action"] == "category_move"
    assert approve(client, checker, response.json()["id"]).status_code == 200
    db.refresh(member)
    rows = db.query(MemberAssignment).filter_by(member_id=member.id).order_by(MemberAssignment.effective_from).all()
    assert [(r.category_id, r.effective_to) for r in rows] == [(category.id, date(2025, 6, 30)), (mgt.id, None)]
    assert member.category_id == mgt.id


def test_employer_transfer_only_in_umbrella_fund(client, db, maker, checker, setup):
    fund, scheme, category = setup
    member = create(client, db, maker, checker, fund, body(scheme, category))
    other = Scheme(fund_id=fund.id, code="EMP02", name="Other Ltd", contribution_day=14)
    db.add(other)
    db.flush()
    other_cat = _category(db, other, code="ALL")
    response = _move(client, maker, member, other, other_cat, employee_no="OT-77")
    assert response.status_code == 202, response.text
    approve(client, checker, response.json()["id"])
    db.refresh(member)
    assert (member.scheme_id, member.employee_no, member.date_joined_employer) == (other.id, "OT-77", date(2025, 7, 1))

    standalone = make_fund(db, maker, checker, fund_type="standalone_dc")
    s1 = Scheme(fund_id=standalone.id, code="S1", name="Sponsor", contribution_day=10)
    s2 = Scheme(fund_id=standalone.id, code="S2", name="Second", contribution_day=10)
    db.add_all([s1, s2])
    db.flush()
    c1, c2 = _category(db, s1), _category(db, s2)
    m2 = create(client, db, maker, checker, standalone, body(s1, c1, id_number="QQ1"))
    r = _move(client, maker, m2, s2, c2)
    assert r.status_code == 400 and "umbrella" in r.json()["detail"]


def test_move_refused_for_deferred_member(client, db, maker, checker, setup):
    fund, scheme, category = setup
    member = create(client, db, maker, checker, fund, body(scheme, category))
    member.status = MemberStatus.deferred
    db.flush()
    assert _move(client, maker, member, scheme, _category(db, scheme, code="MGT")).status_code == 400
