import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.approval import ApprovalStatus


class ApprovalOut(BaseModel):
    id: uuid.UUID
    kind: str
    kind_label: str
    entity_type: str
    entity_id: str | None
    summary: str
    payload: dict
    previous: dict | None
    status: ApprovalStatus
    initiated_by: str
    initiated_by_user_id: uuid.UUID
    created_at: datetime
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_comment: str | None
    # What the signed-in user may do with it.
    can_review: bool
    can_cancel: bool


class ApprovalDecision(BaseModel):
    comment: str | None = None
