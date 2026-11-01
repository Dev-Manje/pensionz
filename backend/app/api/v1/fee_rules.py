import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import to_out
from app.core.database import get_db
from app.models.fee import FeeRule
from app.models.identity import User, UserRole
from app.schemas.approval import ApprovalOut
from app.schemas.fee import FeeRuleIn, FeeRuleOut
from app.services import fund_access
from app.services.fee_rules import RULES, employer_label

router = APIRouter(prefix="/funds/{fund_id}/fee-rules", tags=["fee rules"])

config_maker = require_roles(UserRole.scheme_config_maker)


def _out(db: Session, r: FeeRule) -> FeeRuleOut:
    return FeeRuleOut(
        id=r.id, fund_id=r.fund_id, code=r.code, name=r.name, scheme_id=r.scheme_id, employer=employer_label(db, r.scheme_id),
        fee_type=r.fee_type, basis=r.basis, rate=r.rate, payer=r.payer, frequency=r.frequency,
        effective_from=r.effective_from, effective_to=r.effective_to, pending_approval_id=RULES.pending_request_id(db, r.id),
    )


@router.get("", response_model=list[FeeRuleOut])
def list_rules(fund_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> list[FeeRuleOut]:
    fund = fund_access.require_fund_access(db, user, fund_id)
    return [_out(db, r) for r in RULES.rows(db, fund.id)]


@router.post("", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def create_rule(fund_id: uuid.UUID, payload: FeeRuleIn, db: Session = Depends(get_db), maker: User = Depends(config_maker)) -> ApprovalOut:
    fund = fund_access.require_fund_access(db, maker, fund_id)
    return to_out(db, RULES.propose_new(db, maker, fund, payload.model_dump()), maker)


@router.put("/{rule_id}", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def update_rule(fund_id: uuid.UUID, rule_id: uuid.UUID, payload: FeeRuleIn, db: Session = Depends(get_db),
                maker: User = Depends(config_maker)) -> ApprovalOut:
    fund = fund_access.require_fund_access(db, maker, fund_id)
    return to_out(db, RULES.propose_update(db, maker, fund, RULES.get(db, rule_id, fund.id), payload.model_dump()), maker)
