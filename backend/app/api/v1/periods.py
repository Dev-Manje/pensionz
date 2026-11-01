import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import _name, to_out
from app.core.database import get_db
from app.models.fund import Fund
from app.models.identity import User, UserRole
from app.models.period import FundPeriod, PeriodStatus
from app.schemas.approval import ApprovalOut
from app.schemas.period import CheckOut, CloseIn, OpenFirstIn, PeriodOut, PeriodsOut, ReopenIn
from app.services import fund_access, periods

router = APIRouter(prefix="/funds/{fund_id}/periods", tags=["periods"])

finance = require_roles(UserRole.finance)


def _out(db: Session, p: FundPeriod) -> PeriodOut:
    return PeriodOut(id=p.id, period=p.period, status=p.status, opened_at=p.opened_at, opened_by=_name(db, p.opened_by_user_id),
                     closed_at=p.closed_at, closed_by=_name(db, p.closed_by_user_id))


def _state(db: Session, fund: Fund, user: User) -> PeriodsOut:
    rows = periods.history(db, fund.id)
    open_now = next((p for p in rows if p.status == PeriodStatus.open), None)
    is_finance = user.has_role(UserRole.finance)
    pending = periods.pending_reopen_id(db, fund.id)
    return PeriodsOut(
        current=_out(db, open_now) if open_now else None,
        checklist=[CheckOut(**vars(c)) for c in periods.checklist(db, fund, open_now)] if open_now else [],
        history=[_out(db, p) for p in rows],
        pending_reopen_approval_id=pending,
        can_open_first=is_finance and not rows,
        can_close=is_finance and open_now is not None,
        can_request_reopen=is_finance and pending is None and any(p.status == PeriodStatus.closed for p in rows),
    )


@router.get("", response_model=PeriodsOut)
def get_periods(fund_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> PeriodsOut:
    return _state(db, fund_access.require_fund_access(db, user, fund_id), user)


@router.post("/open", response_model=PeriodsOut, status_code=status.HTTP_201_CREATED)
def open_first(fund_id: uuid.UUID, payload: OpenFirstIn, db: Session = Depends(get_db), user: User = Depends(finance)) -> PeriodsOut:
    """Opens the fund's first processing month (the month its records start)."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    periods.open_first(db, user, fund, payload.period)
    return _state(db, fund, user)


@router.post("/close", response_model=PeriodsOut)
def close(fund_id: uuid.UUID, payload: CloseIn, db: Session = Depends(get_db), user: User = Depends(finance)) -> PeriodsOut:
    """Closes the open month after the month-end checks pass, and opens the next."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    periods.close(db, user, fund, payload.period)
    return _state(db, fund, user)


@router.post("/{period_id}/reopen", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def reopen(fund_id: uuid.UUID, period_id: uuid.UUID, payload: ReopenIn, db: Session = Depends(get_db),
           user: User = Depends(finance)) -> ApprovalOut:
    """Asks to re-open the latest closed month; a finance checker approves."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    return to_out(db, periods.propose_reopen(db, user, fund, period_id, payload.reason), user)
