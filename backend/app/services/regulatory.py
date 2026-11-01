"""Regulatory parameters and tax tables (FR-CFG-009), maker-checker.

The known parameters are listed in PARAMETERS (what they mean, their unit and
allowed range). Changing one adds a version with an effective date — kind
"regulatory_parameter"; a new tax table version — kind "tax_table". Both are
proposed by a scheme-setup maker and approved by a scheme-setup checker.
Values resolve through services/config_resolver.py."""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.identity import User, UserRole
from app.models.regulatory import RegulatoryParameterVersion, TaxBand, TaxTable, TaxTableKind
from app.services import approvals, audit

PARAMETER_KIND = "regulatory_parameter"
TAX_KIND = "tax_table"


@dataclass(frozen=True)
class Parameter:
    key: str
    label: str
    # percent | years | months | age | money
    unit: str
    minimum: Decimal
    maximum: Decimal
    help: str
    group: str


_P = Decimal
PARAMETERS: dict[str, Parameter] = {p.key: p for p in [
    Parameter("min_employee_contribution_pct", "Minimum employee contribution", "percent", _P(0), _P(100),
              "Lowest employee rate a benefit category may set, as % of pensionable salary.", "Contributions"),
    Parameter("min_employer_contribution_pct", "Minimum employer contribution", "percent", _P(0), _P(100),
              "Lowest employer rate a benefit category may set, as % of pensionable salary.", "Contributions"),
    Parameter("late_payment_interest_pct", "Late-payment interest rate", "percent", _P(0), _P(100),
              "Annual interest charged to employers on contributions paid after the due day.", "Contributions"),
    Parameter("min_retirement_age", "Earliest retirement age", "age", _P(40), _P(75),
              "Youngest age at which retirement benefits may be paid.", "Retirement"),
    Parameter("max_retirement_age", "Latest retirement age", "age", _P(50), _P(80),
              "Age by which retirement benefits must start.", "Retirement"),
    Parameter("max_lump_sum_pct", "Maximum retirement lump sum", "percent", _P(0), _P(100),
              "Largest share of the retirement benefit that may be taken in cash; the rest buys a pension.", "Retirement"),
    Parameter("small_balance_threshold", "Small-balance threshold", "money", _P(0), _P("1000000000"),
              "If the residual after the lump sum is below this, the whole benefit may be paid in cash.", "Retirement"),
    Parameter("unemployment_access_wait_months", "Unemployment access waiting period", "months", _P(0), _P(24),
              "Months a member must be without work before they may access their savings.", "Early access"),
    Parameter("pre_retirement_access_years", "Pre-retirement access window", "years", _P(0), _P(20),
              "Years before normal retirement age in which early access is allowed.", "Early access"),
    Parameter("pre_retirement_access_max_pct", "Pre-retirement access limit", "percent", _P(0), _P(100),
              "Largest share of the balance that may be accessed within that window.", "Early access"),
]}

WHOLE_UNITS = {"years", "months", "age"}


def _day(d: date) -> str:
    """"1 Apr 2027" — the app's date style, without a leading zero."""
    return f"{d.day} {d:%b %Y}"


def get_parameter(key: str) -> Parameter:
    if key not in PARAMETERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown regulatory parameter")
    return PARAMETERS[key]


def versions(db: Session, key: str) -> list[RegulatoryParameterVersion]:
    return list(db.execute(
        select(RegulatoryParameterVersion).where(RegulatoryParameterVersion.key == key)
        .order_by(RegulatoryParameterVersion.effective_from.desc())
    ).scalars())


def pending_parameter_request(db: Session, key: str) -> uuid.UUID | None:
    return db.execute(
        select(ApprovalRequest.id).where(
            ApprovalRequest.kind == PARAMETER_KIND, ApprovalRequest.entity_id == key, ApprovalRequest.status == ApprovalStatus.pending,
        )
    ).scalar_one_or_none()


def format_value(p: Parameter, value: Decimal) -> str:
    if p.unit == "percent":
        return f"{value.normalize():f}%"
    if p.unit == "money":
        return f"MWK {value:,.2f}"
    return f"{int(value)} {'years' if p.unit == 'age' else p.unit}"


def propose_parameter(db: Session, maker: User, key: str, value: Decimal, effective_from: date, source: str | None) -> ApprovalRequest:
    p = get_parameter(key)
    if not (p.minimum <= value <= p.maximum):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{p.label} must be between {format_value(p, p.minimum)} and {format_value(p, p.maximum)}")
    if p.unit in WHOLE_UNITS and value != value.to_integral_value():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{p.label} must be a whole number of {p.unit}")
    if db.execute(select(RegulatoryParameterVersion.id).where(
        RegulatoryParameterVersion.key == key, RegulatoryParameterVersion.effective_from == effective_from
    )).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{p.label} already has a value from {_day(effective_from)}")
    from app.services.config_resolver import regulatory

    current = regulatory(db, key, effective_from)
    back_dated = effective_from < date.today()
    request = approvals.submit(
        db, maker, PARAMETER_KIND, entity_type="regulatory_parameter", entity_id=key,
        summary=f"{p.label}: {format_value(p, value)} from {_day(effective_from)}" + (" (back-dated)" if back_dated else ""),
        payload={"parameter": p.label, "value": format_value(p, value), "effective_from": effective_from,
                 "source": source, "_key": key, "_value": str(value)},
        previous={"parameter": p.label, "value": format_value(p, current) if current is not None else None},
    )
    db.commit()
    db.refresh(request)
    return request


def _apply_parameter(db: Session, request: ApprovalRequest, checker: User) -> None:
    data = request.payload
    effective_from = date.fromisoformat(data["effective_from"])
    if db.execute(select(RegulatoryParameterVersion.id).where(
        RegulatoryParameterVersion.key == data["_key"], RegulatoryParameterVersion.effective_from == effective_from
    )).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A value from that date was added in the meantime")
    row = RegulatoryParameterVersion(key=data["_key"], value=Decimal(data["_value"]), effective_from=effective_from,
                                     source=data.get("source"), approved_by_user_id=checker.id)
    db.add(row)
    db.flush()
    audit.record(db, checker.id, "regulatory_parameter", data["_key"], "version_added",
                 after={"value": data["_value"], "effective_from": effective_from, "source": data.get("source")})


# ---- tax tables

TAX_LABELS = {TaxTableKind.paye_monthly: "PAYE on pensions (monthly)", TaxTableKind.lump_sum: "Tax on lump sums"}


def tax_tables(db: Session, kind: TaxTableKind) -> list[TaxTable]:
    return list(db.execute(select(TaxTable).where(TaxTable.kind == kind).order_by(TaxTable.effective_from.desc())).scalars())


def pending_tax_request(db: Session, kind: TaxTableKind) -> uuid.UUID | None:
    return db.execute(
        select(ApprovalRequest.id).where(
            ApprovalRequest.kind == TAX_KIND, ApprovalRequest.entity_id == kind.value, ApprovalRequest.status == ApprovalStatus.pending,
        )
    ).scalar_one_or_none()


def band_lines(bands: list[tuple[Decimal, Decimal]]) -> list[str]:
    """Readable bands for the checker: "MWK 150,000.00 – 500,000.00 at 25%"."""
    lines = []
    for i, (lower, rate) in enumerate(bands):
        upper = bands[i + 1][0] if i + 1 < len(bands) else None
        span = f"MWK {lower:,.2f} – {upper:,.2f}" if upper is not None else f"Over MWK {lower:,.2f}"
        lines.append(f"{span} at {rate.normalize():f}%")
    return lines


def propose_tax_table(db: Session, maker: User, kind: TaxTableKind, effective_from: date, source: str | None,
                      bands: list[tuple[Decimal, Decimal]]) -> ApprovalRequest:
    if not bands:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add at least one band")
    if bands[0][0] != 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The first band must start at 0")
    if any(b[0] >= nxt[0] for b, nxt in zip(bands, bands[1:])):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Each band must start above the previous one")
    if any(not (0 <= rate <= 100) for _, rate in bands):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rates must be between 0% and 100%")
    if db.execute(select(TaxTable.id).where(TaxTable.kind == kind, TaxTable.effective_from == effective_from)).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"There is already a {TAX_LABELS[kind]} table from {_day(effective_from)}")
    from app.services.config_resolver import tax_table

    current = tax_table(db, kind, effective_from)
    request = approvals.submit(
        db, maker, TAX_KIND, entity_type="tax_table", entity_id=kind.value,
        summary=f"New {TAX_LABELS[kind]} table from {_day(effective_from)}",
        payload={"table": TAX_LABELS[kind], "effective_from": effective_from, "source": source, "bands": band_lines(bands),
                 "_kind": kind.value, "_bands": [[str(lower), str(rate)] for lower, rate in bands]},
        previous={"table": TAX_LABELS[kind],
                  "bands": band_lines([(b.lower, b.rate_pct) for b in current.bands]) if current else None},
    )
    db.commit()
    db.refresh(request)
    return request


def _apply_tax_table(db: Session, request: ApprovalRequest, checker: User) -> None:
    data = request.payload
    kind, effective_from = TaxTableKind(data["_kind"]), date.fromisoformat(data["effective_from"])
    if db.execute(select(TaxTable.id).where(TaxTable.kind == kind, TaxTable.effective_from == effective_from)).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A table from that date was added in the meantime")
    table = TaxTable(kind=kind, effective_from=effective_from, source=data.get("source"), approved_by_user_id=checker.id)
    table.bands = [TaxBand(position=i, lower=Decimal(lower), rate_pct=Decimal(rate)) for i, (lower, rate) in enumerate(data["_bands"])]
    db.add(table)
    db.flush()
    audit.record(db, checker.id, "tax_table", table.id, "created",
                 after={"kind": kind.value, "effective_from": effective_from, "bands": data["_bands"]})


approvals.register(approvals.ApprovalKind(
    name=PARAMETER_KIND, label="Regulatory parameter", checker_roles=frozenset({UserRole.scheme_config_checker}), apply=_apply_parameter,
))
approvals.register(approvals.ApprovalKind(
    name=TAX_KIND, label="Tax table", checker_roles=frozenset({UserRole.scheme_config_checker}), apply=_apply_tax_table,
))
