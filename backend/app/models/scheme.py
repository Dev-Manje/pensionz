"""Participating employers ("schemes") within a fund (FR-CFG-003).

An umbrella fund has many; a stand-alone or DB fund usually has its sponsoring
employer. Each has its own contribution due day, billing frequency and
contacts, and the principal officers who remit for it through the portal
(FR-PRT-006: one officer may serve many schemes, a scheme many officers).
Created and changed only through the "scheme_setup" approval."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class EmployerApplicationStatus(str, enum.Enum):
    # The officer is still filling it in.
    draft = "draft"
    # Sent to the administrator; scheme setup reviews it.
    submitted = "submitted"
    # Sent back to the officer with a note.
    returned = "returned"
    # Scheme setup sent the final terms to a checker.
    in_approval = "in_approval"
    approved = "approved"
    rejected = "rejected"
    withdrawn = "withdrawn"


class EmployerApplication(UUIDPKMixin, TimestampMixin, Base):
    """A principal officer's application for a new employer to join a fund
    (decided 2026-11-03). The officer proposes the details and the members'
    categories and rates and completes the organisation KYC; compliance
    approves the KYC, scheme setup sets the final terms (employer code,
    default investment option, any rate changes) and a scheme-setup checker
    approves — only then is the employer created, with the officer linked."""

    __tablename__ = "employer_application"

    reference: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    officer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True)
    status: Mapped[EmployerApplicationStatus] = mapped_column(
        str_enum(EmployerApplicationStatus, 20), nullable=False, default=EmployerApplicationStatus.draft, index=True)
    # Organisation details as proposed (name, registration, address, contact, contribution day …).
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # [{"name", "employee_rate", "employer_rate", "salary_basis", "normal_retirement_age"}] as proposed.
    categories: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # The final terms scheme setup sent for approval (code, join date, full category terms).
    final_terms: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    kyc_application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("kyc_application.id"), nullable=True)
    scheme_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("scheme.id"), nullable=True)
    # The latest note to the officer (returned / rejected / approved).
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
