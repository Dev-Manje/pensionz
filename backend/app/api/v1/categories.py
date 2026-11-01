import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import to_out
from app.core.database import get_db
from app.models.category import BenefitCategory, BenefitCategoryTerms
from app.models.fund import Fund
from app.models.identity import User, UserRole
from app.models.scheme import Scheme
from app.schemas.approval import ApprovalOut
from app.schemas.category import CategoryChangeIn, CategoryIn, CategoryOut, TermsOut
from app.services import categories as category_service
from app.services import fund_access

router = APIRouter(tags=["benefit categories"])

config_maker = require_roles(UserRole.scheme_config_maker)


def _terms(db: Session, t: BenefitCategoryTerms) -> TermsOut:
    return TermsOut(
        id=t.id, effective_from=t.effective_from, design=t.design,
        **{f: getattr(t, f) for f in category_service.TERM_FIELDS},
        default_investment_option=category_service.option_label(db, t.default_investment_option_id),
    )


def _out(db: Session, c: BenefitCategory) -> CategoryOut:
    today = date.today()
    current = next((t for t in c.terms if t.effective_from <= today), None)
    upcoming = [t for t in c.terms if t.effective_from > today]
    return CategoryOut(
        id=c.id, scheme_id=c.scheme_id, fund_id=c.fund_id, code=c.code, name=c.name, status=c.status,
        design=category_service.design_for(db.get(Fund, c.fund_id)),
        current=_terms(db, current) if current else None,
        upcoming=_terms(db, upcoming[-1]) if upcoming else None,
        history=[_terms(db, t) for t in c.terms],
        pending_approval_id=category_service.pending_request_id(db, c.id),
    )


def _scheme(db: Session, user: User, scheme_id: uuid.UUID) -> Scheme:
    scheme = db.get(Scheme, scheme_id)
    if scheme is None or not fund_access.can_access(db, user, scheme.fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employer not found")
    return scheme


def _category(db: Session, user: User, category_id: uuid.UUID) -> BenefitCategory:
    category = db.get(BenefitCategory, category_id)
    if category is None or not fund_access.can_access(db, user, category.fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


@router.get("/schemes/{scheme_id}/categories", response_model=list[CategoryOut])
def list_categories(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> list[CategoryOut]:
    scheme = _scheme(db, user, scheme_id)
    rows = db.execute(select(BenefitCategory).where(BenefitCategory.scheme_id == scheme.id).order_by(BenefitCategory.code)).scalars()
    return [_out(db, c) for c in rows]


@router.post("/schemes/{scheme_id}/categories", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def create_category(scheme_id: uuid.UUID, payload: CategoryIn, db: Session = Depends(get_db), maker: User = Depends(config_maker)) -> ApprovalOut:
    """Proposes a new category with its first terms; a scheme-setup checker approves it."""
    scheme = _scheme(db, maker, scheme_id)
    return to_out(db, category_service.propose_new(db, maker, scheme, payload.code, payload.name, payload.terms), maker)


@router.get("/categories/{category_id}", response_model=CategoryOut)
def get_category(category_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> CategoryOut:
    return _out(db, _category(db, user, category_id))


@router.put("/categories/{category_id}", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def change_category(category_id: uuid.UUID, payload: CategoryChangeIn, db: Session = Depends(get_db),
                    maker: User = Depends(config_maker)) -> ApprovalOut:
    """Proposes a rename / close and/or new terms from a later date; a checker approves."""
    category = _category(db, maker, category_id)
    return to_out(db, category_service.propose_change(db, maker, category, payload.name, payload.status, payload.terms), maker)
