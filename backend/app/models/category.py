"""Benefit categories (FR-CFG-004) — e.g. "Management", "Staff" under an employer.

The category itself (code, name, status) is stable; its rules are
`BenefitCategoryTerms` versions, each in force from a date, so a rate change
never rewrites the past (pz-scheme-config). Terms resolve through
services/config_resolver.category_terms."""
import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPKMixin, str_enum


class CategoryStatus(str, enum.Enum):
    active = "active"
    # Existing members stay; nobody new joins this category.
    closed = "closed"


class BenefitDesign(str, enum.Enum):
    dc = "dc"
    db = "db"


class RateType(str, enum.Enum):
    # % of pensionable salary
    percent = "percent"
    # fixed MWK per month
    fixed = "fixed"


class SalaryBasis(str, enum.Enum):
    basic = "basic"
    basic_plus_allowances = "basic_plus_allowances"
    total_emoluments = "total_emoluments"


class BenefitCategory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "benefit_category"
    __table_args__ = (UniqueConstraint("scheme_id", "code", name="uq_benefit_category_scheme_code"),)

    scheme_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scheme.id"), nullable=False, index=True)
    # Copied from the scheme so fund scoping and approvals need no join.
    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[CategoryStatus] = mapped_column(str_enum(CategoryStatus, 20), nullable=False, default=CategoryStatus.active)

    terms: Mapped[list["BenefitCategoryTerms"]] = relationship(
        back_populates="category", lazy="selectin", order_by="BenefitCategoryTerms.effective_from.desc()"
    )


class BenefitCategoryTerms(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "benefit_category_terms"
    __table_args__ = (UniqueConstraint("category_id", "effective_from", name="uq_benefit_category_terms_from"),)

    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("benefit_category.id"), nullable=False, index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    design: Mapped[BenefitDesign] = mapped_column(str_enum(BenefitDesign, 10), nullable=False)

    employee_rate_type: Mapped[RateType] = mapped_column(str_enum(RateType, 10), nullable=False, default=RateType.percent)
    # Percent rates as percent (5.000000 = 5%); fixed rates in MWK per month.
    employee_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    employer_rate_type: Mapped[RateType] = mapped_column(str_enum(RateType, 10), nullable=False, default=RateType.percent)
    # NULL for DB funds where the employer pays the balance of cost set by the actuary.
    employer_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    salary_basis: Mapped[SalaryBasis] = mapped_column(str_enum(SalaryBasis, 30), nullable=False, default=SalaryBasis.basic)

    normal_retirement_age: Mapped[int] = mapped_column(Integer, nullable=False)
    min_entry_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_entry_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waiting_period_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # [{"years": 0, "vested_pct": "0"}, {"years": 5, "vested_pct": "100"}] — share of
    # employer money a leaver keeps after that many years of service.
    vesting_scale: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    default_investment_option_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("investment_option.id"), nullable=True)
    member_choice_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    avc_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Group life cover as a multiple of annual pensionable salary (insured with the risk insurer).
    group_life_multiple: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)

    # DB design only: pension = service × salary ÷ accrual_denominator (e.g. 60 → 1/60th per year).
    accrual_denominator: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Final salary averaged over this many months (e.g. 36).
    final_salary_months: Mapped[int | None] = mapped_column(Integer, nullable=True)

    category: Mapped["BenefitCategory"] = relationship(back_populates="terms")
