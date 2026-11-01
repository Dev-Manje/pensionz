"""Maker-checker (FR-SEC-002). Anything a second person must approve is an
ApprovalRequest: the maker submits the proposed change as `payload`; a checker
with the right role (and not the maker) approves it, and the handler
registered for its `kind` applies it (services/approvals.py)."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, UUIDPKMixin, str_enum


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class ApprovalRequest(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "approval_request"
    __table_args__ = (Index("ix_approval_request_status_kind", "status", "kind"),)

    # Registered kind, e.g. "user_access": decides who may approve and what approval does.
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    # The record it changes (entity_id NULL while it proposes a new record).
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Values at submission, for the checker's before → after view.
    previous: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ApprovalStatus] = mapped_column(str_enum(ApprovalStatus, 20), nullable=False, default=ApprovalStatus.pending)
    fund_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    initiated_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
