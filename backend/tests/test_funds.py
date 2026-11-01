"""Fund setup through maker-checker (FR-CFG-001, FR-CFG-011), fund scoping
(FR-SEC-001) and bank-number masking (FR-SEC-005)."""
import pytest
from sqlalchemy import select

from app.models.approval import ApprovalRequest
from app.models.audit import AuditEvent
from app.models.fund import Fund, FundBankAccount, UserFundAccess
from app.models.identity import UserRole
from app.models.reference import Bank
from app.services import fund_access
from app.services import funds as fund_service
from tests.factories import auth_headers, make_user


@pytest.fixture
def bank(db):
    return db.execute(select(Bank).where(Bank.name == "National Bank of Malawi")).scalar_one()


@pytest.fixture
def other_bank(db):
    return db.execute(select(Bank).where(Bank.name == "FDH Bank")).scalar_one()


def fund_body(bank, code="TST01", **overrides):
    branch = bank.branches[0]
    body = {
        "code": code,
        "name": "Test Staff Pension Fund",
        "fund_type": "standalone_dc",
        "registration_number": "RBM/PF/999",
        "email": "fund@test.dev",
        "address_line1": "Private Bag 9",
        "financial_year_end_month": 6,
        "contact_name": "Fund Secretary",
        "contact_email": "",  # blank optional fields are allowed
        "trustees": [{"full_name": "Ann Trustee", "designation": "Chairperson"}, {"full_name": "Bob Trustee"}],
        "bank_accounts": [{
            "bank_id": str(bank.id), "branch_id": str(branch.id), "account_name": "Test Fund Collections",
            "account_number": "1001 2345 67", "purpose": "collections",
        }],
    }
    body.update(overrides)
    return body


def approve(client, checker, request_id):
    return client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(checker), json={})


def create_fund(client, db, bank, maker, checker, code="TST01") -> Fund:
    response = client.post("/api/v1/funds", headers=auth_headers(maker), json=fund_body(bank, code))
    assert response.status_code == 202, response.text
    assert approve(client, checker, response.json()["id"]).status_code == 200
    return db.execute(select(Fund).where(Fund.code == code)).scalar_one()


@pytest.fixture
def maker(db):
    return make_user(db, UserRole.scheme_config_maker)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.scheme_config_checker)


def test_new_fund_waits_for_a_checker(client, db, bank, maker):
    response = client.post("/api/v1/funds", headers=auth_headers(maker), json=fund_body(bank))
    assert response.status_code == 202
    assert response.json()["kind"] == "fund_setup"
    assert db.execute(select(Fund).where(Fund.code == "TST01")).scalar_one_or_none() is None


def test_maker_cannot_approve_own_fund(client, db, bank, maker):
    request_id = client.post("/api/v1/funds", headers=auth_headers(maker), json=fund_body(bank)).json()["id"]
    assert approve(client, maker, request_id).status_code == 400


def test_only_scheme_setup_checker_approves(client, db, bank, maker):
    request_id = client.post("/api/v1/funds", headers=auth_headers(maker), json=fund_body(bank)).json()["id"]
    finance_checker = make_user(db, UserRole.finance_checker)
    assert approve(client, finance_checker, request_id).status_code == 403


def test_only_scheme_setup_maker_proposes(client, db, bank):
    other = make_user(db, UserRole.member_admin)
    assert client.post("/api/v1/funds", headers=auth_headers(other), json=fund_body(bank)).status_code == 403


def test_approval_creates_fund_with_trustees_and_accounts(client, db, bank, maker, checker):
    fund = create_fund(client, db, bank, maker, checker)
    assert fund.fund_type.value == "standalone_dc"
    assert fund.contact_email is None
    assert [t.full_name for t in fund.trustees] == ["Ann Trustee", "Bob Trustee"]
    assert fund.bank_accounts[0].account_number == "1001234567"  # spaces stripped
    # The maker and checker administer the fund they set up.
    assert fund_access.can_access(db, maker, fund.id)
    assert fund_access.can_access(db, checker, fund.id)
    assert db.query(AuditEvent).filter_by(entity_type="fund", entity_id=str(fund.id), action="created").count() == 1


def test_duplicate_code_is_refused(client, db, bank, maker, checker):
    create_fund(client, db, bank, maker, checker)
    again = client.post("/api/v1/funds", headers=auth_headers(maker), json=fund_body(bank, code="tst01"))
    assert again.status_code == 409


def test_code_already_waiting_for_approval_is_refused(client, db, bank, maker):
    assert client.post("/api/v1/funds", headers=auth_headers(maker), json=fund_body(bank, code="WAIT1")).status_code == 202
    assert client.post("/api/v1/funds", headers=auth_headers(maker), json=fund_body(bank, code="WAIT1")).status_code == 409


def test_invalid_code_and_branch_of_another_bank(client, db, bank, other_bank, maker):
    assert client.post("/api/v1/funds", headers=auth_headers(maker), json=fund_body(bank, code="TOO-LONG-CODE")).status_code == 422
    body = fund_body(bank)
    body["bank_accounts"][0]["branch_id"] = str(other_bank.branches[0].id)
    response = client.post("/api/v1/funds", headers=auth_headers(maker), json=body)
    assert response.status_code == 400
    assert "branch" in response.json()["detail"]


def test_edit_applies_only_after_approval_and_keeps_removed_account(client, db, bank, other_bank, maker, checker):
    fund = create_fund(client, db, bank, maker, checker)
    old_account_id = fund.bank_accounts[0].id
    body = fund_body(bank, name="Renamed Fund")
    body["trustees"] = [{"id": str(fund.trustees[0].id), "full_name": "Ann Trustee", "designation": "Chairperson"}]
    body["bank_accounts"] = [{"bank_id": str(other_bank.id), "account_name": "New account", "account_number": "5550001111"}]

    response = client.put(f"/api/v1/funds/{fund.id}", headers=auth_headers(maker), json=body)
    assert response.status_code == 202, response.text
    request = response.json()
    assert request["previous"]["name"] == "Test Staff Pension Fund"
    db.refresh(fund)
    assert fund.name == "Test Staff Pension Fund"

    detail = client.get(f"/api/v1/funds/{fund.id}", headers=auth_headers(maker)).json()
    assert detail["pending_approval_id"] == request["id"]
    # A second change can't be stacked on top of the waiting one.
    assert client.put(f"/api/v1/funds/{fund.id}", headers=auth_headers(maker), json=fund_body(bank, name="Again")).status_code == 409

    assert approve(client, checker, request["id"]).status_code == 200
    db.refresh(fund)
    assert fund.name == "Renamed Fund"
    assert [t.full_name for t in fund.trustees if t.active] == ["Ann Trustee"]
    old = db.get(FundBankAccount, old_account_id)
    assert old is not None and old.active is False  # retired, not deleted
    assert [a.account_number for a in fund.bank_accounts if a.active] == ["5550001111"]


def test_unchanged_edit_is_refused(client, db, bank, maker, checker):
    fund = create_fund(client, db, bank, maker, checker)
    detail = client.get(f"/api/v1/funds/{fund.id}", headers=auth_headers(maker)).json()
    body = fund_body(bank)
    body["trustees"] = [{"id": t["id"], "full_name": t["full_name"], "designation": t["designation"]} for t in detail["trustees"]]
    body["bank_accounts"] = [{"id": a["id"], "bank_id": a["bank_id"], "branch_id": a["branch_id"], "account_name": a["account_name"],
                              "account_number": a["account_number"], "purpose": a["purpose"]} for a in detail["bank_accounts"]]
    response = client.put(f"/api/v1/funds/{fund.id}", headers=auth_headers(maker), json=body)
    assert response.status_code == 400
    assert response.json()["detail"] == "Nothing has changed"


def test_code_and_type_frozen_once_members_exist(client, db, bank, maker, checker, monkeypatch):
    fund = create_fund(client, db, bank, maker, checker)
    monkeypatch.setattr(fund_service, "fund_has_members", lambda db, fund: True)
    response = client.put(f"/api/v1/funds/{fund.id}", headers=auth_headers(maker), json=fund_body(bank, fund_type="umbrella_dc"))
    assert response.status_code == 400
    assert "fund type" in response.json()["detail"]
    assert client.get(f"/api/v1/funds/{fund.id}", headers=auth_headers(maker)).json()["locked_fields"] == ["code", "fund_type"]


def test_staff_only_see_their_funds(client, db, bank, maker, checker):
    fund = create_fund(client, db, bank, maker, checker)
    outsider = make_user(db, UserRole.contributions_officer)
    assert client.get(f"/api/v1/funds/{fund.id}", headers=auth_headers(outsider)).status_code == 404
    assert all(f["id"] != str(fund.id) for f in client.get("/api/v1/funds", headers=auth_headers(outsider)).json())
    # Can't propose a change to a fund you don't administer either.
    other_maker = make_user(db, UserRole.scheme_config_maker)
    assert client.put(f"/api/v1/funds/{fund.id}", headers=auth_headers(other_maker), json=fund_body(bank, name="Other name")).status_code == 404

    auditor = make_user(db, UserRole.auditor)
    assert client.get(f"/api/v1/funds/{fund.id}", headers=auth_headers(auditor)).status_code == 200


def test_portal_users_cannot_list_funds(client, db):
    po = make_user(db, UserRole.principal_officer)
    assert client.get("/api/v1/funds", headers=auth_headers(po)).status_code == 403


def test_bank_numbers_masked_for_roles_that_dont_need_them(client, db, bank, maker, checker):
    fund = create_fund(client, db, bank, maker, checker)
    officer = make_user(db, UserRole.contributions_officer)
    fund_access.grant(db, officer.id, fund.id, None)
    account = client.get(f"/api/v1/funds/{fund.id}", headers=auth_headers(officer)).json()["bank_accounts"][0]
    assert account["account_number"] is None
    assert account["account_number_masked"] == "•••• 4567"
    full = client.get(f"/api/v1/funds/{fund.id}", headers=auth_headers(maker)).json()["bank_accounts"][0]
    assert full["account_number"] == "1001234567"


def test_checker_without_the_fund_cannot_see_or_decide_its_changes(client, db, bank, maker, checker):
    fund = create_fund(client, db, bank, maker, checker)
    request_id = client.put(f"/api/v1/funds/{fund.id}", headers=auth_headers(maker), json=fund_body(bank, name="Changed")).json()["id"]
    outsider = make_user(db, UserRole.scheme_config_checker)
    listed = client.get("/api/v1/approvals", headers=auth_headers(outsider)).json()
    assert all(a["id"] != request_id for a in listed)
    assert approve(client, outsider, request_id).status_code == 404
    fund_access.grant(db, outsider.id, fund.id, None)
    assert approve(client, outsider, request_id).status_code == 200


def test_fund_access_is_assigned_through_user_approval(client, db, bank, maker, checker):
    fund = create_fund(client, db, bank, maker, checker)
    admin1, admin2 = make_user(db, UserRole.admin), make_user(db, UserRole.admin)
    target = make_user(db, UserRole.contributions_officer)
    response = client.patch(f"/api/v1/users/{target.id}", headers=auth_headers(admin1), json={"fund_ids": [str(fund.id)]})
    assert response.status_code == 202
    assert response.json()["payload"]["funds"] == ["TST01"]
    assert db.query(UserFundAccess).filter_by(user_id=target.id).count() == 0
    assert approve(client, admin2, response.json()["id"]).status_code == 200
    assert client.get(f"/api/v1/funds/{fund.id}", headers=auth_headers(target)).status_code == 200
    assert client.get(f"/api/v1/users/{target.id}", headers=auth_headers(admin1)).json()["fund_ids"] == [str(fund.id)]


def test_reference_banks_lists_seeded_malawi_banks(client, db, maker):
    banks = client.get("/api/v1/reference/banks", headers=auth_headers(maker)).json()
    names = [b["name"] for b in banks]
    assert names[0] == "National Bank of Malawi"
    assert len(names) >= 8 and all(b["branches"] for b in banks)
    assert client.get("/api/v1/reference/banks").status_code == 401
