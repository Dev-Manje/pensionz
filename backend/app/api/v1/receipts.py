import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import _name, to_out
from app.core import storage
from app.core.database import get_db
from app.models.contribution import ContributionReceipt, ReceiptStatus
from app.models.fund import Fund, FundBankAccount
from app.models.identity import User
from app.models.ledger import JournalEntry
from app.models.scheme import Scheme
from app.schemas.approval import ApprovalOut
from app.schemas.contribution import (
    AgeingBucketOut, DeclineIn, IdentifyIn, ReceiptCaptureIn, ReceiptConfirmIn, ReceiptOut, ReceiptPage,
)
from app.services import audit, fund_access, ledger
from app.services import receipts as service
from app.services.io import receipt_document

router = APIRouter(tags=["receipts"])

maker = require_roles(*service.MAKERS)


def get_receipt(db: Session, user: User, receipt_id: uuid.UUID) -> ContributionReceipt:
    receipt = db.get(ContributionReceipt, receipt_id)
    if receipt is None or not fund_access.can_access(db, user, receipt.fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found")
    return receipt


def receipt_out(db: Session, r: ContributionReceipt, user: User) -> ReceiptOut:
    fund = db.get(Fund, r.fund_id)
    scheme = db.get(Scheme, r.scheme_id) if r.scheme_id else None
    account = db.get(FundBankAccount, r.bank_account_id) if r.bank_account_id else None
    entry = db.get(JournalEntry, r.journal_entry_id) if r.journal_entry_id else None
    is_maker = user.has_any_role(*service.MAKERS)
    return ReceiptOut(
        id=r.id, fund_id=r.fund_id, fund_code=fund.code, scheme_id=r.scheme_id, employer=f"{scheme.code} — {scheme.name}" if scheme else None,
        status=r.status, source=r.source, receipt_number=r.receipt_number, notice_number=r.notice_number, payment_method=r.payment_method,
        notified_amount=r.notified_amount, amount=r.amount, allocated_amount=r.allocated_amount, unallocated=r.unallocated,
        payment_date=r.payment_date, value_date=r.value_date, bank_account_id=r.bank_account_id,
        bank_account=f"{account.bank.short_name or account.bank.name} · {account.account_name}" if account else None,
        payer_name=r.payer_name, payer_reference=r.payer_reference, bank_reference=r.bank_reference, contribution_month=r.contribution_month,
        notes=r.notes, has_proof=r.proof_storage_key is not None, proof_filename=r.proof_filename,
        notified_by=_name(db, r.notified_by_user_id), captured_by=_name(db, r.captured_by_user_id), confirmed_by=_name(db, r.confirmed_by_user_id),
        confirmed_at=r.confirmed_at, created_at=r.created_at, rejection_reason=r.rejection_reason, approval_request_id=r.approval_request_id,
        journal_reference=ledger.entry_ref(entry) if entry else None,
        can_confirm=is_maker and r.status == ReceiptStatus.notified,
        can_identify=is_maker and r.status == ReceiptStatus.confirmed and r.scheme_id is None,
        document_kind=receipt_document.kind(r),
    )


@router.get("/funds/{fund_id}/receipts", response_model=ReceiptPage)
def list_receipts(
    fund_id: uuid.UUID, status_filter: ReceiptStatus | None = Query(None, alias="status"), scheme_id: uuid.UUID | None = None,
    unidentified: bool = False, unallocated: bool = False, q: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db), user: User = Depends(require_staff),
) -> ReceiptPage:
    """Payment notices and receipts, newest first, with the unallocated (suspense) ageing."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    query = select(ContributionReceipt).where(ContributionReceipt.fund_id == fund.id)
    if status_filter:
        query = query.where(ContributionReceipt.status == status_filter)
    if scheme_id:
        query = query.where(ContributionReceipt.scheme_id == scheme_id)
    if unidentified:
        query = query.where(ContributionReceipt.status == ReceiptStatus.confirmed, ContributionReceipt.scheme_id.is_(None))
    if unallocated:
        query = query.where(ContributionReceipt.status == ReceiptStatus.confirmed,
                            ContributionReceipt.amount > ContributionReceipt.allocated_amount)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.where(or_(ContributionReceipt.receipt_number.ilike(like), ContributionReceipt.notice_number.ilike(like),
                                ContributionReceipt.payer_name.ilike(like), ContributionReceipt.payer_reference.ilike(like),
                                ContributionReceipt.bank_reference.ilike(like)))
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar()
    rows = db.execute(query.order_by(ContributionReceipt.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    waiting = db.execute(select(func.count()).where(ContributionReceipt.fund_id == fund.id,
                                                    ContributionReceipt.status == ReceiptStatus.notified)).scalar()
    return ReceiptPage(items=[receipt_out(db, r, user) for r in rows], total=total, notices_waiting=waiting,
                       unallocated_ageing=[AgeingBucketOut(**b) for b in service.unallocated_ageing(db, fund.id)])


@router.post("/funds/{fund_id}/receipts", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def capture_receipt(fund_id: uuid.UUID, payload: ReceiptCaptureIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Records money that is on the fund's bank statement; a contributions checker confirms it."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    values = service.ConfirmValues(amount=payload.amount, value_date=payload.value_date, bank_account_id=payload.bank_account_id,
                                   bank_reference=payload.bank_reference, scheme_id=payload.scheme_id,
                                   contribution_month=payload.contribution_month.replace(day=1) if payload.contribution_month else None,
                                   notes=payload.notes)
    _, request = service.capture(db, user, fund, payment_method=payload.payment_method, payment_date=payload.payment_date,
                                 payer_name=payload.payer_name, payer_reference=payload.payer_reference, values=values)
    return to_out(db, request, user)


@router.get("/receipts/{receipt_id}", response_model=ReceiptOut)
def get_one(receipt_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> ReceiptOut:
    return receipt_out(db, get_receipt(db, user, receipt_id), user)


@router.post("/receipts/{receipt_id}/confirm", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def confirm(receipt_id: uuid.UUID, payload: ReceiptConfirmIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Confirms a payment notice against the bank statement; a contributions checker approves."""
    receipt = get_receipt(db, user, receipt_id)
    values = service.ConfirmValues(amount=payload.amount, value_date=payload.value_date, bank_account_id=payload.bank_account_id,
                                   bank_reference=payload.bank_reference, scheme_id=None,
                                   contribution_month=payload.contribution_month.replace(day=1) if payload.contribution_month else None,
                                   notes=payload.notes)
    return to_out(db, service.propose_confirmation(db, user, receipt, values), user)


@router.post("/receipts/{receipt_id}/decline", response_model=ReceiptOut)
def decline(receipt_id: uuid.UUID, payload: DeclineIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ReceiptOut:
    """The notified money isn't on the statement; the principal officer is told why."""
    return receipt_out(db, service.decline(db, user, get_receipt(db, user, receipt_id), payload.reason), user)


@router.post("/receipts/{receipt_id}/identify", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def identify(receipt_id: uuid.UUID, payload: IdentifyIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Places unidentified money with an employer; a contributions checker approves."""
    receipt = get_receipt(db, user, receipt_id)
    return to_out(db, service.propose_identification(db, user, receipt, payload.scheme_id, payload.note), user)


@router.post("/receipts/{receipt_id}/proof", response_model=ReceiptOut)
async def upload_proof(receipt_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
                       user: User = Depends(maker)) -> ReceiptOut:
    receipt = get_receipt(db, user, receipt_id)
    content = await file.read()
    return receipt_out(db, service.attach_proof(db, user, receipt, file.filename or "proof", content), user)


@router.get("/receipts/{receipt_id}/proof")
def download_proof(receipt_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> Response:
    receipt = get_receipt(db, user, receipt_id)
    if receipt.proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No proof of payment attached")
    audit.record(db, user.id, "contribution_receipt", receipt.id, "proof_viewed", fund_id=receipt.fund_id)
    db.commit()
    safe = "".join(c for c in (receipt.proof_filename or "proof") if c.isalnum() or c in "._- ") or "proof"
    return Response(content=storage.download_file(receipt.proof_storage_key), media_type=receipt.proof_content_type,
                    headers={"Content-Disposition": f'inline; filename="{safe}"', "Cache-Control": "no-store"})


@router.get("/receipts/{receipt_id}/document")
def document(receipt_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> Response:
    """The official receipt (confirmed money) or the acknowledgement of a payment notice, as PDF (FR-CON-010)."""
    receipt = get_receipt(db, user, receipt_id)
    which = receipt_document.kind(receipt)
    if which is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "There's nothing to print for this receipt yet")
    fund = db.get(Fund, receipt.fund_id)
    scheme = db.get(Scheme, receipt.scheme_id) if receipt.scheme_id else None
    account = db.get(FundBankAccount, receipt.bank_account_id) if receipt.bank_account_id and which == "receipt" else None
    content = receipt_document.render(fund, scheme, account, receipt, service.today())
    audit.record(db, user.id, "contribution_receipt", receipt.id, "document_printed", after={"kind": which}, fund_id=receipt.fund_id)
    db.commit()
    name = receipt.receipt_number if which == "receipt" else f"acknowledgement-{receipt.notice_number}"
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})
