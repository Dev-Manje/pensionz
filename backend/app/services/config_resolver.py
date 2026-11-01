"""One place that answers "what value applies on this date?" for configuration
(pz-scheme-config). Every caller — contribution checks, benefit quotes, tax —
resolves through here so effective dates are applied the same way everywhere.
Category and member overrides are added here as those layers are built."""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import BenefitCategoryTerms
from app.models.regulatory import RegulatoryParameterVersion, TaxTable, TaxTableKind

CENT = Decimal("0.01")


def regulatory(db: Session, key: str, as_of: date) -> Decimal | None:
    """The value of a regulatory parameter in force on `as_of` (None if never set)."""
    return db.execute(
        select(RegulatoryParameterVersion.value)
        .where(RegulatoryParameterVersion.key == key, RegulatoryParameterVersion.effective_from <= as_of)
        .order_by(RegulatoryParameterVersion.effective_from.desc())
        .limit(1)
    ).scalar_one_or_none()


def category_terms(db: Session, category_id, as_of: date) -> BenefitCategoryTerms | None:
    """The benefit category's terms in force on `as_of` (None before its first terms)."""
    return db.execute(
        select(BenefitCategoryTerms).where(BenefitCategoryTerms.category_id == category_id, BenefitCategoryTerms.effective_from <= as_of)
        .order_by(BenefitCategoryTerms.effective_from.desc()).limit(1)
    ).scalar_one_or_none()


def tax_table(db: Session, kind: TaxTableKind, as_of: date) -> TaxTable | None:
    return db.execute(
        select(TaxTable).where(TaxTable.kind == kind, TaxTable.effective_from <= as_of)
        .order_by(TaxTable.effective_from.desc()).limit(1)
    ).scalar_one_or_none()


def tax_on(table: TaxTable, amount: Decimal) -> Decimal:
    """Progressive tax: each band's slice of `amount` at that band's rate,
    rounded half-up to the tambala per band, then summed."""
    amount = Decimal(amount)
    bands = sorted(table.bands, key=lambda b: b.lower)
    total = Decimal("0")
    for i, band in enumerate(bands):
        upper = bands[i + 1].lower if i + 1 < len(bands) else None
        if amount <= band.lower:
            break
        slice_ = (min(amount, upper) if upper is not None else amount) - band.lower
        total += (slice_ * band.rate_pct / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return total
