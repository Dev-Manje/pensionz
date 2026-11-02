"""System-wide Setup lists (FR-CFG-005, 006, 010) through one generic
maker-checker mechanism (services/system_lists.py)."""
import pytest

from app.models.identity import UserRole
from app.models.reference import Bank, BankBranch, District, TransactionType
from tests.factories import auth_headers, make_user

BASE = "/api/v1/setup/lists"


@pytest.fixture
def maker(db):
    return make_user(db, UserRole.scheme_config_maker)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.scheme_config_checker)


def approve(client, user, request_id):
    return client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(user), json={})


def propose(client, user, name, body, row_id=None):
    if row_id:
        return client.put(f"{BASE}/{name}/{row_id}", headers=auth_headers(user), json=body)
    return client.post(f"{BASE}/{name}", headers=auth_headers(user), json=body)


def test_describe_and_seeded_rows(client, db, maker):
    lists = {d["name"]: d for d in client.get(BASE, headers=auth_headers(maker)).json()}
    assert {"transaction_types", "account_types", "banks", "bank_branches", "districts", "countries", "salutations"} <= set(lists)
    assert lists["bank_branches"]["parent_field"] == "bank_id"
    codes = [r["code"] for r in client.get(f"{BASE}/transaction_types", headers=auth_headers(maker)).json()]
    assert codes == [1, 2, 3, 4, 5, 6]
    assert len(client.get(f"{BASE}/districts", headers=auth_headers(maker)).json()) == 28
    salutations = client.get(f"{BASE}/salutations", headers=auth_headers(maker)).json()
    assert salutations[0]["name"] == "Mr" and all("list_key" not in s for s in salutations)


def test_new_district_after_approval_and_case_insensitive_uniqueness(client, db, maker, checker):
    assert propose(client, maker, "districts", {"name": "lilongwe", "region": "central"}).status_code == 409
    response = propose(client, maker, "districts", {"name": "Test District", "region": "southern"})
    assert response.status_code == 202, response.text
    assert response.json()["payload"]["region"] == "Southern"  # readable for the checker
    assert db.query(District).filter_by(name="Test District").count() == 0
    assert approve(client, maker, response.json()["id"]).status_code == 400
    assert approve(client, checker, response.json()["id"]).status_code == 200
    assert db.query(District).filter_by(name="Test District").one().region == "southern"
    assert propose(client, maker, "districts", {"name": "TEST DISTRICT", "region": "southern"}).status_code == 409


def test_validation(client, db, maker):
    assert propose(client, maker, "districts", {"name": "", "region": "central"}).status_code == 400
    assert propose(client, maker, "districts", {"name": "X District", "region": "eastern"}).status_code == 400
    assert propose(client, maker, "transaction_types", {"code": "abc", "name": "X", "effect": "credit"}).status_code == 400


def test_branch_belongs_to_a_bank_and_parent_filter(client, db, maker, checker):
    bank = db.query(Bank).filter_by(name="FDH Bank").one()
    response = propose(client, maker, "bank_branches", {"bank_id": str(bank.id), "name": "Mangochi", "code": "fdh-mgc"})
    assert response.json()["payload"]["bank_id"] == "FDH Bank"
    assert approve(client, checker, response.json()["id"]).status_code == 200
    branch = db.query(BankBranch).filter_by(bank_id=bank.id, name="Mangochi").one()
    assert branch.code == "FDH-MGC"  # upper-cased
    rows = client.get(f"{BASE}/bank_branches?parent={bank.id}", headers=auth_headers(maker)).json()
    assert {r["name"] for r in rows} == {"Blantyre", "Lilongwe", "Mzuzu", "Zomba", "Mangochi"}
    assert rows[0]["bank_id_label"] == "FDH Bank"
    # The bank of a branch is fixed once set.
    other = db.query(Bank).filter_by(name="NBS Bank").one()
    assert propose(client, maker, "bank_branches", {"bank_id": str(other.id), "name": "Mangochi"}, branch.id).status_code == 400
    assert propose(client, maker, "bank_branches", {"bank_id": "00000000-0000-0000-0000-000000000000", "name": "X"}).status_code == 400


def test_retire_instead_of_delete(client, db, maker, checker):
    bank = db.query(Bank).filter_by(name="Centenary Bank Malawi").one()
    response = propose(client, maker, "banks", {"name": bank.name, "short_name": bank.short_name, "active": False}, bank.id)
    assert response.status_code == 202, response.text
    assert response.json()["previous"]["active"] == "Yes" and response.json()["payload"]["active"] == "No"
    assert approve(client, checker, response.json()["id"]).status_code == 200
    db.refresh(bank)
    assert bank.active is False
    # Retired banks drop out of pick-lists but stay in Setup.
    assert bank.name not in [b["name"] for b in client.get("/api/v1/reference/banks", headers=auth_headers(maker)).json()]
    assert bank.name in [b["name"] for b in client.get(f"{BASE}/banks", headers=auth_headers(maker)).json()]


def test_transaction_type_pairing(client, db, maker, checker):
    # Same effect as its proposed reversal → refused.
    assert propose(client, maker, "transaction_types", {"code": 70, "name": "Transfer In", "effect": "credit", "reversal_code": 1}).status_code == 400
    # Type 2 already reverses type 1.
    assert propose(client, maker, "transaction_types", {"code": 70, "name": "Transfer In", "effect": "debit", "reversal_code": 1}).status_code == 400
    assert propose(client, maker, "transaction_types", {"code": 70, "name": "Transfer In", "effect": "credit", "reversal_code": 99}).status_code == 400
    first = propose(client, maker, "transaction_types", {"code": 70, "name": "Transfer In", "effect": "credit", "credit_gl_code": "2000"})
    assert approve(client, checker, first.json()["id"]).status_code == 200
    second = propose(client, maker, "transaction_types", {"code": 71, "name": "Reversal Transfer In", "effect": "debit", "reversal_code": 70})
    assert second.status_code == 202, second.text
    assert approve(client, checker, second.json()["id"]).status_code == 200
    t70 = db.query(TransactionType).filter_by(code=70).one()
    db.refresh(t70)
    assert t70.reversal_code == 71  # paired both ways
    # Code and effect are fixed; the pairing can't be changed.
    assert propose(client, maker, "transaction_types", {"code": 72, "name": "Transfer In", "effect": "credit", "reversal_code": 71}, t70.id).status_code == 400
    assert propose(client, maker, "transaction_types", {"name": "Transfer In", "effect": "debit", "reversal_code": 71}, t70.id).status_code == 400
    renamed = propose(client, maker, "transaction_types", {"name": "Transfer In from another fund", "reversal_code": 71}, t70.id)
    assert renamed.status_code == 202, renamed.text


def test_one_pending_entry_per_key(client, db, maker):
    assert propose(client, maker, "salutations", {"code": "sir", "name": "Sir"}).status_code == 202
    assert propose(client, maker, "salutations", {"code": "SIR", "name": "Sir (again)"}).status_code == 409


def test_access(client, db, maker):
    finance = make_user(db, UserRole.finance)
    assert client.get(f"{BASE}/countries", headers=auth_headers(finance)).status_code == 200
    assert propose(client, finance, "districts", {"name": "Y District", "region": "central"}).status_code == 403
    po = make_user(db, UserRole.principal_officer)
    # Portal users read only the lists their KYC forms use.
    assert client.get(f"{BASE}/countries", headers=auth_headers(po)).status_code == 200
    assert client.get(f"{BASE}/transaction_types", headers=auth_headers(po)).status_code == 403
    assert propose(client, po, "countries", {"code": "XX", "name": "X"}).status_code == 403
    assert client.get(f"{BASE}/nope", headers=auth_headers(maker)).status_code == 404
