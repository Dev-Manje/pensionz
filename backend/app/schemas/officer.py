import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.identity import UserStatus


class OfficerCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    # Funds the officer may apply into with a new employer.
    fund_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class OfficerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    fund_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=50)


class OfficerFundOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    # Granted by staff (else only there through one of the officer's employers).
    granted: bool


class OfficerEmployerOut(BaseModel):
    scheme_id: uuid.UUID
    code: str
    name: str
    fund_code: str


class OfficerListOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    status: UserStatus
    awaiting_setup: bool
    last_login_at: datetime | None
    funds: list[OfficerFundOut]
    employers: list[OfficerEmployerOut]
    pending_approval_id: uuid.UUID | None = None
