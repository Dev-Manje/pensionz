import re
import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.fund import BankAccountPurpose, FundStatus, FundType

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9/_\-]{0,9}$")


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class _Clean(BaseModel):
    """Trims text and turns empty strings into None, so optional fields left
    blank on a form don't fail email/length checks."""

    @model_validator(mode="before")
    @classmethod
    def _strip(cls, data):
        if isinstance(data, dict):
            return {k: _blank_to_none(v) for k, v in data.items()}
        return data


class TrusteeIn(_Clean):
    id: uuid.UUID | None = None
    full_name: str = Field(min_length=2, max_length=200)
    designation: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    appointed_on: date | None = None


class BankAccountIn(_Clean):
    id: uuid.UUID | None = None
    bank_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    account_name: str = Field(min_length=2, max_length=200)
    account_number: str = Field(min_length=4, max_length=30)
    currency: str = Field(default="MWK", pattern=r"^[A-Z]{3}$")
    purpose: BankAccountPurpose = BankAccountPurpose.general

    @field_validator("account_number")
    @classmethod
    def _digits(cls, value: str) -> str:
        value = re.sub(r"[\s-]", "", value)
        if not value.isdigit():
            raise ValueError("Account number should contain digits only")
        return value


class FundIn(_Clean):
    """The whole fund as the maker wants it to be: create and edit both send a
    full snapshot (details, trustees, bank accounts) for one approval."""

    code: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=2, max_length=200)
    fund_type: FundType
    status: FundStatus = FundStatus.active
    registration_number: str | None = Field(default=None, max_length=60)
    tpin: str | None = Field(default=None, max_length=30)
    financial_year_end_month: int | None = Field(default=None, ge=1, le=12)
    address_line1: str | None = Field(default=None, max_length=120)
    address_line2: str | None = Field(default=None, max_length=120)
    address_line3: str | None = Field(default=None, max_length=120)
    address_line4: str | None = Field(default=None, max_length=120)
    address_line5: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    fax: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    website: str | None = Field(default=None, max_length=255)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=40)
    contact_alt_phone: str | None = Field(default=None, max_length=40)
    trustees: list[TrusteeIn] = Field(default_factory=list, max_length=50)
    bank_accounts: list[BankAccountIn] = Field(default_factory=list, max_length=20)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.upper()
        if not CODE_RE.match(value):
            raise ValueError("Use up to 10 letters or digits (/, _ and - allowed after the first)")
        return value


class TrusteeOut(BaseModel):
    id: uuid.UUID
    full_name: str
    designation: str | None
    email: str | None
    phone: str | None
    appointed_on: date | None

    model_config = {"from_attributes": True}


class BankAccountOut(BaseModel):
    id: uuid.UUID
    bank_id: uuid.UUID
    bank_name: str
    branch_id: uuid.UUID | None
    branch_name: str | None
    account_name: str
    # Full number only for roles that work with it (FR-SEC-005); everyone gets the masked form.
    account_number: str | None
    account_number_masked: str
    currency: str
    purpose: BankAccountPurpose


class FundSummaryOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    fund_type: FundType
    status: FundStatus
    trustee_count: int
    bank_account_count: int
    pending_approval_id: uuid.UUID | None


class FundOut(FundSummaryOut):
    registration_number: str | None
    tpin: str | None
    financial_year_end_month: int | None
    address_line1: str | None
    address_line2: str | None
    address_line3: str | None
    address_line4: str | None
    address_line5: str | None
    phone: str | None
    fax: str | None
    email: str | None
    website: str | None
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    contact_alt_phone: str | None
    trustees: list[TrusteeOut]
    bank_accounts: list[BankAccountOut]
    # Fields that can no longer change because the fund has members.
    locked_fields: list[str]
    can_edit: bool


class BranchOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None

    model_config = {"from_attributes": True}


class BankOut(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None
    swift_code: str | None
    branches: list[BranchOut]

    model_config = {"from_attributes": True}
