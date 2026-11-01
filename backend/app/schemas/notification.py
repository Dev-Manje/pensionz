import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    event: str
    title: str
    body: str
    link: str | None
    created_at: datetime
    read_at: datetime | None

    model_config = {"from_attributes": True}


class UnreadCount(BaseModel):
    unread: int


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int
