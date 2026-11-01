"""Fee rules per fund (FR-CFG-008) via the shared FundConfig maker-checker
(approval kind "fee_rule")."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fee import FeeBasis, FeeFrequency, FeePayer, FeeRule, FeeType
from app.models.fund import Fund
from app.models.scheme import Scheme
from app.services.config_changes import FundConfig, as_date, enum_of

def employer_label(db: Session, scheme_id) -> str | None:
    scheme = db.get(Scheme, uuid.UUID(str(scheme_id))) if scheme_id else None
    return f"{scheme.code} — {scheme.name}" if scheme else None


LIMITS = {
    FeeBasis.pct_contributions: (Decimal("0"), Decimal("100")),
    FeeBasis.pct_assets: (Decimal("0"), Decimal("10")),  # per year
    FeeBasis.flat_per_member: (Decimal("0"), Decimal("10000000")),
}


def _validate(db: Session, fund: Fund, values: dict, existing: FeeRule | None) -> None:
    basis, frequency = values["basis"], values["frequency"]
    low, high = LIMITS[basis]
    if not (low <= values["rate"] <= high):
        unit = "MWK" if basis == FeeBasis.flat_per_member else "%"
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The rate must be between {low} and {high} {unit}".replace(" %", "%"))
    if basis == FeeBasis.pct_contributions and frequency != FeeFrequency.per_contribution:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A % of contributions fee is charged on each contribution")
    if basis != FeeBasis.pct_contributions and frequency == FeeFrequency.per_contribution:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a % of contributions fee is charged per contribution — choose how often to charge it")
    if values["effective_to"] and values["effective_to"] <= values["effective_from"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The end date must be after the start date")
    scheme_id = values["scheme_id"]
    if scheme_id is not None:
        scheme = db.get(Scheme, scheme_id)
        if scheme is None or scheme.fund_id != fund.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The employer must belong to this fund")
    # Same fee type and scope may not overlap in time.
    clash_query = select(FeeRule).where(
        FeeRule.fund_id == fund.id, FeeRule.fee_type == values["fee_type"],
        FeeRule.scheme_id.is_(None) if scheme_id is None else FeeRule.scheme_id == scheme_id,
    )
    start, end = values["effective_from"], values["effective_to"] or date.max
    for other in db.execute(clash_query).scalars():
        if existing is not None and other.id == existing.id:
            continue
        if other.effective_from < end and start < (other.effective_to or date.max):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Fee rule {other.code} already covers this fee for the same {'employer' if scheme_id else 'fund'} "
                                f"from {other.effective_from.day} {other.effective_from:%b %Y} — end it first")


RULES = FundConfig(
    kind="fee_rule",
    label="Fee rule",
    model=FeeRule,
    fields=("code", "name", "scheme_id", "fee_type", "basis", "rate", "payer", "frequency", "effective_from", "effective_to"),
    converters={
        "scheme_id": lambda v: uuid.UUID(str(v)), "fee_type": enum_of(FeeType), "basis": enum_of(FeeBasis), "rate": lambda v: Decimal(str(v)),
        "payer": enum_of(FeePayer), "frequency": enum_of(FeeFrequency), "effective_from": as_date, "effective_to": as_date,
    },
    validate=_validate,
    readable=lambda db, values: {"employer": employer_label(db, values.get("scheme_id")) or "Whole fund"},
)


def rules_in_force(db: Session, fund_id: uuid.UUID, scheme_id: uuid.UUID | None, as_of: date) -> list[FeeRule]:
    """The fee rules that apply to an employer (or the fund) on a date: an
    employer's own rule replaces the fund-wide rule of the same fee type."""
    rows = db.execute(
        select(FeeRule).where(
            FeeRule.fund_id == fund_id, FeeRule.effective_from <= as_of,
            (FeeRule.effective_to.is_(None)) | (FeeRule.effective_to > as_of),
        )
    ).scalars().all()
    chosen: dict[FeeType, FeeRule] = {}
    for rule in sorted(rows, key=lambda r: r.scheme_id is not None):  # fund-wide first, employer rules override
        if rule.scheme_id is None or rule.scheme_id == scheme_id:
            chosen[rule.fee_type] = rule
    return list(chosen.values())
