"""Principal officer portal — remitting contributions: schedules, payment notices,
proof of payment, receipts. Every route goes through the officer's employer links
(`services/remittances.require_*`); other employers' records are 404."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.schedules import _line_values, schedule_out
from app.core import storage
from app.core.database import get_db
from app.models.contribution import ContributionSchedule, ReceiptStatus
from app.models.fund import Fund, FundBankAccount
from app.models.identity import User, UserRole
from app.models.scheme import Scheme
from app.schemas.contribution import ScheduleLineIn, ScheduleOut
from app.schemas.portal import CodeIn, CodeSentOut, NoticeIn, PaymentDetailOut, RemittanceMonthOut, StartScheduleIn
from app.services import audit, portal, receipts, remittances, schedules
from app.services.io import receipt_document

router = APIRouter(prefix="/po", tags=["principal officer portal"])

officer_only = require_roles(UserRole.principal_officer)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _out(db: Session, s: ContributionSchedule, user: User) -> ScheduleOut:
    out = schedule_out(db, s, user)
    out.can_edit = remittances.editable(s)
    return out


def _editable(db: Session, user: User, schedule_id: uuid.UUID) -> ContributionSchedule:
    s = remittances.require_schedule(db, user, schedule_id)
    remittances.require_editable(s)
    return s


@router.get("/schemes/{scheme_id}/remittances", response_model=list[RemittanceMonthOut])
def history(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> list[dict]:
    """Month by month: the schedules sent and the payments made, with where each has got to."""
    return remittances.history(db, portal.require_officer_scheme(db, user, scheme_id), receipts.today())


@router.get("/schemes/{scheme_id}/schedules/template")
def template(scheme_id: uuid.UUID, month: date, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> Response:
    """The schedule spreadsheet for the month, prefilled with every active member at the expected amounts."""
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    name, content = schedules.template_for(db, db.get(Fund, scheme.fund_id), scheme.id, month)
    return Response(content=content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/schemes/{scheme_id}/schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def start(scheme_id: uuid.UUID, payload: StartScheduleIn, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ScheduleOut:
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    return _out(db, remittances.start(db, user, scheme, payload.contribution_month, payload.supplementary), user)


@router.get("/schedules/{schedule_id}", response_model=ScheduleOut)
def get_schedule(schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ScheduleOut:
    return _out(db, remittances.require_schedule(db, user, schedule_id), user)


@router.post("/schedules/{schedule_id}/upload", response_model=ScheduleOut)
async def upload(schedule_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
                 user: User = Depends(officer_only)) -> ScheduleOut:
    """Replaces the draft's rows with the uploaded spreadsheet; every row is checked."""
    s = _editable(db, user, schedule_id)
    content = await file.read()
    return _out(db, schedules.upload(db, user, s, file.filename or "schedule.xlsx", content), user)


@router.post("/schedules/{schedule_id}/fill-expected", response_model=ScheduleOut)
def fill_expected(schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ScheduleOut:
    return _out(db, schedules.fill_expected(db, _editable(db, user, schedule_id)), user)


@router.post("/schedules/{schedule_id}/lines", response_model=ScheduleOut)
def add_line(schedule_id: uuid.UUID, payload: ScheduleLineIn, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ScheduleOut:
    return _out(db, schedules.add_line(db, _editable(db, user, schedule_id), _line_values(payload)), user)


@router.put("/schedules/{schedule_id}/lines/{line_id}", response_model=ScheduleOut)
def update_line(schedule_id: uuid.UUID, line_id: uuid.UUID, payload: ScheduleLineIn, db: Session = Depends(get_db),
                user: User = Depends(officer_only)) -> ScheduleOut:
    return _out(db, schedules.update_line(db, _editable(db, user, schedule_id), line_id, _line_values(payload)), user)


@router.delete("/schedules/{schedule_id}/lines/{line_id}", response_model=ScheduleOut)
def remove_line(schedule_id: uuid.UUID, line_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ScheduleOut:
    return _out(db, schedules.remove_line(db, _editable(db, user, schedule_id), line_id), user)


@router.post("/remit-code", response_model=CodeSentOut, status_code=status.HTTP_202_ACCEPTED)
def remit_code(db: Session = Depends(get_db), user: User = Depends(officer_only)) -> CodeSentOut:
    """Emails a one-time code; sending a schedule or a payment notice needs it."""
    return CodeSentOut(sent_to=remittances.send_code(db, user))


@router.post("/schedules/{schedule_id}/submit", response_model=ScheduleOut)
def submit(schedule_id: uuid.UUID, payload: CodeIn, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ScheduleOut:
    """Sends the schedule to the administrator for allocation (one-time code needed)."""
    s = remittances.require_schedule(db, user, schedule_id)
    return _out(db, remittances.submit(db, user, s, payload.code), user)


@router.post("/schedules/{schedule_id}/cancel", response_model=ScheduleOut)
def cancel(schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ScheduleOut:
    """Throws away a draft started in the portal."""
    return _out(db, remittances.cancel(db, user, remittances.require_schedule(db, user, schedule_id)), user)


@router.post("/schemes/{scheme_id}/payment-notices", response_model=PaymentDetailOut, status_code=status.HTTP_201_CREATED)
def payment_notice(scheme_id: uuid.UUID, payload: NoticeIn, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    """Tells the administrator a payment was made — "received, pending confirmation" until the bank shows it."""
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    receipt = remittances.notice(db, user, scheme, amount=payload.amount, payment_date=payload.payment_date,
                                 payment_method=payload.payment_method, payer_reference=payload.payer_reference,
                                 contribution_month=payload.contribution_month, notes=payload.notes, code=payload.code)
    return remittances.payment_detail(db, receipt)


@router.get("/remittances/{receipt_id}", response_model=PaymentDetailOut)
def payment(receipt_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    return remittances.payment_detail(db, remittances.require_receipt(db, user, receipt_id))


@router.post("/remittances/{receipt_id}/proof", response_model=PaymentDetailOut)
async def add_proof(receipt_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
                    user: User = Depends(officer_only)) -> dict:
    """Attaches proof of payment (bank slip, transfer confirmation) to a notice not yet confirmed."""
    receipt = remittances.require_receipt(db, user, receipt_id)
    if receipt.notified_by_user_id is None or receipt.status != ReceiptStatus.notified:
        raise HTTPException(status.HTTP_409_CONFLICT, "Proof of payment can only be added to a notice that is waiting for confirmation")
    content = await file.read()
    return remittances.payment_detail(db, receipts.attach_proof(db, user, receipt, file.filename or "proof", content))


@router.get("/remittances/{receipt_id}/proof")
def proof(receipt_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> Response:
    receipt = remittances.require_receipt(db, user, receipt_id)
    if receipt.proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No proof of payment attached")
    safe = "".join(c for c in (receipt.proof_filename or "proof") if c.isalnum() or c in "._- ") or "proof"
    return Response(content=storage.download_file(receipt.proof_storage_key), media_type=receipt.proof_content_type,
                    headers={"Content-Disposition": f'inline; filename="{safe}"', "Cache-Control": "no-store"})


@router.get("/remittances/{receipt_id}/document")
def document(receipt_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> Response:
    """The official receipt once confirmed, or the acknowledgement of the notice before that (PDF)."""
    receipt = remittances.require_receipt(db, user, receipt_id)
    which = receipt_document.kind(receipt)
    if which is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "There's nothing to print for this payment")
    fund = db.get(Fund, receipt.fund_id)
    scheme = db.get(Scheme, receipt.scheme_id)
    account = db.get(FundBankAccount, receipt.bank_account_id) if receipt.bank_account_id and which == "receipt" else None
    content = receipt_document.render(fund, scheme, account, receipt, receipts.today())
    audit.record(db, user.id, "contribution_receipt", receipt.id, "document_printed", after={"kind": which}, fund_id=receipt.fund_id)
    db.commit()
    name = receipt.receipt_number if which == "receipt" else f"acknowledgement-{receipt.notice_number}"
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})
