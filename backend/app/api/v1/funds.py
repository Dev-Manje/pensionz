import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import to_out
from app.core.database import get_db
from app.models.fund import Fund, FundStatus
from app.models.identity import User, UserRole
from app.schemas.approval import ApprovalOut
from app.schemas.fund import BankAccountOut, FundIn, FundOut, FundSummaryOut, TrusteeOut
from app.services import fund_access, periods
from app.services import funds as fund_service

router = APIRouter(prefix="/funds", tags=["funds"])

config_maker = require_roles(UserRole.scheme_config_maker)
# Roles that work with the fund's full bank account numbers; others see them masked (FR-SEC-005).
BANK_DETAIL_ROLES = (UserRole.admin, UserRole.scheme_config_maker, UserRole.scheme_config_checker,
                     UserRole.finance, UserRole.finance_checker)


def _summary(db: Session, fund: Fund) -> dict:
    return {
        "id": fund.id,
        "code": fund.code,
        "name": fund.name,
        "fund_type": fund.fund_type,
        "status": fund.status,
        "trustee_count": sum(1 for t in fund.trustees if t.active),
        "bank_account_count": sum(1 for a in fund.bank_accounts if a.active),
        "pending_approval_id": fund_service.pending_request_id(db, fund.id),
        "current_period": open_period.period if (open_period := periods.current(db, fund.id)) else None,
    }


def _detail(db: Session, fund: Fund, viewer: User) -> FundOut:
    full_numbers = viewer.has_any_role(*BANK_DETAIL_ROLES)
    return FundOut(
        **_summary(db, fund),
        **{f: getattr(fund, f) for f in fund_service.FUND_FIELDS if f not in ("code", "name", "fund_type", "status")},
        trustees=[TrusteeOut.model_validate(t) for t in fund.trustees if t.active],
        bank_accounts=[
            BankAccountOut(
                id=a.id, bank_id=a.bank_id, bank_name=a.bank.name, branch_id=a.branch_id,
                branch_name=a.branch.name if a.branch else None, account_name=a.account_name,
                account_number=a.account_number if full_numbers else None,
                account_number_masked=fund_service.mask_account_number(a.account_number),
                currency=a.currency, purpose=a.purpose,
            )
            for a in fund.bank_accounts if a.active
        ],
        locked_fields=fund_service.locked_fields(db, fund),
        can_edit=viewer.has_role(UserRole.scheme_config_maker),
    )


@router.get("", response_model=list[FundSummaryOut])
def list_funds(q: str | None = None, fund_status: FundStatus | None = None,
               db: Session = Depends(get_db), user: User = Depends(require_staff)) -> list[FundSummaryOut]:
    """The funds the signed-in staff member administers (all, for admins and auditors)."""
    query = select(Fund).order_by(Fund.code)
    allowed = fund_access.fund_ids_for(db, user)
    if allowed is not None:
        query = query.where(Fund.id.in_(allowed))
    if fund_status is not None:
        query = query.where(Fund.status == fund_status)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(Fund.code).like(like), func.lower(Fund.name).like(like)))
    return [FundSummaryOut(**_summary(db, f)) for f in db.execute(query).scalars()]


@router.get("/{fund_id}", response_model=FundOut)
def get_fund(fund_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> FundOut:
    return _detail(db, fund_access.require_fund_access(db, user, fund_id), user)


@router.post("", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def create_fund(payload: FundIn, db: Session = Depends(get_db), maker: User = Depends(config_maker)) -> ApprovalOut:
    """Proposes a new fund; a scheme-setup checker approves it before it exists."""
    return to_out(db, fund_service.propose_new(db, maker, payload), maker)


@router.put("/{fund_id}", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def update_fund(fund_id: uuid.UUID, payload: FundIn, db: Session = Depends(get_db),
                maker: User = Depends(config_maker)) -> ApprovalOut:
    """Proposes the fund as it should be (details, trustees, bank accounts); a checker approves."""
    fund = fund_access.require_fund_access(db, maker, fund_id)
    return to_out(db, fund_service.propose_update(db, maker, fund, payload), maker)
