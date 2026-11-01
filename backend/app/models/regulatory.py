"""Regulatory parameters and tax tables (FR-CFG-009).

Every figure is effective-dated: a new value is a new version from a date,
never an overwrite, so any past date still resolves to the value then in force
(services/config_resolver.py). Versions are added through approvals only."""
import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, UUIDPKMixin, str_enum


class RegulatoryParameterVersion(UUIDPKMixin, CreatedAtMixin, Base):
    """One value of a parameter (key from services/regulatory.PARAMETERS) from a date."""

    __tablename__ = "regulatory_parameter_version"
    __table_args__ = (UniqueConstraint("key", "effective_from", name="uq_regulatory_parameter_version"),)

    key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # Percentages are stored as percent (5.000000 = 5%); ages/months/years as whole numbers.
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    # Where the figure comes from, e.g. "Pension Act 2023 s.66".
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)


class TaxTableKind(str, enum.Enum):
    # Monthly PAYE applied to pensions in payment and programmed withdrawals.
    paye_monthly = "paye_monthly"
    # Tax on lump-sum benefits (retirement, withdrawal, death).
    lump_sum = "lump_sum"


class TaxTable(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "tax_table"
    __table_args__ = (UniqueConstraint("kind", "effective_from", name="uq_tax_table_version"),)

    kind: Mapped[TaxTableKind] = mapped_column(str_enum(TaxTableKind, 30), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    bands: Mapped[list["TaxBand"]] = relationship(
        back_populates="table", lazy="selectin", order_by="TaxBand.position", cascade="all, delete-orphan"
    )


class TaxBand(UUIDPKMixin, Base):
    """Income from `lower` up to the next band's lower (or without limit, for
    the last band) is taxed at `rate_pct`."""

    __tablename__ = "tax_band"

    table_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tax_table.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    lower: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    rate_pct: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)

    table: Mapped["TaxTable"] = relationship(back_populates="bands")
