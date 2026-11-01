import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import to_out
from app.core.database import get_db
from app.models.identity import User, UserRole
from app.schemas.approval import ApprovalOut
from app.services import system_lists

router = APIRouter(prefix="/setup/lists", tags=["setup"])

config_maker = require_roles(UserRole.scheme_config_maker)


@router.get("")
def describe_lists(_: User = Depends(require_staff)) -> list[dict]:
    """The maintainable lists and their fields — drives the generic Setup screen."""
    return system_lists.describe()


@router.get("/{name}")
def list_rows(name: str, parent: uuid.UUID | None = None, db: Session = Depends(get_db), _: User = Depends(require_staff)) -> list[dict]:
    return system_lists.rows(db, system_lists.get_list(name), parent)


@router.post("/{name}", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def create_row(name: str, payload: dict = Body(...), db: Session = Depends(get_db), maker: User = Depends(config_maker)) -> ApprovalOut:
    """Proposes a new entry; a scheme-setup checker approves it."""
    return to_out(db, system_lists.propose(db, maker, system_lists.get_list(name), payload), maker)


@router.put("/{name}/{row_id}", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def update_row(name: str, row_id: uuid.UUID, payload: dict = Body(...), db: Session = Depends(get_db),
               maker: User = Depends(config_maker)) -> ApprovalOut:
    """Proposes a change (including retiring the entry); a scheme-setup checker approves it."""
    spec = system_lists.get_list(name)
    row = db.get(spec.model, row_id)
    if row is None or any(getattr(row, k) != v for k, v in spec.fixed.items()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{spec.label} not found")
    return to_out(db, system_lists.propose(db, maker, spec, payload, row), maker)
