"""Processing month per fund (FR-CFG-002, legacy "processing month").

A fund has exactly one open month; transactions post only into it
(services/periods.require_open). Closing a month opens the next; re-opening
the latest closed month is maker-checker."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, UUIDPKMixin, str_enum


class PeriodStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class FundPeriod(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "fund_period"
    __table_args__ = (
        UniqueConstraint("fund_id", "period", name="uq_fund_period"),
        # One open month per fund, enforced by the database.
        Index("uq_fund_period_one_open", "fund_id", unique=True, postgresql_where=text("status = 'open'")),
    )

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    # First day of the month.
    period: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PeriodStatus] = mapped_column(str_enum(PeriodStatus, 20), nullable=False, default=PeriodStatus.open)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opened_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
