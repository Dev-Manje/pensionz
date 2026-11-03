"""Declared bonus / earnings (FR-EAR-001…004; method decided 2026-11-03).

A `bonus_declaration` is the trustees' rate for a fund and period (interim or
final), recorded through maker-checker. A `bonus_run` calculates the bonus per
member per component for a declaration — previewed, then approved and posted
as Bonus (transaction type 6), or Bonus Reversal (type 5) where a final rate
is below what an interim already credited. `bonus_run_line` keeps every
member's figures (base, time-weighted amounts, already credited) so the run
can be explained and reversed exactly.

Bonus member transactions carry the declaration's period in
`member_transaction.contribution_month` (first day of the period's last month):
that is how later periods count earlier bonus in their opening balance and how
a final run knows what interim bonus a member already received."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.ledger import Component
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPKMixin, str_enum


class BonusKind(str, enum.Enum):
    # For members who leave before the final rate is known; trued up later.
    interim = "interim"
    final = "final"


class BonusRunStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    posted = "posted"
    # Thrown away before posting (rejected by the checker or discarded by the maker).
    discarded = "discarded"
    reversed = "reversed"


class BonusDeclaration(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "bonus_declaration"
    __table_args__ = (
        Index("uq_bonus_declaration_period_kind", "fund_id", "period_start", "period_end", "kind", unique=True),
    )

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    reference: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    kind: Mapped[BonusKind] = mapped_column(str_enum(BonusKind, 10), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    # Percent per annum (6.5 = 6.5% a year), applied pro rata by days / 365.
    rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    # Components that earn bonus, e.g. ["employee", "employer", "voluntary", "transfer_in"].
    components: Mapped[list] = mapped_column(JSONB, nullable=False)
    # Trustee resolution / minute reference.
    resolution: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    declared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)


class BonusRun(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "bonus_run"
    __table_args__ = (
        # Only one live final run per declaration (idempotent batch).
        Index("uq_bonus_run_final_live", "declaration_id", unique=True,
              postgresql_where=text("kind = 'final' AND status IN ('draft', 'pending_approval', 'posted')")),
    )

    declaration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bonus_declaration.id"), nullable=False, index=True)
    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    reference: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    kind: Mapped[BonusKind] = mapped_column(str_enum(BonusKind, 10), nullable=False)
    status: Mapped[BonusRunStatus] = mapped_column(str_enum(BonusRunStatus, 20), nullable=False, default=BonusRunStatus.draft, index=True)
    # Interim runs: the members it is for (each to their exit date or `as_at`); final runs: None = every member.
    member_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Interim runs: calculate to this date for members without an exit date in the period.
    as_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    total_debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_entry.id"), nullable=True)
    reversal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_entry.id"), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lines: Mapped[list["BonusRunLine"]] = relationship(back_populates="run", lazy="selectin", cascade="all, delete-orphan",
                                                       order_by="BonusRunLine.position")


class BonusRunLine(UUIDPKMixin, CreatedAtMixin, Base):
    """One member and component: how the bonus was worked out."""

    __tablename__ = "bonus_run_line"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bonus_run.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("member.id"), nullable=False, index=True)
    component: Mapped[Component] = mapped_column(str_enum(Component, 20), nullable=False)
    # The member's end of the period: the period end, their exit date, or the interim as-at date.
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    opening_bonus: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    # Net money in/out during the period (contributions, reversals, withdrawals), and bonus on it.
    movements: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    movements_bonus: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    # Opening bonus + movements bonus, 2 dp half-up.
    calculated: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # Bonus for this period already credited (an earlier interim run).
    already_credited: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # calculated − already credited: > 0 posts Bonus (6), < 0 posts Bonus Reversal (5).
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    member_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("member_transaction.id"), nullable=True)
    # Individual reversal (type 5 / 6 mirror) of this line after posting.
    reversal_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("member_transaction.id"), nullable=True)

    run: Mapped["BonusRun"] = relationship(back_populates="lines")
