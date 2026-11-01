"""Reference data (FR-CFG-010). Banks & branches come first because fund bank
accounts pick from them; districts, countries, relationships etc. follow."""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, UUIDPKMixin


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
