import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.period import PeriodStatus


class PeriodOut(BaseModel):
    id: uuid.UUID
    period: date
    status: PeriodStatus
    opened_at: datetime
    opened_by: str | None
    closed_at: datetime | None
    closed_by: str | None


class CheckOut(BaseModel):
    key: str
    label: str
    status: str
    detail: str | None


class PeriodsOut(BaseModel):
    current: PeriodOut | None
    checklist: list[CheckOut]
    history: list[PeriodOut]
    pending_reopen_approval_id: uuid.UUID | None
    can_open_first: bool
    can_close: bool
    can_request_reopen: bool


class OpenFirstIn(BaseModel):
    period: date


class CloseIn(BaseModel):
    # The month the user saw on screen; refused if the open month has moved on.
    period: date


class ReopenIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
