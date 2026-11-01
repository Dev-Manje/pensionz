from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import to_out
from app.core.database import get_db
from app.models.identity import User, UserRole
from app.models.regulatory import RegulatoryParameterVersion, TaxTable, TaxTableKind
from app.schemas.approval import ApprovalOut
from app.schemas.regulatory import (
    ParameterOut, ParameterVersionIn, ParameterVersionOut, TaxBandOut, TaxCalcOut, TaxTableIn, TaxTableOut, TaxTablesOut,
)
from app.services import config_resolver, regulatory

router = APIRouter(prefix="/regulatory", tags=["regulatory"])

config_maker = require_roles(UserRole.scheme_config_maker)


def _version(p: regulatory.Parameter, v: RegulatoryParameterVersion) -> ParameterVersionOut:
    return ParameterVersionOut(id=v.id, value=v.value, display=regulatory.format_value(p, v.value),
                               effective_from=v.effective_from, source=v.source)


def _parameter(db: Session, p: regulatory.Parameter, today: date) -> ParameterOut:
    rows = regulatory.versions(db, p.key)
    current = next((v for v in rows if v.effective_from <= today), None)
    upcoming = [v for v in rows if v.effective_from > today]
    return ParameterOut(
        key=p.key, label=p.label, unit=p.unit, group=p.group, help=p.help, minimum=p.minimum, maximum=p.maximum,
        current=_version(p, current) if current else None,
        upcoming=_version(p, upcoming[-1]) if upcoming else None,
        versions=[_version(p, v) for v in rows],
        pending_approval_id=regulatory.pending_parameter_request(db, p.key),
    )


def _table(t: TaxTable) -> TaxTableOut:
    bands = sorted(t.bands, key=lambda b: b.lower)
    return TaxTableOut(
        id=t.id, kind=t.kind, effective_from=t.effective_from, source=t.source,
        bands=[TaxBandOut(lower=b.lower, rate_pct=b.rate_pct, upper=bands[i + 1].lower if i + 1 < len(bands) else None)
               for i, b in enumerate(bands)],
    )


@router.get("/parameters", response_model=list[ParameterOut])
def list_parameters(db: Session = Depends(get_db), _: User = Depends(require_staff)) -> list[ParameterOut]:
    today = date.today()
    return [_parameter(db, p, today) for p in regulatory.PARAMETERS.values()]


@router.post("/parameters/{key}/versions", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def propose_parameter(key: str, payload: ParameterVersionIn, db: Session = Depends(get_db), maker: User = Depends(config_maker)) -> ApprovalOut:
    """Proposes a new value from a date; a scheme-setup checker approves it."""
    request = regulatory.propose_parameter(db, maker, key, payload.value, payload.effective_from, payload.source)
    return to_out(db, request, maker)


@router.get("/tax-tables/{kind}", response_model=TaxTablesOut)
def get_tax_tables(kind: TaxTableKind, db: Session = Depends(get_db), _: User = Depends(require_staff)) -> TaxTablesOut:
    today = date.today()
    rows = regulatory.tax_tables(db, kind)
    current = next((t for t in rows if t.effective_from <= today), None)
    upcoming = [t for t in rows if t.effective_from > today]
    return TaxTablesOut(
        kind=kind, label=regulatory.TAX_LABELS[kind],
        current=_table(current) if current else None,
        upcoming=_table(upcoming[-1]) if upcoming else None,
        versions=[_table(t) for t in rows],
        pending_approval_id=regulatory.pending_tax_request(db, kind),
    )


@router.post("/tax-tables/{kind}", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def propose_tax_table(kind: TaxTableKind, payload: TaxTableIn, db: Session = Depends(get_db), maker: User = Depends(config_maker)) -> ApprovalOut:
    """Proposes a new version of the table from a date; a scheme-setup checker approves it."""
    bands = sorted(((b.lower, b.rate_pct) for b in payload.bands), key=lambda b: b[0])
    return to_out(db, regulatory.propose_tax_table(db, maker, kind, payload.effective_from, payload.source, bands), maker)


@router.get("/tax-tables/{kind}/calculate", response_model=TaxCalcOut)
def calculate_tax(kind: TaxTableKind, amount: Decimal = Query(ge=0), as_of: date | None = None,
                  db: Session = Depends(get_db), _: User = Depends(require_staff)) -> TaxCalcOut:
    """Tax on `amount` under the table in force on `as_of` (default today)."""
    table = config_resolver.tax_table(db, kind, as_of or date.today())
    return TaxCalcOut(amount=amount, tax=config_resolver.tax_on(table, amount) if table else Decimal("0"),
                      table_effective_from=table.effective_from if table else None)
