"""Contributions (FR-CON): money received, schedules and allocation.

Receipts are two-stage (decided with the user 2026-11-02):
1. a principal officer's **payment notice** (amount, date, reference, proof of
   payment) — acknowledged as "received, pending confirmation"; nothing posts;
2. a contributions officer **confirms** the money on the fund's bank statement
   (value date, amount actually received) and a contributions checker
   approves: Dr 1000 Bank / Cr 2100 Unallocated, and the official receipt
   number is issued.
Money that arrives without a notice is captured by staff straight into stage 2.
Money nobody can place yet is confirmed without an employer (unidentified)
and stays in 2100 until it is identified.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin, str_enum


class ReceiptStatus(str, enum.Enum):
    # A principal officer says they've paid; staff haven't confirmed the money yet.
    notified = "notified"
    # Staff confirmed it against the bank; waiting for a contributions checker.
    pending_approval = "pending_approval"
    confirmed = "confirmed"
    # The money was never received (notice declined) or the capture was rejected.
    rejected = "rejected"
    cancelled = "cancelled"


class ReceiptSource(str, enum.Enum):
    portal_notice = "portal_notice"
    staff = "staff"


class PaymentMethod(str, enum.Enum):
    eft = "eft"
    rtgs = "rtgs"
    cheque = "cheque"
    cash_deposit = "cash_deposit"
    mobile_money = "mobile_money"


class ContributionReceipt(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "contribution_receipt"
    __table_args__ = (UniqueConstraint("fund_id", "receipt_number", name="uq_contribution_receipt_number"),)

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    # NULL = unidentified money (confirmed but not yet placed with an employer).
    scheme_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("scheme.id"), nullable=True, index=True)
    status: Mapped[ReceiptStatus] = mapped_column(str_enum(ReceiptStatus, 20), nullable=False, index=True)
    source: Mapped[ReceiptSource] = mapped_column(str_enum(ReceiptSource, 20), nullable=False)
    # Issued on confirmation: "<FUND>-R000123".
    receipt_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Notice reference shown to the officer before confirmation: "<FUND>-N000045".
    notice_number: Mapped[str | None] = mapped_column(String(30), nullable=True)

    payment_method: Mapped[PaymentMethod] = mapped_column(str_enum(PaymentMethod, 20), nullable=False)
    # What the officer said they paid (notices only).
    notified_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    # What reached the fund's bank account (set by staff).
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Good funds in the fund's account — drives investment dates and late-payment interest.
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fund_bank_account.id"), nullable=True)
    payer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # The reference the payer put on the payment (should carry the employer code).
    payer_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bank_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # The month the money is for (first of the month), when known.
    contribution_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    proof_storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    proof_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    proof_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    notified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    captured_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_entry.id"), nullable=True)

    @property
    def unallocated(self) -> Decimal:
        return (self.amount or Decimal("0")) - self.allocated_amount if self.status == ReceiptStatus.confirmed else Decimal("0")


class ScheduleStatus(str, enum.Enum):
    # Being built (upload or capture); lines can change.
    draft = "draft"
    # Checked with no errors and handed over for allocation.
    ready = "ready"
    allocated = "allocated"
    cancelled = "cancelled"


class ScheduleSource(str, enum.Enum):
    upload = "upload"
    manual = "manual"
    portal = "portal"


class ContributionSchedule(UUIDPKMixin, TimestampMixin, Base):
    """An employer's member-by-member split of one month's contributions
    (FR-CON-003). One main schedule per employer per month; back pay or
    corrections go in supplementary schedules."""

    __tablename__ = "contribution_schedule"

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    scheme_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scheme.id"), nullable=False, index=True)
    # First day of the month the contributions are for.
    contribution_month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    supplementary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reference: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[ScheduleStatus] = mapped_column(str_enum(ScheduleStatus, 20), nullable=False, default=ScheduleStatus.draft, index=True)
    source: Mapped[ScheduleSource] = mapped_column(str_enum(ScheduleSource, 20), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Totals of all lines, kept in step on every change.
    total_employee: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    total_employer: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    total_voluntary: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    total_severance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lines: Mapped[list["ContributionScheduleLine"]] = relationship(
        back_populates="schedule", lazy="selectin", order_by="ContributionScheduleLine.row_no", cascade="all, delete-orphan"
    )


class ContributionScheduleLine(UUIDPKMixin, Base):
    __tablename__ = "contribution_schedule_line"

    schedule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contribution_schedule.id", ondelete="CASCADE"), nullable=False, index=True)
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    member_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("member.id"), nullable=True, index=True)
    # As given on the schedule (kept even when no member matches).
    account_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    employee_no: Mapped[str | None] = mapped_column(String(30), nullable=True)
    member_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pensionable_salary: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    employee: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    employer: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    voluntary: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    severance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    schedule: Mapped["ContributionSchedule"] = relationship(back_populates="lines")

    @property
    def total(self) -> Decimal:
        return self.employee + self.employer + self.voluntary + self.severance


class AllocationStatus(str, enum.Enum):
    pending_approval = "pending_approval"
    posted = "posted"
    rejected = "rejected"
    cancelled = "cancelled"
    # Undone by a reversal entry (FR-CON-007).
    reversed = "reversed"


class ContributionAllocation(UUIDPKMixin, TimestampMixin, Base):
    """Allocation of a ready schedule to members (legacy "Initial Allocation",
    FR-CON-005): the employer's confirmed receipts pay for it exactly — the
    schedule total plus any fees the employer pays on top ("hold until
    resolved", decided 2026-11-02). Members are credited net of fees they bear."""

    __tablename__ = "contribution_allocation"

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    scheme_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scheme.id"), nullable=False, index=True)
    schedule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contribution_schedule.id"), nullable=False, index=True)
    status: Mapped[AllocationStatus] = mapped_column(str_enum(AllocationStatus, 20), nullable=False, index=True)
    # Schedule total (what members' contributions add up to).
    schedule_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # Fees taken out of members' contributions.
    member_fees: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    # Fees the employer pays on top of the schedule.
    employer_fees: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    # Money taken from receipts = schedule total + employer fees.
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # Credited to members = schedule total − member fees.
    net_to_members: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # [{"code", "name", "fee_type", "payer", "rate", "amount", "gl_code"}]
    fees: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_entry.id"), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    receipts: Mapped[list["AllocationReceipt"]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class AllocationReceipt(UUIDPKMixin, Base):
    """How much of which receipt pays for an allocation."""

    __tablename__ = "contribution_allocation_receipt"

    allocation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contribution_allocation.id", ondelete="CASCADE"), nullable=False, index=True)
    receipt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contribution_receipt.id"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
