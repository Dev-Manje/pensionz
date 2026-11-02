"""Contribution receipts (FR-CON-004): payment notices, staff capture, checker
confirmation posting Dr 1000 / Cr 2100, unidentified money, ageing, access."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.approval import ApprovalRequest
from app.models.contribution import ContributionReceipt, PaymentMethod, ReceiptStatus
from app.models.fund import FundBankAccount
from app.models.identity import UserRole
from app.models.mixins import utcnow
from app.models.notification import UserNotification
from app.models.period import FundPeriod, PeriodStatus
from app.models.reference import Bank
from app.models.scheme import Scheme, SchemeOfficer
from app.services import ledger, receipts
from tests.factories import auth_headers, make_fund, make_user

D = Decimal
TODAY = date.today()


@pytest.fixture
def officer(db):
    return make_user(db, UserRole.contributions_officer)


@pytest.fixture
def checker(db):
    return make_user(db, UserRole.contributions_checker)


@pytest.fixture
def po(db):
    return make_user(db, UserRole.principal_officer)


@pytest.fixture
def setup(db, officer, checker, po):
    fund = make_fund(db, officer, checker, fund_type="umbrella_dc")
    db.add(FundPeriod(fund_id=fund.id, period=TODAY.replace(day=1), status=PeriodStatus.open, opened_at=utcnow()))
    scheme = Scheme(fund_id=fund.id, code="EMP01", name="Employer Ltd", contribution_day=14)
    db.add(scheme)
    db.flush()
    db.add(SchemeOfficer(scheme_id=scheme.id, user_id=po.id))
    bank = db.execute(select(Bank).limit(1)).scalar_one()
    account = FundBankAccount(fund_id=fund.id, bank_id=bank.id, account_name="Fund Collections", account_number="1001001")
    db.add(account)
    db.flush()
    db.refresh(scheme)
    return fund, scheme, account


def capture_body(scheme, account, **kw):
    b = {"scheme_id": str(scheme.id) if scheme else None, "payment_method": "eft", "payment_date": TODAY.isoformat(),
         "value_date": TODAY.isoformat(), "amount": "150000.00", "bank_account_id": str(account.id),
         "payer_name": "Employer Ltd", "payer_reference": "EMP01 OCT", "bank_reference": "FT2611001"}
    b.update(kw)
    return b


def approve(client, user, request_id):
    return client.post(f"/api/v1/approvals/{request_id}/approve", headers=auth_headers(user), json={})


def test_staff_capture_posts_only_after_checker_approval(client, db, officer, checker, po, setup):
    fund, scheme, account = setup
    r = client.post(f"/api/v1/funds/{fund.id}/receipts", headers=auth_headers(officer), json=capture_body(scheme, account))
    assert r.status_code == 202, r.text
    receipt = db.get(ContributionReceipt, uuid.UUID(r.json()["entity_id"]))
    assert receipt.status == ReceiptStatus.pending_approval and receipt.journal_entry_id is None
    assert ledger.gl_balance(db, fund.id, "1000") == D("0")
    # The maker can't approve their own capture.
    assert approve(client, officer, r.json()["id"]).status_code in (400, 403)
    assert approve(client, checker, r.json()["id"]).status_code == 200
    db.refresh(receipt)
    assert receipt.status == ReceiptStatus.confirmed and receipt.receipt_number == f"{fund.code}-R000001"
    assert ledger.gl_balance(db, fund.id, "1000") == D("150000.00")
    assert ledger.gl_balance(db, fund.id, "2100") == D("150000.00")
    assert receipt.unallocated == D("150000.00")
    # The employer's principal officer hears about it.
    assert db.execute(select(UserNotification).where(UserNotification.user_id == po.id, UserNotification.event == "receipt.confirmed")).first()


def test_notice_then_confirmation_with_actual_amount(client, db, officer, checker, po, setup):
    fund, scheme, account = setup
    notice = receipts.submit_notice(db, po, scheme, amount=D("100000"), payment_date=TODAY, payment_method=PaymentMethod.eft,
                                    payer_reference="EMP01", contribution_month=TODAY, notes=None)
    assert notice.status == ReceiptStatus.notified and notice.notice_number == f"{fund.code}-N000001"
    assert ledger.gl_balance(db, fund.id, "1000") == D("0")
    staff = client.get(f"/api/v1/receipts/{notice.id}", headers=auth_headers(officer)).json()
    assert staff["can_confirm"] is True
    r = client.post(f"/api/v1/receipts/{notice.id}/confirm", headers=auth_headers(officer),
                    json={"value_date": TODAY.isoformat(), "amount": "99500.00", "bank_account_id": str(account.id), "bank_reference": "FT1"})
    assert r.status_code == 202, r.text
    assert approve(client, checker, r.json()["id"]).status_code == 200
    db.refresh(notice)
    assert notice.status == ReceiptStatus.confirmed and notice.amount == D("99500.00") and notice.notified_amount == D("100000.00")
    assert notice.scheme_id == scheme.id


def test_rejected_confirmation_returns_notice_to_waiting(client, db, officer, checker, po, setup):
    fund, scheme, account = setup
    notice = receipts.submit_notice(db, po, scheme, amount=D("5000"), payment_date=TODAY, payment_method=PaymentMethod.cheque,
                                    payer_reference=None, contribution_month=None, notes=None)
    r = client.post(f"/api/v1/receipts/{notice.id}/confirm", headers=auth_headers(officer),
                    json={"value_date": TODAY.isoformat(), "amount": "5000", "bank_account_id": str(account.id)})
    rej = client.post(f"/api/v1/approvals/{r.json()['id']}/reject", headers=auth_headers(checker), json={"comment": "Cheque not cleared"})
    assert rej.status_code == 200, rej.text
    db.refresh(notice)
    assert notice.status == ReceiptStatus.notified and notice.amount is None and notice.value_date is None


def test_decline_notice_tells_the_officer(client, db, officer, po, setup):
    fund, scheme, account = setup
    notice = receipts.submit_notice(db, po, scheme, amount=D("5000"), payment_date=TODAY, payment_method=PaymentMethod.eft,
                                    payer_reference=None, contribution_month=None, notes=None)
    assert client.post(f"/api/v1/receipts/{notice.id}/decline", headers=auth_headers(officer), json={"reason": "x"}).status_code == 400
    r = client.post(f"/api/v1/receipts/{notice.id}/decline", headers=auth_headers(officer), json={"reason": "Not on the statement"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert db.execute(select(UserNotification).where(UserNotification.user_id == po.id, UserNotification.event == "receipt.declined")).first()


def test_notice_only_for_own_scheme(db, setup):
    fund, scheme, account = setup
    stranger = make_user(db, UserRole.principal_officer)
    with pytest.raises(Exception) as exc:
        receipts.submit_notice(db, stranger, scheme, amount=D("1"), payment_date=TODAY, payment_method=PaymentMethod.eft,
                               payer_reference=None, contribution_month=None, notes=None)
    assert getattr(exc.value, "status_code", None) == 404


def test_unidentified_money_then_identified(client, db, officer, checker, setup):
    fund, scheme, account = setup
    r = client.post(f"/api/v1/funds/{fund.id}/receipts", headers=auth_headers(officer), json=capture_body(None, account, amount="2500"))
    approve(client, checker, r.json()["id"])
    receipt = db.get(ContributionReceipt, uuid.UUID(r.json()["entity_id"]))
    listing = client.get(f"/api/v1/funds/{fund.id}/receipts?unidentified=true", headers=auth_headers(officer)).json()
    assert listing["total"] == 1 and listing["items"][0]["can_identify"]
    assert listing["unallocated_ageing"][0]["amount"] == "2500.00"
    ident = client.post(f"/api/v1/receipts/{receipt.id}/identify", headers=auth_headers(officer), json={"scheme_id": str(scheme.id)})
    assert ident.status_code == 202, ident.text
    assert approve(client, checker, ident.json()["id"]).status_code == 200
    db.refresh(receipt)
    assert receipt.scheme_id == scheme.id
    assert ledger.gl_balance(db, fund.id, "2100") == D("2500.00")  # a reclass inside suspense
    assert ledger.tie_out(db, fund.id).balanced


def test_value_date_rules(client, db, officer, setup):
    fund, scheme, account = setup
    future = client.post(f"/api/v1/funds/{fund.id}/receipts", headers=auth_headers(officer),
                         json=capture_body(scheme, account, value_date=(TODAY + timedelta(days=1)).isoformat()))
    assert future.status_code == 400
    # Money that cleared in an earlier (closed) month posts on the first day of the open month.
    earlier = TODAY.replace(day=1) - timedelta(days=3)
    assert receipts.posting_date(db, fund.id, earlier) == TODAY.replace(day=1)


def test_wrong_bank_account_and_employer_refused(client, db, officer, setup, staff_other_fund):
    fund, scheme, account = setup
    other_fund, other_scheme, other_account = staff_other_fund
    bad_account = client.post(f"/api/v1/funds/{fund.id}/receipts", headers=auth_headers(officer), json=capture_body(scheme, other_account))
    assert bad_account.status_code == 400
    bad_scheme = client.post(f"/api/v1/funds/{fund.id}/receipts", headers=auth_headers(officer), json=capture_body(other_scheme, account))
    assert bad_scheme.status_code == 400


@pytest.fixture
def staff_other_fund(db, officer):
    fund = make_fund(db, officer)
    scheme = Scheme(fund_id=fund.id, code="OTH01", name="Other", contribution_day=14)
    bank = db.execute(select(Bank).limit(1)).scalar_one()
    db.add(scheme)
    account = FundBankAccount(fund_id=fund.id, bank_id=bank.id, account_name="Other", account_number="9")
    db.add(account)
    db.flush()
    return fund, scheme, account


def test_receipt_access(client, db, setup):
    fund, scheme, account = setup
    outsider = make_user(db, UserRole.contributions_officer)
    assert client.get(f"/api/v1/funds/{fund.id}/receipts", headers=auth_headers(outsider)).status_code == 404
    member_admin = make_user(db, UserRole.member_admin)
    assert client.post(f"/api/v1/funds/{fund.id}/receipts", headers=auth_headers(member_admin),
                       json=capture_body(scheme, account)).status_code == 403
    portal = make_user(db, UserRole.principal_officer)
    assert client.get(f"/api/v1/funds/{fund.id}/receipts", headers=auth_headers(portal)).status_code == 403


def test_receipt_documents(client, db, officer, checker, po, setup):
    fund, scheme, account = setup
    notice = receipts.submit_notice(db, po, scheme, amount=D("742300"), payment_date=TODAY, payment_method=PaymentMethod.rtgs,
                                    payer_reference="EMP01 OCT", contribution_month=TODAY, notes=None)
    h = auth_headers(officer)
    assert client.get(f"/api/v1/receipts/{notice.id}", headers=h).json()["document_kind"] == "acknowledgement"
    ack = client.get(f"/api/v1/receipts/{notice.id}/document", headers=h)
    assert ack.status_code == 200 and ack.content.startswith(b"%PDF")
    r = client.post(f"/api/v1/receipts/{notice.id}/confirm", headers=h,
                    json={"value_date": TODAY.isoformat(), "amount": "742300", "bank_account_id": str(account.id)})
    approve(client, checker, r.json()["id"])
    assert client.get(f"/api/v1/receipts/{notice.id}", headers=h).json()["document_kind"] == "receipt"
    official = client.get(f"/api/v1/receipts/{notice.id}/document", headers=h)
    assert official.status_code == 200 and f"{fund.code}-R000001.pdf" in official.headers["content-disposition"]
    # A staff capture has nothing to print until it is confirmed.
    pending = client.post(f"/api/v1/funds/{fund.id}/receipts", headers=h, json=capture_body(scheme, account)).json()
    assert client.get(f"/api/v1/receipts/{pending['entity_id']}/document", headers=h).status_code == 409


def test_amount_in_words():
    from app.services.io.receipt_document import amount_in_words
    assert amount_in_words(D("1250000.50")) == "One million two hundred and fifty thousand kwacha and fifty tambala"
    assert amount_in_words(D("1001")) == "One thousand and one kwacha only"
    assert amount_in_words(D("284006.25")) == "Two hundred and eighty-four thousand and six kwacha and twenty-five tambala"
