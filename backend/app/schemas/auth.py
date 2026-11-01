import uuid

from pydantic import BaseModel, EmailStr

from app.models.identity import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ResetLinkStatus(BaseModel):
    valid: bool
    purpose: str | None = None
    email: str | None = None


class MeResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    roles: list[UserRole]
    is_staff: bool

    model_config = {"from_attributes": True}
