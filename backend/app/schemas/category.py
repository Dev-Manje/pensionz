import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.category import BenefitDesign, CategoryStatus, RateType, SalaryBasis
from app.schemas.fund import CODE_RE


class VestingStep(BaseModel):
    years: int = Field(ge=0, le=60)
    vested_pct: Decimal = Field(ge=0, le=100)


class TermsIn(BaseModel):
    """A category's rules from `effective_from`."""

    effective_from: date
    employee_rate_type: RateType = RateType.percent
    employee_rate: Decimal = Field(ge=0)
    employer_rate_type: RateType = RateType.percent
    employer_rate: Decimal | None = Field(default=None, ge=0)
    salary_basis: SalaryBasis = SalaryBasis.basic
    normal_retirement_age: int = Field(ge=40, le=80)
    min_entry_age: int | None = Field(default=None, ge=14, le=80)
    max_entry_age: int | None = Field(default=None, ge=14, le=80)
    waiting_period_months: int = Field(default=0, ge=0, le=60)
    vesting_scale: list[VestingStep] = Field(default_factory=list, max_length=30)
    default_investment_option_id: uuid.UUID | None = None
    member_choice_allowed: bool = False
    avc_allowed: bool = True
    group_life_multiple: Decimal | None = Field(default=None, ge=0, le=20)
    accrual_denominator: int | None = Field(default=None, ge=1, le=200)
    final_salary_months: int | None = Field(default=None, ge=1, le=240)

    @model_validator(mode="after")
    def _checks(self):
        if self.min_entry_age and self.max_entry_age and self.min_entry_age > self.max_entry_age:
            raise ValueError("The youngest entry age can't be above the oldest")
        if self.max_entry_age and self.max_entry_age >= self.normal_retirement_age:
            raise ValueError("The oldest entry age must be below the normal retirement age")
        years = [s.years for s in self.vesting_scale]
        if years != sorted(set(years)):
            raise ValueError("Vesting steps must be in order of years of service, each year once")
        pcts = [s.vested_pct for s in self.vesting_scale]
        if pcts != sorted(pcts):
            raise ValueError("The vested share can't go down as service grows")
        if self.employee_rate_type == RateType.percent and self.employee_rate > 100:
            raise ValueError("The employee rate can't be above 100%")
        if self.employer_rate_type == RateType.percent and self.employer_rate is not None and self.employer_rate > 100:
            raise ValueError("The employer rate can't be above 100%")
        return self


class CategoryIn(BaseModel):
    code: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=2, max_length=120)
    terms: TermsIn

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.strip().upper()
        if not CODE_RE.match(value):
            raise ValueError("Use up to 10 letters or digits (/, _ and - allowed after the first)")
        return value


class CategoryChangeIn(BaseModel):
    """Rename or close a category, and/or give it new terms from a date."""

    name: str = Field(min_length=2, max_length=120)
    status: CategoryStatus
    terms: TermsIn | None = None


class TermsOut(BaseModel):
    id: uuid.UUID
    effective_from: date
    design: BenefitDesign
    employee_rate_type: RateType
    employee_rate: Decimal
    employer_rate_type: RateType
    employer_rate: Decimal | None
    salary_basis: SalaryBasis
    normal_retirement_age: int
    min_entry_age: int | None
    max_entry_age: int | None
    waiting_period_months: int
    vesting_scale: list[VestingStep]
    default_investment_option_id: uuid.UUID | None
    default_investment_option: str | None
    member_choice_allowed: bool
    avc_allowed: bool
    group_life_multiple: Decimal | None
    accrual_denominator: int | None
    final_salary_months: int | None


class CategoryOut(BaseModel):
    id: uuid.UUID
    scheme_id: uuid.UUID
    fund_id: uuid.UUID
    code: str
    name: str
    status: CategoryStatus
    design: BenefitDesign
    current: TermsOut | None
    upcoming: TermsOut | None
    history: list[TermsOut]
    pending_approval_id: uuid.UUID | None
