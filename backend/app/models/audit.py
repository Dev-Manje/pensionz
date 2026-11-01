import uuid

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, UUIDPKMixin


class AuditEvent(UUIDPKMixin, CreatedAtMixin, Base):
    """Who did what to which record, with the values before and after
    (FR-SEC-003). Written in the same commit as the change it describes.
    Never updated or deleted."""

    __tablename__ = "audit_event"
    __table_args__ = (Index("ix_audit_event_entity", "entity_type", "entity_id", "created_at"),)

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Filled once funds exist (Phase 1) so audit can be filtered per fund.
    fund_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
