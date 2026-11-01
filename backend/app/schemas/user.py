import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.identity import UserRole, UserStatus


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    phone: str | None
    roles: list[UserRole]
    status: UserStatus
    last_login_at: datetime | None
    created_at: datetime
    locked: bool = False
    # Invited but hasn't set a password yet.
    awaiting_setup: bool = False

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    roles: list[UserRole]


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    roles: list[UserRole] | None = None
    status: UserStatus | None = None
