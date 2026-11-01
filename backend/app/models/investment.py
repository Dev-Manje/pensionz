"""Investment options per fund (FR-CFG-007).

A declared-rate pool earns the bonus rate trustees declare each period (the
legacy method, Phase 6); a unit-priced portfolio is priced per unit (later
phase — the option can be recorded now, pricing comes with FR-EAR-005).
Benefit categories pick their default option from these."""
import enum
import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin, str_enum


class PricingMethod(str, enum.Enum):
    declared_rate = "declared_rate"
    unit_price = "unit_price"


class InvestmentOptionStatus(str, enum.Enum):
    active = "active"
    # Existing money stays; no new money or switches in.
    closed = "closed"


class InvestmentOption(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "investment_option"
    __table_args__ = (UniqueConstraint("fund_id", "code", name="uq_investment_option_fund_code"),)

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    pricing_method: Mapped[PricingMethod] = mapped_column(str_enum(PricingMethod, 20), nullable=False)
    status: Mapped[InvestmentOptionStatus] = mapped_column(str_enum(InvestmentOptionStatus, 20), nullable=False, default=InvestmentOptionStatus.active)
    launch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
