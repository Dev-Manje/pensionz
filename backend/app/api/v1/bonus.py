"""Declared bonus (FR-EAR-001…004) — see services/bonus.py."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import to_out
from app.core.database import get_db
from app.models.bonus import BonusDeclaration, BonusKind, BonusRun, BonusRunStatus
from app.models.identity import User
from app.models.ledger import Component
from app.models.member import Member
from app.schemas.approval import ApprovalOut
from app.services import bonus as svc
from app.services import fund_access

router = APIRouter(tags=["bonus"])
maker = require_roles(*svc.MAKERS)


class DeclarationIn(BaseModel):
    kind: BonusKind
    period_start: date
    period_end: date
    rate: Decimal = Field(ge=0, le=100)
    components: list[Component] | None = None
    resolution: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class RunIn(BaseModel):
    member_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    as_at: date | None = None
    posting_date: date | None = None


class ReversalIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)
    member_ids: list[uuid.UUID] | None = None


class RunSummaryOut(BaseModel):
    id: uuid.UUID
    reference: str
    kind: BonusKind
    status: BonusRunStatus
    member_count: int
    total_credit: Decimal
    total_debit: Decimal
    posting_date: date
    as_at: date | None
    posted_at: datetime | None
    created_at: datetime
    pending_approval_id: uuid.UUID | None = None


class DeclarationOut(BaseModel):
    id: uuid.UUID
    fund_id: uuid.UUID
    reference: str
    kind: BonusKind
    period_start: date
    period_end: date
    rate: Decimal
    components: list[str]
    resolution: str | None
    notes: str | None
    created_at: datetime
    runs: list[RunSummaryOut] = []


class RunLineOut(BaseModel):
    member_id: uuid.UUID
    account_code: str
    member_name: str
    component: Component
    to_date: date
    days: int
    opening_balance: Decimal
    opening_bonus: Decimal
    movements: Decimal
    movements_bonus: Decimal
    calculated: Decimal
    already_credited: Decimal
    amount: Decimal
    reversed: bool


class RunOut(RunSummaryOut):
    declaration: DeclarationOut
    fund_code: str
    lines: list[RunLineOut]
    entry_ref: str | None = None


def _run_summary(db: Session, r: BonusRun) -> RunSummaryOut:
    return RunSummaryOut(id=r.id, reference=r.reference, kind=r.kind, status=r.status, member_count=r.member_count,
                         total_credit=r.total_credit, total_debit=r.total_debit, posting_date=r.posting_date, as_at=r.as_at,
                         posted_at=r.posted_at, created_at=r.created_at, pending_approval_id=svc.pending_request_id(db, r))


def _declaration(db: Session, d: BonusDeclaration, with_runs: bool = True) -> DeclarationOut:
    return DeclarationOut(
        id=d.id, fund_id=d.fund_id, reference=d.reference, kind=d.kind, period_start=d.period_start, period_end=d.period_end,
        rate=d.rate, components=d.components, resolution=d.resolution, notes=d.notes, created_at=d.created_at,
        runs=[_run_summary(db, r) for r in svc.runs_for(db, d.id)] if with_runs else [],
    )


def _get_declaration(db: Session, user: User, declaration_id: uuid.UUID) -> BonusDeclaration:
    d = db.get(BonusDeclaration, declaration_id)
    if d is None or not fund_access.can_access(db, user, d.fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Declaration not found")
    return d


def _get_run(db: Session, user: User, run_id: uuid.UUID) -> BonusRun:
    r = db.get(BonusRun, run_id)
    if r is None or not fund_access.can_access(db, user, r.fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bonus run not found")
    return r


def _run_out(db: Session, r: BonusRun) -> RunOut:
    from app.models.fund import Fund
    from app.models.ledger import JournalEntry
    from app.services import ledger

    members = {m.id: m for m in db.execute(select(Member).where(Member.id.in_({l.member_id for l in r.lines}))).scalars()} if r.lines else {}
    entry = db.get(JournalEntry, r.journal_entry_id) if r.journal_entry_id else None
    return RunOut(
        **_run_summary(db, r).model_dump(), declaration=_declaration(db, db.get(BonusDeclaration, r.declaration_id), with_runs=False),
        fund_code=db.get(Fund, r.fund_id).code, entry_ref=ledger.entry_ref(entry) if entry else None,
        lines=[RunLineOut(
            member_id=l.member_id, account_code=members[l.member_id].account_code,
            member_name=f"{members[l.member_id].first_name} {members[l.member_id].last_name}", component=l.component,
            to_date=l.to_date, days=l.days, opening_balance=l.opening_balance, opening_bonus=l.opening_bonus, movements=l.movements,
            movements_bonus=l.movements_bonus, calculated=l.calculated, already_credited=l.already_credited, amount=l.amount,
            reversed=l.reversal_transaction_id is not None,
        ) for l in r.lines],
    )


@router.get("/funds/{fund_id}/bonus-declarations", response_model=list[DeclarationOut])
def list_declarations(fund_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> list[DeclarationOut]:
    fund = fund_access.require_fund_access(db, user, fund_id)
    return [_declaration(db, d) for d in svc.declarations(db, fund.id)]


@router.post("/funds/{fund_id}/bonus-declarations", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def declare(fund_id: uuid.UUID, payload: DeclarationIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Records the trustees' rate; a finance checker approves it."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    return to_out(db, svc.propose_declaration(db, user, fund, **payload.model_dump()), user)


@router.get("/bonus-declarations/{declaration_id}", response_model=DeclarationOut)
def get_declaration(declaration_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> DeclarationOut:
    return _declaration(db, _get_declaration(db, user, declaration_id))


@router.post("/bonus-declarations/{declaration_id}/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(declaration_id: uuid.UUID, payload: RunIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> RunOut:
    """Calculates a preview (nothing is posted until a checker approves it)."""
    run = svc.create_run(db, user, _get_declaration(db, user, declaration_id), **payload.model_dump())
    return _run_out(db, run)


@router.get("/bonus-runs/{run_id}", response_model=RunOut)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> RunOut:
    return _run_out(db, _get_run(db, user, run_id))


@router.post("/bonus-runs/{run_id}/recalculate", response_model=RunOut)
def recalculate(run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(maker)) -> RunOut:
    return _run_out(db, svc.recalculate(db, user, _get_run(db, user, run_id)))


@router.post("/bonus-runs/{run_id}/discard", response_model=RunOut)
def discard(run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(maker)) -> RunOut:
    return _run_out(db, svc.discard(db, user, _get_run(db, user, run_id)))


@router.post("/bonus-runs/{run_id}/submit", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def submit(run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    return to_out(db, svc.submit_run(db, user, _get_run(db, user, run_id)), user)


@router.post("/bonus-runs/{run_id}/reverse", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def reverse(run_id: uuid.UUID, payload: ReversalIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Reverses the whole run, or only the chosen members; a finance checker approves."""
    return to_out(db, svc.propose_reversal(db, user, _get_run(db, user, run_id), member_ids=payload.member_ids, reason=payload.reason), user)
