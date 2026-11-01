from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.identity import User
from app.models.reference import Bank
from app.schemas.fund import BankOut, BranchOut

router = APIRouter(prefix="/reference", tags=["reference"])


@router.get("/banks", response_model=list[BankOut])
def list_banks(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[BankOut]:
    """Banks in use with their active branches — for any bank-account form, staff or portal."""
    banks = db.execute(select(Bank).where(Bank.active.is_(True)).order_by(Bank.sort_order, Bank.name)).scalars()
    return [
        BankOut(id=b.id, name=b.name, short_name=b.short_name, swift_code=b.swift_code,
                branches=[BranchOut.model_validate(br) for br in b.branches if br.active])
        for b in banks
    ]
