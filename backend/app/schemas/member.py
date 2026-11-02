import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.member import AssignmentReason, MemberStatus
from app.schemas.fund import _Clean

GENDERS = ("female", "male")
CIVIL_STATUSES = ("single", "married", "divorced", "widowed")
CONTACT_MODES = ("phone", "sms", "email", "post")


class MemberDetailsIn(_Clean):
    """Everything about the person that a data correction may change (FR-MEM-001/002/004).
    Employer/category moves and status changes have their own requests."""

    party_id: uuid.UUID | None = None
    old_member_no: str | None = Field(default=None, max_length=30)
    employee_no: str | None = Field(default=None, max_length=30)
    upid: str | None = Field(default=None, max_length=40)
    bi_upid: str | None = Field(default=None, max_length=40)
    is_group_account: bool = False
    group_account_id: uuid.UUID | None = None

    salutation: str | None = Field(default=None, max_length=20)
    first_name: str = Field(min_length=1, max_length=80)
    other_names: str | None = Field(default=None, max_length=120)
    maiden_name: str | None = Field(default=None, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    gender: str
    date_of_birth: date
    nationality: str | None = Field(default=None, min_length=2, max_length=2)
    id_type: str | None = Field(default=None, max_length=20)
    id_number: str | None = Field(default=None, max_length=40)
    civil_status_on_entry: str | None = None
    civil_status_current: str | None = None
    civil_status_foreign: str | None = Field(default=None, max_length=40)
    birth_district_id: uuid.UUID | None = None
    birth_village: str | None = Field(default=None, max_length=120)

    postal_address: str | None = Field(default=None, max_length=200)
    postal_district_id: uuid.UUID | None = None
    postal_village: str | None = Field(default=None, max_length=120)
    physical_address: str | None = Field(default=None, max_length=200)
    home_district_id: uuid.UUID | None = None
    home_ta_id: uuid.UUID | None = None
    home_village_id: uuid.UUID | None = None
    telephone: str | None = Field(default=None, max_length=40)
    mobile: str | None = Field(default=None, max_length=40)
    fax: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    preferred_contact: str | None = None

    bank_id: uuid.UUID | None = None
    bank_branch_id: uuid.UUID | None = None
    bank_account_name: str | None = Field(default=None, max_length=200)
    bank_account_number: str | None = Field(default=None, max_length=40)

    next_of_kin_name: str | None = Field(default=None, max_length=200)
    next_of_kin_relationship: str | None = Field(default=None, max_length=20)
    next_of_kin_phone: str | None = Field(default=None, max_length=40)
    next_of_kin_email: EmailStr | None = None

    date_joined_fund: date
    date_joined_employer: date | None = None
    regulatory_data: dict[str, str] = Field(default_factory=dict, max_length=50)

    @field_validator("gender")
    @classmethod
    def _gender(cls, value: str) -> str:
        if value not in GENDERS:
            raise ValueError("Choose female or male")
        return value

    @field_validator("civil_status_on_entry", "civil_status_current")
    @classmethod
    def _civil(cls, value: str | None) -> str | None:
        if value is not None and value not in CIVIL_STATUSES:
            raise ValueError("Choose single, married, divorced or widowed")
        return value

    @field_validator("preferred_contact")
    @classmethod
    def _contact(cls, value: str | None) -> str | None:
        if value is not None and value not in CONTACT_MODES:
            raise ValueError("Choose phone, SMS, email or post")
        return value

    @field_validator("nationality")
    @classmethod
    def _nationality(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("regulatory_data")
    @classmethod
    def _regulatory(cls, value: dict[str, str]) -> dict[str, str]:
        clean = {}
        for k, v in value.items():
            k, v = (k or "").strip(), (v or "").strip()
            if not k:
                continue
            if len(k) > 60 or len(v) > 200:
                raise ValueError("Regulatory data: names up to 60 characters, values up to 200")
            clean[k] = v
        return clean


class MemberCreateIn(MemberDetailsIn):
    scheme_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    # Leave empty to generate one (<fund code><6 digits>); give it when loading legacy members.
    account_code: str | None = Field(default=None, max_length=20)

    @field_validator("account_code")
    @classmethod
    def _account_code(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class StatusChangeIn(_Clean):
    to_status: MemberStatus
    effective_date: date
    reason: str = Field(min_length=3, max_length=1000)


class DuplicateOut(BaseModel):
    member_id: uuid.UUID
    account_code: str
    full_name: str
    date_of_birth: date
    fund_code: str
    employer: str | None
    status: MemberStatus
    match: str


class MemberSummaryOut(BaseModel):
    id: uuid.UUID
    fund_id: uuid.UUID
    fund_code: str
    account_code: str
    full_name: str
    employee_no: str | None
    id_number_masked: str | None
    date_of_birth: date
    employer_code: str | None
    category_code: str | None
    status: MemberStatus
    date_joined_fund: date
    pending_approval_id: uuid.UUID | None


class KycStatusOut(BaseModel):
    # none | current | review_overdue | document_expired
    state: str
    label: str
    party_id: uuid.UUID | None = None
    party_name: str | None = None
    risk_rating: str | None = None
    review_due: date | None = None
    application_id: uuid.UUID | None = None
    application_reference: str | None = None
    # Why benefit payments are blocked, if they are.
    payment_block: str | None = None


class StatusChangeOut(BaseModel):
    id: uuid.UUID
    from_status: MemberStatus | None
    to_status: MemberStatus
    effective_date: date
    reason: str
    requested_by: str | None
    approved_by: str | None
    created_at: datetime


class AssignmentOut(BaseModel):
    id: uuid.UUID
    employer: str | None
    category: str | None
    effective_from: date
    effective_to: date | None
    reason: AssignmentReason
    note: str | None


class MemberOut(BaseModel):
    """The record with display names for every reference. Sensitive values
    (ID number, bank account) are masked unless `sensitive` is true."""

    id: uuid.UUID
    sensitive: bool
    fields: dict
    labels: dict
    fund: dict
    company: dict
    kyc: KycStatusOut
    status: MemberStatus
    allowed_transitions: list[MemberStatus]
    status_history: list[StatusChangeOut]
    assignments: list[AssignmentOut]
    pending_approval_id: uuid.UUID | None
    can_edit: bool
