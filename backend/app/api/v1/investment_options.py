import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import to_out
from app.core.database import get_db
from app.models.identity import User, UserRole
from app.models.investment import InvestmentOption
from app.schemas.approval import ApprovalOut
from app.schemas.investment import InvestmentOptionIn, InvestmentOptionOut
from app.services import fund_access
from app.services.investment_options import OPTIONS

router = APIRouter(prefix="/funds/{fund_id}/investment-options", tags=["investment options"])

config_maker = require_roles(UserRole.scheme_config_maker)


def _out(db: Session, o: InvestmentOption) -> InvestmentOptionOut:
    return InvestmentOptionOut(
        id=o.id, fund_id=o.fund_id, code=o.code, name=o.name, pricing_method=o.pricing_method, status=o.status,
        launch_date=o.launch_date, description=o.description, pending_approval_id=OPTIONS.pending_request_id(db, o.id),
    )


@router.get("", response_model=list[InvestmentOptionOut])
def list_options(fund_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> list[InvestmentOptionOut]:
    fund = fund_access.require_fund_access(db, user, fund_id)
    return [_out(db, o) for o in OPTIONS.rows(db, fund.id)]


@router.post("", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def create_option(fund_id: uuid.UUID, payload: InvestmentOptionIn, db: Session = Depends(get_db), maker: User = Depends(config_maker)) -> ApprovalOut:
    fund = fund_access.require_fund_access(db, maker, fund_id)
    return to_out(db, OPTIONS.propose_new(db, maker, fund, payload.model_dump()), maker)


@router.put("/{option_id}", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def update_option(fund_id: uuid.UUID, option_id: uuid.UUID, payload: InvestmentOptionIn, db: Session = Depends(get_db),
                  maker: User = Depends(config_maker)) -> ApprovalOut:
    fund = fund_access.require_fund_access(db, maker, fund_id)
    row = OPTIONS.get(db, option_id, fund.id)
    return to_out(db, OPTIONS.propose_update(db, maker, fund, row, payload.model_dump()), maker)
