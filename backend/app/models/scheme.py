"""Participating employers ("schemes") within a fund (FR-CFG-003).

An umbrella fund has many; a stand-alone or DB fund usually has its sponsoring
employer. Each has its own contribution due day, billing frequency and
contacts, and the principal officers who remit for it through the portal
(FR-PRT-006: one officer may serve many schemes, a scheme many officers).
Created and changed only through the "scheme_setup" approval."""
import enum
import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPKMixin, str_enum


class SchemeStatus(str, enum.Enum):
    active = "active"
    # Contributions on hold (e.g. employer in arrears or dispute); members stay.
    suspended = "suspended"
    # The employer has left the fund.
    exited = "exited"


class BillingFrequency(str, enum.Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    annually = "annually"


class Scheme(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "scheme"
    __table_args__ = (UniqueConstraint("fund_id", "code", name="uq_scheme_fund_code"),)

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[SchemeStatus] = mapped_column(str_enum(SchemeStatus, 20), nullable=False, default=SchemeStatus.active)
    registration_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tpin: Mapped[str | None] = mapped_column(String(30), nullable=True)
    join_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Contributions for a month are due by this day of the following month.
    contribution_day: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_frequency: Mapped[BillingFrequency] = mapped_column(str_enum(BillingFrequency, 20), nullable=False, default=BillingFrequency.monthly)

    address_line1: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_line3: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The employer's approved corporate KYC client (FR-ONB-105).
    party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("party.id"), nullable=True, index=True)

    officers: Mapped[list["SchemeOfficer"]] = relationship(back_populates="scheme", lazy="selectin", cascade="all, delete-orphan")


class SchemeOfficer(UUIDPKMixin, CreatedAtMixin, Base):
    """A principal officer who acts for the scheme in the portal."""

    __tablename__ = "scheme_officer"
    __table_args__ = (UniqueConstraint("scheme_id", "user_id", name="uq_scheme_officer"),)

    scheme_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scheme.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True)

    scheme: Mapped["Scheme"] = relationship(back_populates="officers")
    user = relationship("User", lazy="joined")
