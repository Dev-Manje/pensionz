import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.identity import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SignInResult(BaseModel):
    """Either tokens, or — for portal users — a challenge to finish with the
    emailed one-time code (POST /auth/sign-in-code)."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    code_required: bool = False
    challenge: str | None = None
    code_sent_to: str | None = None


class SignInCodeRequest(BaseModel):
    challenge: str
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendCodeRequest(BaseModel):
    challenge: str


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
