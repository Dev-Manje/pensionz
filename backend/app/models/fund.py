"""Fund / company setup (FR-CFG-001, legacy "Company Setup") and which staff
administer which funds (FR-SEC-001). Funds are created and changed only
through the "fund_setup" approval (services/funds.py)."""
import enum
import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPKMixin, str_enum


class FundType(str, enum.Enum):
    standalone_dc = "standalone_dc"
    umbrella_dc = "umbrella_dc"
    personal_pension = "personal_pension"
    defined_benefit = "defined_benefit"
    minors_trust = "minors_trust"


class FundStatus(str, enum.Enum):
    active = "active"
    # Existing members carry on; no new joiners.
    closed_to_new_members = "closed_to_new_members"
    wound_up = "wound_up"


class BankAccountPurpose(str, enum.Enum):
    collections = "collections"
    payments = "payments"
    general = "general"


class Fund(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "fund"

    # Free text up to 10 characters, so legacy codes carry over unchanged.
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    fund_type: Mapped[FundType] = mapped_column(str_enum(FundType, 30), nullable=False)
    status: Mapped[FundStatus] = mapped_column(str_enum(FundStatus, 30), nullable=False, default=FundStatus.active)
    registration_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tpin: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # 1–12; NULL means the calendar year (December).
    financial_year_end_month: Mapped[int | None] = mapped_column(Integer, nullable=True)

    address_line1: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_line3: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_line4: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_line5: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fax: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)

    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contact_alt_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    trustees: Mapped[list["FundTrustee"]] = relationship(
        back_populates="fund", lazy="selectin", order_by="FundTrustee.sort_order"
    )
    bank_accounts: Mapped[list["FundBankAccount"]] = relationship(
        back_populates="fund", lazy="selectin", order_by="FundBankAccount.sort_order"
    )


class FundTrustee(UUIDPKMixin, CreatedAtMixin, Base):
    """A trustee of the fund. Removed trustees are kept inactive, not deleted."""

    __tablename__ = "fund_trustee"

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # e.g. Chairperson, Member-elected trustee, Employer-appointed trustee.
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    appointed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    fund: Mapped["Fund"] = relationship(back_populates="trustees")


class FundBankAccount(UUIDPKMixin, CreatedAtMixin, Base):
    """The fund's own bank account. Receipts and payments will reference it, so
    a removed account is kept inactive, never deleted."""

    __tablename__ = "fund_bank_account"

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    bank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bank.id"), nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bank_branch.id"), nullable=True)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_number: Mapped[str] = mapped_column(String(30), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="MWK")
    purpose: Mapped[BankAccountPurpose] = mapped_column(str_enum(BankAccountPurpose, 20), nullable=False, default=BankAccountPurpose.general)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    fund: Mapped["Fund"] = relationship(back_populates="bank_accounts")
    bank = relationship("Bank", lazy="joined")
    branch = relationship("BankBranch", lazy="joined")


class UserFundAccess(UUIDPKMixin, CreatedAtMixin, Base):
    """Staff see only the funds they administer (FR-SEC-001); admins and
    auditors see all funds without a row here."""

    __tablename__ = "user_fund_access"
    __table_args__ = (UniqueConstraint("user_id", "fund_id", name="uq_user_fund_access"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
