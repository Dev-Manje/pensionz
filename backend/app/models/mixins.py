import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


def str_enum(enum_cls, length: int = 40) -> Enum:
    """Enums are stored as VARCHAR (no Postgres enum type), so adding a value
    is a code change only — no migration. Values are still validated in Python."""
    return Enum(enum_cls, native_enum=False, length=length, validate_strings=True)
