import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.scheme import BillingFrequency, SchemeStatus
from app.schemas.fund import CODE_RE, _Clean


class NewOfficerIn(_Clean):
    """Someone to invite as a principal officer when the employer change is
    approved. If the email already belongs to a principal officer (who may act
    for other employers or funds), that login is linked instead."""

    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)


class SchemeIn(_Clean):
    """The whole scheme as the maker wants it to be, including which principal
    officers act for it; create and edit both go to one approval."""

    code: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=2, max_length=200)
    status: SchemeStatus = SchemeStatus.active
    registration_number: str | None = Field(default=None, max_length=60)
    tpin: str | None = Field(default=None, max_length=30)
    join_date: date | None = None
    exit_date: date | None = None
    contribution_day: int = Field(ge=1, le=28)
    billing_frequency: BillingFrequency = BillingFrequency.monthly
    address_line1: str | None = Field(default=None, max_length=120)
    address_line2: str | None = Field(default=None, max_length=120)
    address_line3: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=40)
    officer_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    new_officers: list[NewOfficerIn] = Field(default_factory=list, max_length=10)
    # Approved corporate KYC client for this employer (FR-ONB-105).
    party_id: uuid.UUID | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.upper()
        if not CODE_RE.match(value):
            raise ValueError("Use up to 10 letters or digits (/, _ and - allowed after the first)")
        return value

    @model_validator(mode="after")
    def _exit(self):
        if self.status == SchemeStatus.exited and self.exit_date is None:
            raise ValueError("Give the date the employer left the fund")
        if self.exit_date and self.join_date and self.exit_date < self.join_date:
            raise ValueError("The exit date can't be before the join date")
        return self


class OfficerOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    # Invited but hasn't chosen a password yet.
    awaiting_setup: bool = False
    # Other employers (any fund) this officer acts for.
    other_scheme_count: int = 0


class SchemeSummaryOut(BaseModel):
    id: uuid.UUID
    fund_id: uuid.UUID
    code: str
    name: str
    status: SchemeStatus
    contribution_day: int
    billing_frequency: BillingFrequency
    contact_name: str | None
    officer_count: int
    pending_approval_id: uuid.UUID | None


class SchemeOut(SchemeSummaryOut):
    fund_code: str
    fund_name: str
    registration_number: str | None
    tpin: str | None
    join_date: date | None
    exit_date: date | None
    address_line1: str | None
    address_line2: str | None
    address_line3: str | None
    phone: str | None
    email: str | None
    contact_email: str | None
    contact_phone: str | None
    officers: list[OfficerOut]
    party_id: uuid.UUID | None
    kyc: dict
    member_count: int
    can_edit: bool
