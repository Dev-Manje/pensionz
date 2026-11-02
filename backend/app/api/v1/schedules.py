import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import _name, to_out
from app.core.database import get_db
from app.models.contribution import ContributionAllocation, ContributionReceipt, ContributionSchedule, ScheduleSource, ScheduleStatus
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.identity import User
from app.models.scheme import Scheme
from app.schemas.approval import ApprovalOut
from app.schemas.contribution import (
    AllocateIn, AllocationOut, AllocationPreviewOut, CandidateReceiptOut, FeeLineOut, ReverseIn,
    ScheduleCreateIn, ScheduleLineIn, ScheduleLineOut, ScheduleOut, SchedulePage, ScheduleSummaryOut,
)
from app.services import allocations, fund_access
from app.services import schedules as service
from app.services.io import contribution_schedule as io_schedule

router = APIRouter(tags=["schedules"])

maker = require_roles(*service.MAKERS)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def get_schedule(db: Session, user: User, schedule_id: uuid.UUID) -> ContributionSchedule:
    schedule = db.get(ContributionSchedule, schedule_id)
    if schedule is None or not fund_access.can_access(db, user, schedule.fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    return schedule


def _summary_values(db: Session, s: ContributionSchedule) -> dict:
    scheme = db.get(Scheme, s.scheme_id)
    return dict(
        id=s.id, fund_id=s.fund_id, scheme_id=s.scheme_id, employer=f"{scheme.code} — {scheme.name}", contribution_month=s.contribution_month,
        supplementary=s.supplementary, reference=s.reference, status=s.status, source=s.source, filename=s.filename,
        total_employee=s.total_employee, total_employer=s.total_employer, total_voluntary=s.total_voluntary, total_severance=s.total_severance,
        total=s.total, line_count=s.line_count, error_count=s.error_count, warning_count=s.warning_count,
        created_by=_name(db, s.created_by_user_id), created_at=s.created_at, submitted_by=_name(db, s.submitted_by_user_id),
        submitted_at=s.submitted_at,
    )


def schedule_out(db: Session, s: ContributionSchedule, user: User) -> ScheduleOut:
    return ScheduleOut(
        **_summary_values(db, s), notes=s.notes, lines=[ScheduleLineOut.model_validate(l) for l in s.lines],
        can_edit=s.status == ScheduleStatus.draft and user.has_any_role(*service.MAKERS),
    )


def _line_values(p: ScheduleLineIn) -> service.LineValues:
    return service.LineValues(p.account_code, p.employee_no, p.member_name, p.pensionable_salary, p.employee, p.employer, p.voluntary, p.severance)


@router.get("/funds/{fund_id}/schedules", response_model=SchedulePage)
def list_schedules(
    fund_id: uuid.UUID, scheme_id: uuid.UUID | None = None, month: date | None = None,
    status_filter: ScheduleStatus | None = Query(None, alias="status"), page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db), user: User = Depends(require_staff),
) -> SchedulePage:
    fund = fund_access.require_fund_access(db, user, fund_id)
    query = select(ContributionSchedule).where(ContributionSchedule.fund_id == fund.id)
    if scheme_id:
        query = query.where(ContributionSchedule.scheme_id == scheme_id)
    if month:
        query = query.where(ContributionSchedule.contribution_month == month.replace(day=1))
    if status_filter:
        query = query.where(ContributionSchedule.status == status_filter)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar()
    rows = db.execute(query.order_by(ContributionSchedule.contribution_month.desc(), ContributionSchedule.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return SchedulePage(items=[ScheduleSummaryOut(**_summary_values(db, s)) for s in rows], total=total)


@router.get("/funds/{fund_id}/schedules/template")
def template(fund_id: uuid.UUID, scheme_id: uuid.UUID, month: date, db: Session = Depends(get_db),
             user: User = Depends(require_staff)) -> Response:
    """The schedule workbook, prefilled with the employer's active members and expected contributions."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    filename, content = service.template_for(db, fund, scheme_id, month)
    return Response(content=content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/funds/{fund_id}/schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create(fund_id: uuid.UUID, payload: ScheduleCreateIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ScheduleOut:
    """Starts a draft schedule to capture by hand (prefilled with expected members unless `prefill` is false)."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    s = service.create(db, user, fund, payload.scheme_id, payload.contribution_month, supplementary=payload.supplementary,
                       source=ScheduleSource.manual, notes=payload.notes, prefill=payload.prefill)
    return schedule_out(db, s, user)


@router.post("/funds/{fund_id}/schedules/upload", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
async def upload_new(
    fund_id: uuid.UUID, scheme_id: uuid.UUID = Form(...), contribution_month: date = Form(...), supplementary: bool = Form(False),
    file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(maker),
) -> ScheduleOut:
    """Creates a draft from an uploaded schedule file."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    content = await file.read()
    # Check the file can be read before a draft exists, so a bad file leaves nothing behind.
    io_schedule.read(file.filename or "", content)
    s = service.create(db, user, fund, scheme_id, contribution_month, supplementary=supplementary, source=ScheduleSource.upload)
    return schedule_out(db, service.upload(db, user, s, file.filename or "schedule.xlsx", content), user)


@router.get("/schedules/{schedule_id}", response_model=ScheduleOut)
def get_one(schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> ScheduleOut:
    return schedule_out(db, get_schedule(db, user, schedule_id), user)


@router.post("/schedules/{schedule_id}/upload", response_model=ScheduleOut)
async def upload_replace(schedule_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
                         user: User = Depends(maker)) -> ScheduleOut:
    """Replaces a draft's lines with a corrected file."""
    s = get_schedule(db, user, schedule_id)
    content = await file.read()
    return schedule_out(db, service.upload(db, user, s, file.filename or "schedule.xlsx", content), user)


@router.post("/schedules/{schedule_id}/fill-expected", response_model=ScheduleOut)
def fill_expected(schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(maker)) -> ScheduleOut:
    return schedule_out(db, service.fill_expected(db, get_schedule(db, user, schedule_id)), user)


@router.post("/schedules/{schedule_id}/lines", response_model=ScheduleOut)
def add_line(schedule_id: uuid.UUID, payload: ScheduleLineIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ScheduleOut:
    return schedule_out(db, service.add_line(db, get_schedule(db, user, schedule_id), _line_values(payload)), user)


@router.put("/schedules/{schedule_id}/lines/{line_id}", response_model=ScheduleOut)
def update_line(schedule_id: uuid.UUID, line_id: uuid.UUID, payload: ScheduleLineIn, db: Session = Depends(get_db),
                user: User = Depends(maker)) -> ScheduleOut:
    return schedule_out(db, service.update_line(db, get_schedule(db, user, schedule_id), line_id, _line_values(payload)), user)


@router.delete("/schedules/{schedule_id}/lines/{line_id}", response_model=ScheduleOut)
def remove_line(schedule_id: uuid.UUID, line_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(maker)) -> ScheduleOut:
    return schedule_out(db, service.remove_line(db, get_schedule(db, user, schedule_id), line_id), user)


@router.post("/schedules/{schedule_id}/submit", response_model=ScheduleOut)
def submit(schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(maker)) -> ScheduleOut:
    """Hands a draft without errors over for allocation."""
    return schedule_out(db, service.submit(db, user, get_schedule(db, user, schedule_id)), user)


@router.post("/schedules/{schedule_id}/reopen", response_model=ScheduleOut)
def reopen(schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(maker)) -> ScheduleOut:
    return schedule_out(db, service.reopen(db, user, get_schedule(db, user, schedule_id)), user)


@router.post("/schedules/{schedule_id}/cancel", response_model=ScheduleOut)
def cancel(schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(maker)) -> ScheduleOut:
    return schedule_out(db, service.cancel(db, user, get_schedule(db, user, schedule_id)), user)


# ---- allocation (FR-CON-005, FR-CON-006)


def _allocation_out(db: Session, a: ContributionAllocation) -> AllocationOut:
    from app.models.ledger import JournalEntry
    from app.services import ledger

    entry = db.get(JournalEntry, a.journal_entry_id) if a.journal_entry_id else None
    numbers = []
    for part in a.receipts:
        r = db.get(ContributionReceipt, part.receipt_id)
        numbers.append(f"{r.receipt_number} · MWK {part.amount:,.2f}")
    return AllocationOut(id=a.id, status=a.status.value, amount=a.amount, net_to_members=a.net_to_members,
                         journal_reference=ledger.entry_ref(entry) if entry else None, approval_request_id=a.approval_request_id,
                         created_by=_name(db, a.created_by_user_id), approved_by=_name(db, a.approved_by_user_id), posted_at=a.posted_at,
                         receipts=numbers)


@router.get("/schedules/{schedule_id}/allocation", response_model=AllocationPreviewOut)
def allocation_preview(schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> AllocationPreviewOut:
    """What allocating the schedule takes: fees by payer, money needed, the employer's receipts with money left."""
    s = get_schedule(db, user, schedule_id)
    plan = allocations.plan_for(db, s)
    candidates = allocations.candidate_receipts(db, s)
    suggested = dict(allocations.auto_pick(candidates, plan.needed))
    available_total = sum((a for _, a in candidates), Decimal("0"))
    blocker = None
    live = allocations.live_allocation(db, s.id)
    if s.status == ScheduleStatus.draft:
        blocker = "Submit the schedule for allocation first."
    elif s.status != ScheduleStatus.ready:
        blocker = None if s.status == ScheduleStatus.allocated else "This schedule can't be allocated."
    elif live is not None:
        blocker = "An allocation is waiting for a contributions checker."
    elif available_total < plan.needed:
        blocker = (f"Hold: the employer's confirmed receipts have MWK {available_total:,.2f} available but the schedule needs "
                   f"MWK {plan.needed:,.2f}. Allocate once the rest is received and confirmed.")
    history = db.execute(select(ContributionAllocation).where(ContributionAllocation.schedule_id == s.id)
                         .order_by(ContributionAllocation.created_at.desc())).scalars().all()
    return AllocationPreviewOut(
        schedule_total=plan.schedule_total, member_fees=plan.member_fees, employer_fees=plan.employer_fees, needed=plan.needed,
        net_to_members=plan.net_to_members, fees=[FeeLineOut(**f.__dict__) for f in plan.fees],
        candidates=[CandidateReceiptOut(receipt_id=r.id, receipt_number=r.receipt_number, value_date=r.value_date, amount=r.amount,
                                        available=a, suggested=suggested.get(r.id, Decimal("0"))) for r, a in candidates],
        available_total=available_total, blocker=blocker, allocations=[_allocation_out(db, a) for a in history],
        pending_reversal_approval_id=db.execute(select(ApprovalRequest.id).where(
            ApprovalRequest.kind == allocations.REVERSAL_KIND, ApprovalRequest.entity_id == str(live.id),
            ApprovalRequest.status == ApprovalStatus.pending)).scalar() if live is not None else None,
    )


@router.post("/schedules/{schedule_id}/allocate", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def allocate(schedule_id: uuid.UUID, payload: AllocateIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Sends the allocation to a contributions checker; receipts must cover the schedule exactly."""
    s = get_schedule(db, user, schedule_id)
    picks = [(p.receipt_id, p.amount) for p in payload.receipts] if payload.receipts is not None else None
    return to_out(db, allocations.propose(db, user, s, picks), user)


@router.post("/schedules/{schedule_id}/reverse-allocation", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def reverse_allocation(schedule_id: uuid.UUID, payload: ReverseIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Asks to reverse the posted allocation (FR-CON-007); a contributions checker approves."""
    s = get_schedule(db, user, schedule_id)
    return to_out(db, allocations.propose_reversal(db, user, s, payload.reason), user)
