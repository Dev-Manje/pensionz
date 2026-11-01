"""Reference data and ledger set-up lists (FR-CFG-005, FR-CFG-006, FR-CFG-010).
All are maintained through Setup with maker-checker (services/system_lists.py);
rows are retired with `active = false`, never deleted, because records point at them."""
import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, UUIDPKMixin, str_enum


class Bank(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "bank"

    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    short_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
    swift_code: Mapped[str | None] = mapped_column(String(11), nullable=True)
    # Retired banks stay so old bank accounts still show their bank.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    branches: Mapped[list["BankBranch"]] = relationship(
        back_populates="bank", lazy="selectin", order_by="BankBranch.name"
    )


class BankBranch(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "bank_branch"
    __table_args__ = (UniqueConstraint("bank_id", "name", name="uq_bank_branch_name"),)

    bank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bank.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    bank: Mapped["Bank"] = relationship(back_populates="branches")


# ---- ledger set-up (FR-CFG-005, FR-CFG-006)


class LedgerBehaviour(str, enum.Enum):
    fund = "fund"
    member = "member"
    employer = "employer"
    reserve = "reserve"
    other = "other"


class AccountType(UUIDPKMixin, CreatedAtMixin, Base):
    """Legacy account types (Pension Fund, Member, Company, Reserve, Share)."""

    __tablename__ = "account_type"

    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    ledger_behaviour: Mapped[LedgerBehaviour] = mapped_column(str_enum(LedgerBehaviour, 20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TransactionEffect(str, enum.Enum):
    # On the member's account: a credit increases the balance, a debit reduces it.
    credit = "credit"
    debit = "debit"


class TransactionType(UUIDPKMixin, CreatedAtMixin, Base):
    """Configurable transaction codes (legacy 1–6 seeded); every type is paired
    with the type that reverses it, which has the opposite effect."""

    __tablename__ = "transaction_type"

    code: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    effect: Mapped[TransactionEffect] = mapped_column(str_enum(TransactionEffect, 10), nullable=False)
    reversal_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Fund chart of accounts codes (proposed chart — to confirm with finance, pz-accounting).
    debit_gl_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    credit_gl_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ---- places and people (FR-CFG-010)


class District(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "district"

    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    # northern | central | southern
    region: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TraditionalAuthority(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "traditional_authority"
    __table_args__ = (UniqueConstraint("district_id", "name", name="uq_traditional_authority_name"),)

    district_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("district.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Village(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "village"
    __table_args__ = (UniqueConstraint("traditional_authority_id", "name", name="uq_village_name"),)

    traditional_authority_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("traditional_authority.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Country(UUIDPKMixin, CreatedAtMixin, Base):
    """ISO 3166 countries; also the nationality list."""

    __tablename__ = "country"

    code: Mapped[str] = mapped_column(String(2), nullable=False, unique=True)
    code3: Mapped[str] = mapped_column(String(3), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ReferenceList(str, enum.Enum):
    relationship = "relationship"
    id_type = "id_type"
    permit_type = "permit_type"
    salutation = "salutation"
    # Products / schemes a KYC applicant can tick (FR-ONB-003).
    kyc_product = "kyc_product"


class ReferenceItem(UUIDPKMixin, CreatedAtMixin, Base):
    """Short pick-lists: relationships, ID types, permit types, salutations."""

    __tablename__ = "reference_item"
    __table_args__ = (UniqueConstraint("list_key", "code", name="uq_reference_item_code"),)

    list_key: Mapped[ReferenceList] = mapped_column(str_enum(ReferenceList, 30), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
