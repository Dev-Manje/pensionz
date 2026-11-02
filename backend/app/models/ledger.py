"""Fund ledgers and member transactions (FR-ACC-001…003, pz-accounting).

- Every fund has its own chart (`gl_account.fund_id`); the administrator's fee
  income lives in a separate book (`fund_id` NULL, book "administrator").
- A `journal_entry` is one balanced post (Σ debits = Σ credits within the
  fund) referencing the business event that caused it; its `ledger_line`s
  carry the amounts. Entries are never edited or deleted — a correction is a
  reversal entry pointing at the original.
- `member_transaction` is the member sub-ledger: one row per member, component
  and configured transaction type (legacy codes 1–6), each tied to the journal
  entry that posted it. Member balances are always summed from these rows.
"""
import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, UUIDPKMixin, str_enum
from app.models.reference import TransactionEffect


class Book(str, enum.Enum):
    fund = "fund"
    administrator = "administrator"


class AccountClass(str, enum.Enum):
    asset = "asset"
    liability = "liability"
    equity = "equity"
    income = "income"
    expense = "expense"


DEBIT_NORMAL = frozenset({AccountClass.asset, AccountClass.expense})


class Component(str, enum.Enum):
    """Contribution components (FR-CON-001); bonus and withdrawals post against
    the component they belong to, as on the legacy benefit statement."""

    employee = "employee"
    employer = "employer"
    voluntary = "voluntary"
    severance = "severance"
    transfer_in = "transfer_in"


class GLAccount(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "gl_account"
    __table_args__ = (
        UniqueConstraint("fund_id", "code", name="uq_gl_account_fund_code"),
        # The administrator book has no fund; its codes are unique on their own.
        Index("uq_gl_account_admin_code", "code", unique=True, postgresql_where=text("fund_id IS NULL")),
    )

    fund_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=True, index=True)
    book: Mapped[Book] = mapped_column(str_enum(Book, 20), nullable=False, default=Book.fund)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_class: Mapped[AccountClass] = mapped_column(str_enum(AccountClass, 20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class JournalEntry(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "journal_entry"

    fund_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=True, index=True)
    book: Mapped[Book] = mapped_column(str_enum(Book, 20), nullable=False, default=Book.fund)
    # Running number per book and fund, for references on screens and reports ("JE-000123").
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Processing month (first of the month) the entry belongs to.
    period: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # The business event: contribution_allocation, receipt, claim, bonus_run, ...
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_entry.id"), nullable=True, unique=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    lines: Mapped[list["LedgerLine"]] = relationship(back_populates="entry", lazy="selectin", order_by="LedgerLine.position")

    __table_args__ = (
        Index("ix_journal_entry_entity", "entity_type", "entity_id"),
        Index("uq_journal_entry_number", "book", text("coalesce(fund_id, '00000000-0000-0000-0000-000000000000'::uuid)"), "number", unique=True),
    )


class LedgerLine(UUIDPKMixin, Base):
    __tablename__ = "ledger_line"
    __table_args__ = (
        CheckConstraint("(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)", name="ck_ledger_line_one_side"),
    )

    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_entry.id"), nullable=False, index=True)
    # Copied from the entry so balances need no join.
    fund_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=True, index=True)
    gl_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gl_account.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    # Sub-ledger analysis: whose money this line is.
    member_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("member.id"), nullable=True, index=True)
    scheme_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("scheme.id"), nullable=True, index=True)
    component: Mapped[Component | None] = mapped_column(str_enum(Component, 20), nullable=True)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)

    entry: Mapped["JournalEntry"] = relationship(back_populates="lines")
    gl_account: Mapped["GLAccount"] = relationship(lazy="joined")


class MemberTransaction(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "member_transaction"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_member_transaction_positive"),)

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("member.id"), nullable=False, index=True)
    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    transaction_code: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Copied from the transaction type at posting: credit raises the member's balance.
    effect: Mapped[TransactionEffect] = mapped_column(str_enum(TransactionEffect, 10), nullable=False)
    component: Mapped[Component] = mapped_column(str_enum(Component, 20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    period: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Contribution month for allocations (first of the month); NULL otherwise.
    contribution_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_entry.id"), nullable=False, index=True)
    reverses_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("member_transaction.id"), nullable=True, unique=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
