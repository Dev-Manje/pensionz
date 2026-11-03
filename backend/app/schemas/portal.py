import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.contribution import PaymentMethod, ReceiptStatus, ScheduleStatus
from app.models.kyc import ApplicationStatus
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
