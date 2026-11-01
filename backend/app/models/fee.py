"""Fee rules per fund (FR-CFG-008).

A rule applies to the whole fund, or to one participating employer — an
employer's own rule replaces the fund-wide rule of the same fee type.
Rules are dated (`effective_from` / optional `effective_to`); rules of the same
type and scope may not overlap. Charging and posting the fees comes with the
ledger (Phase 4, pz-accounting): fund money never pays administrator costs
except through these approved rules."""
import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin, str_enum


class FeeType(str, enum.Enum):
    administration = "administration"
    investment_management = "investment_management"
    risk_premium = "risk_premium"
    statutory_levy = "statutory_levy"
    other = "other"


class FeeBasis(str, enum.Enum):
    pct_contributions = "pct_contributions"
    pct_assets = "pct_assets"
    flat_per_member = "flat_per_member"


class FeePayer(str, enum.Enum):
    fund = "fund"
    employer = "employer"
    member = "member"


class FeeFrequency(str, enum.Enum):
    per_contribution = "per_contribution"
    monthly = "monthly"
    quarterly = "quarterly"
    annually = "annually"


class FeeRule(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "fee_rule"
    __table_args__ = (UniqueConstraint("fund_id", "code", name="uq_fee_rule_fund_code"),)

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    # NULL = the whole fund; otherwise only this employer (and it overrides the fund-wide rule).
    scheme_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("scheme.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    fee_type: Mapped[FeeType] = mapped_column(str_enum(FeeType, 30), nullable=False)
    basis: Mapped[FeeBasis] = mapped_column(str_enum(FeeBasis, 30), nullable=False)
    # Percent bases: percent (1.5 = 1.5%; % of assets is per year). Flat: MWK per member per period.
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    payer: Mapped[FeePayer] = mapped_column(str_enum(FeePayer, 20), nullable=False)
    frequency: Mapped[FeeFrequency] = mapped_column(str_enum(FeeFrequency, 20), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
