"""Contribution receipts and unallocated suspense (FR-CON-004).

Two stages (see models/contribution.py):
- `submit_notice` — a principal officer's payment notice; nothing posts. Staff
  either `propose_confirmation` (the money is on the statement) or `decline` it.
- `capture` — staff record money that arrived without a notice.
Both end in the approval kind "receipt_confirm" (contributions checker), whose
apply posts Dr 1000 / Cr 2100 with the employer as analysis, issues the receipt
number and tells the employer's principal officers.

Posting date: the value date when it falls in the fund's open month; money
that cleared in an already-closed month posts on the first day of the open
month (the receipt keeps its real value date). A value date after today, or
after the open month, is refused.

`propose_identification` (approval kind "receipt_identify") places
unidentified money with an employer by a reclassification inside 2100.
"""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import storage
from app.models.approval import ApprovalRequest
from app.models.contribution import ContributionReceipt, PaymentMethod, ReceiptSource, ReceiptStatus
from app.models.fund import Fund, FundBankAccount
from app.models.identity import User, UserRole
from app.models.mixins import utcnow
from app.models.scheme import Scheme, SchemeOfficer
from app.services import approvals, audit, fund_access, ledger, notifications, periods

CONFIRM_KIND = "receipt_confirm"
IDENTIFY_KIND = "receipt_identify"
MAKERS = (UserRole.contributions_officer,)
CHECKERS = frozenset({UserRole.contributions_checker})
BANK = "1000"
METHOD_LABELS = {PaymentMethod.eft: "EFT", PaymentMethod.rtgs: "RTGS", PaymentMethod.cheque: "Cheque",
                 PaymentMethod.cash_deposit: "Cash deposit", PaymentMethod.mobile_money: "Mobile money"}


def today() -> date:
    return date.today()


def money_label(amount: Decimal | None) -> str:
    return f"MWK {amount:,.2f}" if amount is not None else "—"


def _next_number(db: Session, fund: Fund, kind: str) -> str:
    """Running number per fund: "UMB01-R000001" (receipts) / "UMB01-N000001" (notices)."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"receipt:{kind}:{fund.id}"})
    column = ContributionReceipt.receipt_number if kind == "R" else ContributionReceipt.notice_number
    prefix = f"{fund.code}-{kind}"
    last = db.execute(select(func.max(column)).where(ContributionReceipt.fund_id == fund.id, column.like(f"{prefix}%"))).scalar()
    return f"{prefix}{(int(last[len(prefix):]) if last else 0) + 1:06d}"


def _scheme(db: Session, fund: Fund, scheme_id: uuid.UUID | None, *, required: bool) -> Scheme | None:
    if scheme_id is None:
        if required:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose the employer the money is from")
        return None
    scheme = db.get(Scheme, scheme_id)
    if scheme is None or scheme.fund_id != fund.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That employer isn't part of this fund")
    return scheme


def _bank_account(db: Session, fund: Fund, account_id: uuid.UUID | None) -> FundBankAccount:
    account = db.get(FundBankAccount, account_id) if account_id else None
    if account is None or account.fund_id != fund.id or not account.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose the fund bank account the money went into")
    return account


def _check_amount(amount: Decimal | None, label: str = "amount") -> Decimal:
    if amount is None or amount <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The {label} must be more than zero")
    return ledger.money(amount)


def posting_date(db: Session, fund_id: uuid.UUID, value_date: date) -> date:
    """The date the receipt posts on (see module doc)."""
    if value_date > today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The value date can't be in the future")
    period = periods.current(db, fund_id)
    if period is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This fund has no open processing month yet")
    if periods.month_start(value_date) > period.period:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"The value date is after the open month ({periods.label(period.period)}) — close that month first")
    return value_date if periods.month_start(value_date) == period.period else period.period


@dataclass
class ConfirmValues:
    amount: Decimal
    value_date: date
    bank_account_id: uuid.UUID
    bank_reference: str | None
    scheme_id: uuid.UUID | None
    contribution_month: date | None
    notes: str | None


def _summary(db: Session, fund: Fund, receipt: ContributionReceipt, values: ConfirmValues) -> tuple[str, dict]:
    scheme = db.get(Scheme, values.scheme_id) if values.scheme_id else None
    employer = f"{scheme.code} — {scheme.name}" if scheme else "Unidentified"
    payload = {
        "fund": fund.code, "employer": employer, "amount": money_label(values.amount), "value_date": values.value_date,
        "posting_date": posting_date(db, fund.id, values.value_date),
        "bank_account": _bank_account(db, fund, values.bank_account_id).account_name,
        "bank_reference": values.bank_reference, "payment_method": METHOD_LABELS[receipt.payment_method],
        "payer": receipt.payer_name, "payer_reference": receipt.payer_reference,
        "contribution_month": periods.label(values.contribution_month) if values.contribution_month else None,
        "notice": receipt.notice_number,
        "notified_amount": money_label(receipt.notified_amount) if receipt.notified_amount else None, "notes": values.notes,
        # Raw values the apply step uses.
        "_values": {"amount": str(values.amount), "value_date": values.value_date.isoformat(), "bank_account_id": str(values.bank_account_id),
                    "bank_reference": values.bank_reference, "scheme_id": str(values.scheme_id) if values.scheme_id else None,
                    "contribution_month": values.contribution_month.isoformat() if values.contribution_month else None, "notes": values.notes},
    }
    return f"Confirm receipt of {money_label(values.amount)} from {employer} into {fund.code}", payload


def _submit_confirmation(db: Session, user: User, fund: Fund, receipt: ContributionReceipt, values: ConfirmValues) -> ApprovalRequest:
    _check_amount(values.amount)
    _bank_account(db, fund, values.bank_account_id)
    _scheme(db, fund, values.scheme_id, required=False)
    summary, payload = _summary(db, fund, receipt, values)
    request = approvals.submit(db, user, CONFIRM_KIND, entity_type="contribution_receipt", entity_id=receipt.id,
                               summary=summary, payload=payload, fund_id=fund.id)
    # Shown on the receipt while it waits; the checker's approval confirms them.
    receipt.amount, receipt.value_date, receipt.bank_account_id = ledger.money(values.amount), values.value_date, values.bank_account_id
    receipt.bank_reference = values.bank_reference
    receipt.status = ReceiptStatus.pending_approval
    receipt.captured_by_user_id = user.id
    receipt.approval_request_id = request.id
    return request


# ---- stage 1: payment notice (principal officer portal, Phase 5 screens)


def submit_notice(db: Session, user: User, scheme: Scheme, *, amount: Decimal, payment_date: date, payment_method: PaymentMethod,
                  payer_reference: str | None, contribution_month: date | None, notes: str | None) -> ContributionReceipt:
    if not user.has_role(UserRole.principal_officer) or db.execute(
        select(SchemeOfficer.id).where(SchemeOfficer.scheme_id == scheme.id, SchemeOfficer.user_id == user.id)
    ).first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employer not found")
    if payment_date > today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The payment date can't be in the future")
    fund = db.get(Fund, scheme.fund_id)
    receipt = ContributionReceipt(
        fund_id=fund.id, scheme_id=scheme.id, status=ReceiptStatus.notified, source=ReceiptSource.portal_notice,
        notice_number=_next_number(db, fund, "N"), payment_method=payment_method, notified_amount=_check_amount(amount),
        payment_date=payment_date, payer_name=scheme.name, payer_reference=(payer_reference or "").strip() or None,
        contribution_month=periods.month_start(contribution_month) if contribution_month else None, notes=notes,
        notified_by_user_id=user.id,
    )
    db.add(receipt)
    db.flush()
    audit.record(db, user.id, "contribution_receipt", receipt.id, "notified", after={"amount": receipt.notified_amount}, fund_id=fund.id)
    staff = [u for u in notifications.users_with_roles(db, set(MAKERS)) if fund_access.can_access(db, u, fund.id)]
    for officer in staff:
        notifications._notify(db, officer, "receipt.notified", f"Payment notice {receipt.notice_number}",
                              f"{scheme.name} says it paid {money_label(receipt.notified_amount)} on {payment_date:%d %b %Y}. "
                              "Confirm it against the bank statement.", link=f"/contributions/receipts/{receipt.id}",
                              entity_type="contribution_receipt", entity_id=receipt.id, email=False)
    db.commit()
    db.refresh(receipt)
    return receipt


def propose_confirmation(db: Session, user: User, receipt: ContributionReceipt, values: ConfirmValues) -> ApprovalRequest:
    """Staff found the notified money on the statement."""
    if receipt.status != ReceiptStatus.notified:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a payment notice waiting for confirmation can be confirmed")
    fund = db.get(Fund, receipt.fund_id)
    if values.scheme_id is None:
        values.scheme_id = receipt.scheme_id
    request = _submit_confirmation(db, user, fund, receipt, values)
    db.commit()
    db.refresh(request)
    return request


def decline(db: Session, user: User, receipt: ContributionReceipt, reason: str) -> ContributionReceipt:
    """The notified money never arrived (or the proof is wrong): tell the officer."""
    if receipt.status != ReceiptStatus.notified:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a payment notice waiting for confirmation can be declined")
    if not reason or len(reason.strip()) < 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say why, so the employer knows what to do")
    receipt.status, receipt.rejection_reason = ReceiptStatus.rejected, reason.strip()
    audit.record(db, user.id, "contribution_receipt", receipt.id, "declined", after={"reason": receipt.rejection_reason}, fund_id=receipt.fund_id)
    notifier = db.get(User, receipt.notified_by_user_id) if receipt.notified_by_user_id else None
    if notifier is not None:
        notifications._notify(db, notifier, "receipt.declined", f"Payment notice {receipt.notice_number} not confirmed",
                              f"We couldn't confirm your payment of {money_label(receipt.notified_amount)}: {receipt.rejection_reason}",
                              link=f"/po/remittances/{receipt.id}", entity_type="contribution_receipt", entity_id=receipt.id)
    db.commit()
    db.refresh(receipt)
    return receipt


# ---- stage 2 without a notice


def capture(db: Session, user: User, fund: Fund, *, payment_method: PaymentMethod, payment_date: date, payer_name: str | None,
            payer_reference: str | None, values: ConfirmValues) -> tuple[ContributionReceipt, ApprovalRequest]:
    if payment_date > today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The payment date can't be in the future")
    if values.value_date < payment_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The value date can't be before the payment date")
    receipt = ContributionReceipt(
        fund_id=fund.id, scheme_id=values.scheme_id, status=ReceiptStatus.pending_approval, source=ReceiptSource.staff,
        payment_method=payment_method, payment_date=payment_date, payer_name=(payer_name or "").strip() or None,
        payer_reference=(payer_reference or "").strip() or None,
    )
    _scheme(db, fund, values.scheme_id, required=False)
    db.add(receipt)
    db.flush()
    request = _submit_confirmation(db, user, fund, receipt, values)
    audit.record(db, user.id, "contribution_receipt", receipt.id, "captured", after={"amount": values.amount}, fund_id=fund.id)
    db.commit()
    db.refresh(receipt)
    return receipt, request


def attach_proof(db: Session, user: User, receipt: ContributionReceipt, filename: str, content: bytes) -> ContributionReceipt:
    if receipt.status not in (ReceiptStatus.notified, ReceiptStatus.pending_approval):
        raise HTTPException(status.HTTP_409_CONFLICT, "Proof of payment can only be added before the receipt is confirmed")
    if len(content) > storage.MAX_EVIDENCE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is larger than 10 MB")
    content_type = storage.evidence_type(content)
    if content_type is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a PDF or a photo (JPEG, PNG or WebP)")
    receipt.proof_storage_key = storage.upload_file(content, content_type, f"receipts/{receipt.id}")
    receipt.proof_filename, receipt.proof_content_type = filename[:200] or "proof", content_type
    audit.record(db, user.id, "contribution_receipt", receipt.id, "proof_attached", after={"filename": receipt.proof_filename}, fund_id=receipt.fund_id)
    db.commit()
    db.refresh(receipt)
    return receipt


# ---- approval: confirm


def _apply_confirm(db: Session, request: ApprovalRequest, checker: User) -> None:
    receipt = db.execute(select(ContributionReceipt).where(ContributionReceipt.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one()
    if receipt.status != ReceiptStatus.pending_approval:
        raise HTTPException(status.HTTP_409_CONFLICT, "This receipt is no longer waiting for approval")
    fund = db.get(Fund, receipt.fund_id)
    v = request.payload["_values"]
    amount, value_date = Decimal(v["amount"]), date.fromisoformat(v["value_date"])
    scheme = _scheme(db, fund, uuid.UUID(v["scheme_id"]) if v["scheme_id"] else None, required=False)
    _bank_account(db, fund, uuid.UUID(v["bank_account_id"]))
    receipt.amount, receipt.value_date, receipt.bank_account_id = amount, value_date, uuid.UUID(v["bank_account_id"])
    receipt.bank_reference, receipt.scheme_id = v["bank_reference"], scheme.id if scheme else None
    receipt.contribution_month = date.fromisoformat(v["contribution_month"]) if v["contribution_month"] else receipt.contribution_month
    receipt.notes = v["notes"] or receipt.notes
    receipt.receipt_number = _next_number(db, fund, "R")
    who = scheme.name if scheme else "unidentified payer"
    entry = ledger.post(
        db, fund.id, entity_type="contribution_receipt", entity_id=receipt.id, entry_date=posting_date(db, fund.id, value_date),
        description=f"Receipt {receipt.receipt_number} — {who}",
        lines=[ledger.dr(BANK, amount, scheme_id=receipt.scheme_id), ledger.cr(ledger.UNALLOCATED, amount, scheme_id=receipt.scheme_id)],
        user=checker,
    )
    receipt.journal_entry_id = entry.id
    receipt.status, receipt.confirmed_by_user_id, receipt.confirmed_at = ReceiptStatus.confirmed, checker.id, utcnow()
    audit.record(db, checker.id, "contribution_receipt", receipt.id, "confirmed",
                 after={"receipt_number": receipt.receipt_number, "amount": amount, "journal": ledger.entry_ref(entry)}, fund_id=fund.id)
    if scheme is not None:
        _notify_officers(db, scheme, receipt)


def _notify_officers(db: Session, scheme: Scheme, receipt: ContributionReceipt) -> None:
    for officer in scheme.officers:
        notifications._notify(db, officer.user, "receipt.confirmed", f"Payment received — receipt {receipt.receipt_number}",
                              f"We have received {money_label(receipt.amount)} from {scheme.name} (value date {receipt.value_date:%d %b %Y}).",
                              link=f"/po/remittances/{receipt.id}", entity_type="contribution_receipt", entity_id=receipt.id)


def _reject_confirm(db: Session, request: ApprovalRequest, user: User) -> None:
    receipt = db.get(ContributionReceipt, uuid.UUID(request.entity_id))
    if receipt is None or receipt.status != ReceiptStatus.pending_approval:
        return
    # A notice goes back to waiting for confirmation; a staff capture ends here.
    if receipt.source == ReceiptSource.portal_notice:
        receipt.status = ReceiptStatus.notified
        receipt.amount = receipt.value_date = receipt.bank_account_id = receipt.bank_reference = None
    else:
        # Only the maker can withdraw a request; a checker's decision is a rejection.
        receipt.status = ReceiptStatus.cancelled if user.id == request.initiated_by_user_id else ReceiptStatus.rejected
    receipt.approval_request_id = None


approvals.register(approvals.ApprovalKind(
    name=CONFIRM_KIND, label="Confirm contribution receipt", checker_roles=CHECKERS, apply=_apply_confirm, on_reject=_reject_confirm,
))


# ---- unidentified money


def propose_identification(db: Session, user: User, receipt: ContributionReceipt, scheme_id: uuid.UUID, note: str | None) -> ApprovalRequest:
    if receipt.status != ReceiptStatus.confirmed or receipt.scheme_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only confirmed, unidentified money can be placed with an employer")
    fund = db.get(Fund, receipt.fund_id)
    scheme = _scheme(db, fund, scheme_id, required=True)
    request = approvals.submit(
        db, user, IDENTIFY_KIND, entity_type="contribution_receipt", entity_id=receipt.id,
        summary=f"Place unidentified receipt {receipt.receipt_number} ({money_label(receipt.amount)}) with {scheme.code} — {scheme.name}",
        payload={"receipt": receipt.receipt_number, "amount": receipt.amount, "employer": f"{scheme.code} — {scheme.name}",
                 "note": (note or "").strip() or None, "_scheme_id": str(scheme.id)},
        previous={"employer": "Unidentified"}, fund_id=fund.id,
    )
    db.commit()
    db.refresh(request)
    return request


def _apply_identify(db: Session, request: ApprovalRequest, checker: User) -> None:
    receipt = db.execute(select(ContributionReceipt).where(ContributionReceipt.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one()
    if receipt.status != ReceiptStatus.confirmed or receipt.scheme_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This receipt has already been placed with an employer")
    fund = db.get(Fund, receipt.fund_id)
    scheme = _scheme(db, fund, uuid.UUID(request.payload["_scheme_id"]), required=True)
    amount = receipt.amount - receipt.allocated_amount
    # Reclassify within suspense: from "unidentified" to the employer.
    ledger.post(db, fund.id, entity_type="contribution_receipt", entity_id=receipt.id, entry_date=posting_date(db, fund.id, today()),
                description=f"Receipt {receipt.receipt_number} identified as {scheme.name}",
                lines=[ledger.dr(ledger.UNALLOCATED, amount), ledger.cr(ledger.UNALLOCATED, amount, scheme_id=scheme.id)], user=checker)
    receipt.scheme_id = scheme.id
    audit.record(db, checker.id, "contribution_receipt", receipt.id, "identified", after={"employer": scheme.code}, fund_id=fund.id)
    _notify_officers(db, scheme, receipt)


approvals.register(approvals.ApprovalKind(
    name=IDENTIFY_KIND, label="Identify unallocated receipt", checker_roles=CHECKERS, apply=_apply_identify,
))


# ---- suspense ageing


AGEING_BUCKETS = ((0, 30, "0–30 days"), (31, 60, "31–60 days"), (61, 90, "61–90 days"), (91, None, "Over 90 days"))


def unallocated_ageing(db: Session, fund_id: uuid.UUID, as_at: date | None = None) -> list[dict]:
    """Unallocated money (confirmed receipts not yet allocated) aged from the value date."""
    as_at = as_at or today()
    rows = db.execute(select(ContributionReceipt).where(
        ContributionReceipt.fund_id == fund_id, ContributionReceipt.status == ReceiptStatus.confirmed,
        ContributionReceipt.amount > ContributionReceipt.allocated_amount,
    )).scalars().all()
    out = [{"label": label, "count": 0, "amount": Decimal("0.00")} for _, _, label in AGEING_BUCKETS]
    for r in rows:
        days = (as_at - r.value_date).days
        i = next(i for i, (lo, hi, _) in enumerate(AGEING_BUCKETS) if days >= lo and (hi is None or days <= hi)) if days >= 0 else 0
        out[i]["count"] += 1
        out[i]["amount"] += r.unallocated
    return out
