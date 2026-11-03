import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.category import SalaryBasis
from app.models.scheme import BillingFrequency, EmployerApplicationStatus
from app.schemas.category import TermsIn
from app.schemas.fund import CODE_RE, _Clean


class ApplicationDetailsIn(_Clean):
    """The organisation as the officer proposes it. Only the name is needed to
    save a draft; the rest is checked when the application is sent."""

    name: str = Field(min_length=2, max_length=200)
    registration_number: str | None = Field(default=None, max_length=60)
    tpin: str | None = Field(default=None, max_length=30)
    address_line1: str | None = Field(default=None, max_length=120)
    address_line2: str | None = Field(default=None, max_length=120)
    address_line3: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=40)
    contribution_day: int | None = Field(default=None, ge=1, le=28)
    billing_frequency: BillingFrequency = BillingFrequency.monthly
    # First month the employer will pay contributions for.
    join_date: date | None = None


class ProposedCategoryIn(_Clean):
    name: str = Field(min_length=2, max_length=120)
    # Percent of pensionable salary.
    employee_rate: Decimal = Field(ge=0, le=100)
    employer_rate: Decimal = Field(ge=0, le=100)
    salary_basis: SalaryBasis = SalaryBasis.basic
    normal_retirement_age: int = Field(ge=40, le=80)


class EmployerApplicationIn(BaseModel):
    fund_id: uuid.UUID
    details: ApplicationDetailsIn
    categories: list[ProposedCategoryIn] = Field(default_factory=list, max_length=10)


class FinalCategoryIn(BaseModel):
    code: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=2, max_length=120)
    terms: TermsIn

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.upper()
        if not CODE_RE.match(value):
            raise ValueError("Use up to 10 letters or digits (/, _ and - allowed after the first)")
        return value


class FinalTermsIn(BaseModel):
    """What scheme setup sends to the checker: the employer code and the final
    categories with full terms (the officer's proposal, possibly changed)."""

    code: str = Field(min_length=1, max_length=10)
    join_date: date
    categories: list[FinalCategoryIn] = Field(min_length=1, max_length=10)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.upper()
        if not CODE_RE.match(value):
            raise ValueError("Use up to 10 letters or digits (/, _ and - allowed after the first)")
        return value


class NoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class ApplicationFundOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    fund_type: str


class EmployerApplicationOut(BaseModel):
    id: uuid.UUID
    reference: str
    status: EmployerApplicationStatus
    fund_id: uuid.UUID
    fund_code: str
    fund_name: str
    officer_name: str
    officer_email: str
    details: dict
    categories: list
    final_terms: dict | None
    kyc_application_id: uuid.UUID | None
    kyc_reference: str | None
    kyc_status: str | None
    scheme_id: uuid.UUID | None
    review_note: str | None
    submitted_at: datetime | None
    decided_at: datetime | None
    created_at: datetime
    # What still stops the officer sending it, or scheme setup approving it.
    problems: list[str] = []
    pending_approval_id: uuid.UUID | None = None
    can_edit: bool = False
