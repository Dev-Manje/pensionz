import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.models.contribution import PaymentMethod, ReceiptStatus, ScheduleStatus
from app.models.approval import ApprovalStatus
from app.models.kyc import ApplicationStatus
from app.models.member import MemberStatus
from app.models.scheme import BillingFrequency, SchemeStatus


class PortalSchemeOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: SchemeStatus
    fund_id: uuid.UUID
    fund_code: str
    fund_name: str
    contribution_day: int
    billing_frequency: BillingFrequency
    member_count: int


class CurrentRemittanceOut(BaseModel):
    """Last month's contributions, due this month."""

    month: date
    due_date: date
    # Negative once the due date has passed.
    days_to_due: int
    # not_started | payment_only | draft | awaiting_allocation | allocated
    stage: str
    schedule_id: uuid.UUID | None
    schedule_reference: str | None
    schedule_total: Decimal | None
    member_lines: int
    # Payment notices not yet confirmed by the administrator.
    notified_amount: Decimal
    # Receipts issued.
    confirmed_amount: Decimal


class ArrearsSummaryOut(BaseModel):
    total: Decimal
    # None when no late-payment interest rate is configured.
    interest: Decimal | None
    overdue_months: int
    oldest_month: date | None
    oldest_days_overdue: int | None


class DashboardSchemeOut(PortalSchemeOut):
    current: CurrentRemittanceOut
    arrears: ArrearsSummaryOut


class ActivityOut(BaseModel):
    at: datetime
    scheme_id: uuid.UUID
    scheme_name: str
    # notice_sent | payment_confirmed | notice_rejected | schedule_sent | allocated | allocation_reversed
    kind: str
    title: str
    detail: str | None
    # Where the officer opens it in the portal.
    link: str | None = None


class PoDashboardOut(BaseModel):
    as_at: date
    schemes: list[DashboardSchemeOut]
    activity: list[ActivityOut]


class PortalKycApplicationOut(BaseModel):
    id: uuid.UUID
    reference: str
    status: ApplicationStatus
    # A change to details already approved (otherwise the employer's first KYC).
    is_change: bool
    submitted_at: datetime | None
    decided_at: datetime | None
    review_note: str | None
    decision_reason: str | None
    updated_at: datetime


class LabelValue(BaseModel):
    label: str
    value: str


class PortalPersonOut(BaseModel):
    name: str
    role: str | None


class PortalDocumentOut(BaseModel):
    label: str
    type_label: str
    issue_date: date | None
    expiry_date: date | None
    # current | due_soon (within 60 days) | expired; None when the document doesn't expire
    state: str | None


class OrganisationOut(BaseModel):
    scheme_id: uuid.UUID
    scheme_name: str
    # False until the employer's KYC has been approved and linked.
    has_client: bool
    approved_at: datetime | None
    review_due: date | None
    # current | due_soon (within 60 days) | overdue
    review_state: str | None
    approved_reference: str | None
    details: list[LabelValue]
    people_title: str
    people: list[PortalPersonOut]
    documents: list[PortalDocumentOut]
    in_progress: PortalKycApplicationOut | None
    history: list[PortalKycApplicationOut]


# ---- remittances (FR-PRT-001)


class RemittanceScheduleOut(BaseModel):
    id: uuid.UUID
    reference: str
    month: date
    supplementary: bool
    status: ScheduleStatus
    total: Decimal
    line_count: int
    error_count: int
    submitted_at: datetime | None
    # When the contributions were credited to members (allocation posted).
    credited_at: datetime | None
    # Started in the portal (otherwise prepared by the administrator — read-only here).
    from_portal: bool
    editable: bool


class PaymentOut(BaseModel):
    id: uuid.UUID
    notice_number: str | None
    receipt_number: str | None
    status: ReceiptStatus
    month: date | None
    notified_amount: Decimal | None
    amount: Decimal | None
    payment_date: date
    value_date: date | None
    payment_method: PaymentMethod
    payer_reference: str | None
    rejection_reason: str | None
    has_proof: bool
    created_at: datetime


class RemittanceMonthOut(BaseModel):
    # None: payments that didn't say which month they were for.
    month: date | None
    stage: str
    schedules: list[RemittanceScheduleOut]
    payments: list[PaymentOut]
    schedule_total: Decimal
    # Confirmed by the administrator.
    paid: Decimal
    # Notified, not confirmed yet.
    noted: Decimal


class PaymentDetailOut(PaymentOut):
    scheme_id: uuid.UUID
    scheme_name: str
    notes: str | None
    proof_filename: str | None
    confirmed_at: datetime | None
    can_add_proof: bool
    # "receipt" | "acknowledgement" | None — the PDF the officer can download.
    document_kind: str | None
    schedules: list[RemittanceScheduleOut]


class StartScheduleIn(BaseModel):
    contribution_month: date
    supplementary: bool = False


class CodeIn(BaseModel):
    code: str = Field(..., pattern=r"^\s*\d{6}\s*$")


class CodeSentOut(BaseModel):
    sent_to: str


class NoticeIn(BaseModel):
    amount: Decimal = Field(..., gt=0, max_digits=18, decimal_places=2)
    payment_date: date
    payment_method: PaymentMethod
    payer_reference: str | None = Field(None, max_length=80)
    contribution_month: date | None = None
    notes: str | None = Field(None, max_length=2000)
    code: str = Field(..., pattern=r"^\s*\d{6}\s*$")


# ---- members (HR-level only)


class PortalMemberOut(BaseModel):
    id: uuid.UUID
    account_code: str
    employee_no: str | None
    full_name: str
    gender: str
    date_of_birth: date
    category: str | None
    status: MemberStatus
    status_label: str
    status_effective: date | None
    date_joined_fund: date
    date_joined_employer: date | None
    # Pensionable salary on record today.
    salary: Decimal | None
    salary_from: date | None
    has_pending_request: bool


class PortalRequestOut(BaseModel):
    id: uuid.UUID
    kind: str
    kind_label: str
    summary: str
    status: ApprovalStatus
    created_at: datetime
    decided_at: datetime | None
    comment: str | None
    member_id: uuid.UUID | None
    requested_by: str | None


class PortalSalaryOut(BaseModel):
    effective_from: date
    basic_salary: Decimal
    pensionable_salary: Decimal


class PortalMemberDetailOut(PortalMemberOut):
    scheme_id: uuid.UUID
    scheme_name: str
    salaries: list[PortalSalaryOut]
    requests: list[PortalRequestOut]
    can_change_salary: bool
    can_give_notice: bool


class PortalCategoryOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class NewMemberIn(BaseModel):
    """What an employer knows about a new employee joining the scheme."""

    first_name: str = Field(min_length=1, max_length=80)
    other_names: str | None = Field(None, max_length=120)
    last_name: str = Field(min_length=1, max_length=80)
    gender: str
    date_of_birth: date
    nationality: str | None = Field(None, min_length=2, max_length=2)
    id_type: str | None = Field(None, max_length=20)
    id_number: str | None = Field(None, max_length=40)
    employee_no: str | None = Field(None, max_length=30)
    category_id: uuid.UUID
    date_joined_employer: date
    date_joined_fund: date
    mobile: str | None = Field(None, max_length=40)
    email: EmailStr | None = None
    physical_address: str | None = Field(None, max_length=200)
    basic_salary: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class ExitNoticeIn(BaseModel):
    # Last working day, or the date of death.
    last_day: date
    # resigned | dismissed | retrenched | contract_ended | retired | ill_health | died | other
    reason: str
    note: str | None = Field(None, max_length=1000)
