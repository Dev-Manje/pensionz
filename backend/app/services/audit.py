"""Business audit trail (FR-SEC-003). Call `record` in the same transaction as
the change; never commits."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def record(
    db: Session,
    actor_user_id: uuid.UUID | None,
    entity_type: str,
    entity_id: Any,
    action: str,
    *,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
    fund_id: uuid.UUID | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        before=_jsonable(before) if before is not None else None,
        after=_jsonable(after) if after is not None else None,
        ip_address=ip_address,
        fund_id=fund_id,
    )
    db.add(event)
    return event
