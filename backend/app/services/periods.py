"""Processing month per fund (FR-CFG-002).

- `require_open(db, fund_id, on_date)` is the guard every posting calls: the
  date must fall in the fund's open month, else 409.
- Finance opens a fund's first month, then closes months one at a time; a
  close runs the month-end checklist and opens the next month.
- Re-opening is maker-checker (kind "period_reopen", finance → finance
  checker) and only for the latest closed month; the month after it, opened
  automatically at close, is removed again provided nothing has posted to it.
"""
import uuid
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.fund import Fund
from app.models.identity import User, UserRole
from app.models.mixins import utcnow
from app.models.period import FundPeriod, PeriodStatus
from app.services import approvals, audit

REOPEN_KIND = "period_reopen"


def month_start(d: date) -> date:
    return d.replace(day=1)


def next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def label(d: date) -> str:
    return d.strftime("%b %Y")


def current(db: Session, fund_id: uuid.UUID) -> FundPeriod | None:
    return db.execute(
        select(FundPeriod).where(FundPeriod.fund_id == fund_id, FundPeriod.status == PeriodStatus.open)
    ).scalar_one_or_none()


def history(db: Session, fund_id: uuid.UUID) -> list[FundPeriod]:
    return list(db.execute(select(FundPeriod).where(FundPeriod.fund_id == fund_id).order_by(FundPeriod.period.desc())).scalars())


def require_open(db: Session, fund_id: uuid.UUID, on_date: date) -> FundPeriod:
    """The guard for every posting: `on_date` must be in the fund's open month."""
    period = current(db, fund_id)
    if period is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This fund has no open processing month yet")
    if month_start(on_date) != period.period:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{label(month_start(on_date))} isn't open for this fund — the processing month is {label(period.period)}",
        )
    return period


def has_postings(db: Session, fund_id: uuid.UUID, period: date) -> bool:
    from app.services import ledger

    return ledger.has_postings(db, fund_id, period)


# ---- month-end checklist (FR-ACC-006 fills these in as each area is built)

@dataclass
class Check:
    key: str
    label: str
    # passed | failed | not_available (the area isn't built yet, so it can't block a close)
    status: str
    detail: str | None = None


def _ledger_check(db: Session, fund: Fund) -> Check:
    from app.services import ledger

    t = ledger.tie_out(db, fund.id)
    name = "Fund ledger balanced and ties to member accounts"
    if not t.balanced:
        return Check("ledger_balanced", name, "failed", f"Debits {t.debits:,.2f} ≠ credits {t.credits:,.2f}")
    if not t.ties:
        return Check("ledger_balanced", name, "failed",
                     f"Member credits GL {t.member_credits_gl:,.2f} ≠ member accounts {t.member_sub_ledger:,.2f}")
    return Check("ledger_balanced", name, "passed", f"Member accounts {t.member_sub_ledger:,.2f} = GL 2000")


def checklist(db: Session, fund: Fund, period: FundPeriod) -> list[Check]:
    later = "Checked automatically once this part of the system is built."
    return [
        Check("schedules_allocated", "Contribution schedules for the month allocated", "not_available", later),
        Check("unallocated_cleared", "Unallocated receipts cleared or explained", "not_available", later),
        Check("bonus_posted", "Bonus / unit pricing for the month posted", "not_available", later),
        Check("bank_reconciled", "Fund bank accounts reconciled", "not_available", later),
        _ledger_check(db, fund),
    ]


# ---- actions


def open_first(db: Session, user: User, fund: Fund, period: date) -> FundPeriod:
    if db.execute(select(FundPeriod.id).where(FundPeriod.fund_id == fund.id)).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This fund already has processing months — close the open one to move on")
    row = FundPeriod(fund_id=fund.id, period=month_start(period), status=PeriodStatus.open,
                     opened_at=utcnow(), opened_by_user_id=user.id)
    db.add(row)
    db.flush()
    audit.record(db, user.id, "fund_period", row.id, "opened", after={"period": row.period}, fund_id=fund.id)
    db.commit()
    db.refresh(row)
    return row


def close(db: Session, user: User, fund: Fund, expected_period: date) -> FundPeriod:
    """Closes the open month and opens the next. `expected_period` guards
    against closing a different month than the one the user was looking at."""
    period = db.execute(
        select(FundPeriod).where(FundPeriod.fund_id == fund.id, FundPeriod.status == PeriodStatus.open).with_for_update()
    ).scalar_one_or_none()
    if period is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This fund has no open processing month")
    if period.period != month_start(expected_period):
        raise HTTPException(status.HTTP_409_CONFLICT, f"The open month is now {label(period.period)} — refresh and check again")
    failed = [c.label for c in checklist(db, fund, period) if c.status == "failed"]
    if failed:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Can't close {label(period.period)} yet: {'; '.join(failed)}")
    period.status = PeriodStatus.closed
    period.closed_at = utcnow()
    period.closed_by_user_id = user.id
    db.flush()
    following = next_month(period.period)
    nxt = db.execute(select(FundPeriod).where(FundPeriod.fund_id == fund.id, FundPeriod.period == following)).scalar_one_or_none()
    if nxt is None:
        nxt = FundPeriod(fund_id=fund.id, period=following)
        db.add(nxt)
    nxt.status, nxt.opened_at, nxt.opened_by_user_id = PeriodStatus.open, utcnow(), user.id
    nxt.closed_at = nxt.closed_by_user_id = None
    db.flush()
    audit.record(db, user.id, "fund_period", period.id, "closed", after={"period": period.period, "next": following}, fund_id=fund.id)
    db.commit()
    db.refresh(nxt)
    return nxt


def pending_reopen_id(db: Session, fund_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(ApprovalRequest.id).where(
            ApprovalRequest.kind == REOPEN_KIND, ApprovalRequest.fund_id == fund_id, ApprovalRequest.status == ApprovalStatus.pending,
        )
    ).scalars().first()


def _latest_closed(db: Session, fund_id: uuid.UUID) -> FundPeriod | None:
    return db.execute(
        select(FundPeriod).where(FundPeriod.fund_id == fund_id, FundPeriod.status == PeriodStatus.closed)
        .order_by(FundPeriod.period.desc()).limit(1)
    ).scalar_one_or_none()


def propose_reopen(db: Session, maker: User, fund: Fund, period_id: uuid.UUID, reason: str) -> ApprovalRequest:
    if not reason or len(reason.strip()) < 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say why the month has to be re-opened")
    period = db.get(FundPeriod, period_id)
    if period is None or period.fund_id != fund.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Processing month not found")
    latest = _latest_closed(db, fund.id)
    if period.status != PeriodStatus.closed or latest is None or latest.id != period.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only the most recently closed month can be re-opened")
    if pending_reopen_id(db, fund.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A re-open request for this fund is already waiting for approval")
    open_now = current(db, fund.id)
    request = approvals.submit(
        db, maker, REOPEN_KIND, entity_type="fund_period", entity_id=period.id,
        summary=f"Re-open {label(period.period)} for fund {fund.code}",
        payload={"fund": fund.code, "processing_month": label(period.period), "reason": reason.strip()},
        previous={"processing_month": label(open_now.period) if open_now else None},
        fund_id=fund.id,
    )
    db.commit()
    db.refresh(request)
    return request


def _apply_reopen(db: Session, request: ApprovalRequest, checker: User) -> None:
    period = db.execute(select(FundPeriod).where(FundPeriod.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one_or_none()
    if period is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That processing month no longer exists")
    latest = _latest_closed(db, period.fund_id)
    if period.status != PeriodStatus.closed or latest is None or latest.id != period.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "A later month has been closed since this was requested — ask again")
    open_now = current(db, period.fund_id)
    if open_now is not None:
        if has_postings(db, period.fund_id, open_now.period):
            raise HTTPException(status.HTTP_409_CONFLICT, f"{label(open_now.period)} already has transactions, so {label(period.period)} can't be re-opened")
        audit.record(db, checker.id, "fund_period", open_now.id, "withdrawn", before={"period": open_now.period}, fund_id=period.fund_id)
        db.delete(open_now)
        db.flush()
    period.status = PeriodStatus.open
    period.closed_at = period.closed_by_user_id = None
    period.opened_at, period.opened_by_user_id = utcnow(), checker.id
    db.flush()
    audit.record(db, checker.id, "fund_period", period.id, "reopened",
                 after={"period": period.period, "reason": request.payload.get("reason")}, fund_id=period.fund_id)


approvals.register(approvals.ApprovalKind(
    name=REOPEN_KIND, label="Re-open processing month", checker_roles=frozenset({UserRole.finance_checker}), apply=_apply_reopen,
))
