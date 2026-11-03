"""Principal officer portal (/po in the app). Role gate: principal officer;
row gate: `services/portal.require_officer_scheme` for anything per employer."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models.identity import User, UserRole
from app.api.v1 import kyc as kyc_api
from app.schemas.kyc import ApplicationOut
from app.schemas.portal import OrganisationOut, PoDashboardOut, PortalSchemeOut
from app.services import audit, kyc, periods, portal, receipts
from app.services.io import employer_statements

router = APIRouter(prefix="/po", tags=["principal officer portal"])

officer_only = require_roles(UserRole.principal_officer)


@router.get("/schemes", response_model=list[PortalSchemeOut])
def my_schemes(db: Session = Depends(get_db), user: User = Depends(officer_only)) -> list[PortalSchemeOut]:
    """The employers this officer acts for, in every fund."""
    rows = portal.officer_schemes(db, user)
    counts = portal.member_counts(db, [s.id for s, _ in rows])
    return [PortalSchemeOut(**portal.scheme_row(s, f, counts.get(s.id, 0))) for s, f in rows]


@router.get("/dashboard", response_model=PoDashboardOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    """Per employer: this month's remittance, arrears totals; plus recent activity."""
    return portal.dashboard(db, user, receipts.today())


@router.get("/schemes/{scheme_id}/organisation", response_model=OrganisationOut)
def organisation(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    """The employer's approved KYC details, documents, review date and any application in progress."""
    return portal.organisation(db, portal.require_officer_scheme(db, user, scheme_id), kyc.today())


@router.post("/schemes/{scheme_id}/kyc", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def start_kyc(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ApplicationOut:
    """Starts the employer's KYC — or a change to approved details, prefilled from them. One at a time per employer."""
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    return kyc_api._out(db, kyc.start_for_scheme(db, user, scheme), user)


# ---- statements (PDF)

MAX_STATEMENT_MONTHS = 24


def _pdf(content: bytes, name: str) -> Response:
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


def _not_future(month: date) -> date:
    month = periods.month_start(month)
    if month > periods.month_start(receipts.today()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a month that has started")
    return month


@router.get("/schemes/{scheme_id}/statements/contributions")
def contribution_statement(scheme_id: uuid.UUID, from_month: date, to_month: date, db: Session = Depends(get_db),
                           user: User = Depends(officer_only)) -> Response:
    """Statement of contributions for the months from–to (at most 24)."""
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    first, last = _not_future(from_month), _not_future(to_month)
    if first > last:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The first month must be before the last")
    if (last.year - first.year) * 12 + last.month - first.month >= MAX_STATEMENT_MONTHS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Choose at most {MAX_STATEMENT_MONTHS} months")
    content = employer_statements.contribution_statement(db, scheme, first, last, receipts.today())
    audit.record(db, user.id, "scheme", scheme.id, "statement_downloaded", after={"kind": "contributions", "from": first, "to": last},
                 fund_id=scheme.fund_id)
    db.commit()
    return _pdf(content, f"contributions-{scheme.code}-{first:%Y%m}-{last:%Y%m}")


@router.get("/schemes/{scheme_id}/statements/invoice")
def invoice(scheme_id: uuid.UUID, month: date, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> Response:
    """What to pay for a month: expected contributions per member plus employer fees, due date and where to pay."""
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    month = _not_future(month)
    content = employer_statements.invoice(db, scheme, month, receipts.today())
    audit.record(db, user.id, "scheme", scheme.id, "statement_downloaded", after={"kind": "invoice", "month": month}, fund_id=scheme.fund_id)
    db.commit()
    return _pdf(content, f"invoice-{scheme.code}-{month:%Y%m}")


@router.get("/schemes/{scheme_id}/statements/arrears")
def arrears_statement(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> Response:
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    today = receipts.today()
    content = employer_statements.arrears_statement(db, scheme, today)
    audit.record(db, user.id, "scheme", scheme.id, "statement_downloaded", after={"kind": "arrears"}, fund_id=scheme.fund_id)
    db.commit()
    return _pdf(content, f"arrears-{scheme.code}-{today:%Y%m%d}")

