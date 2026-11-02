import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.contribution import PaymentMethod, ReceiptSource, ReceiptStatus, ScheduleSource, ScheduleStatus


class ReceiptCaptureIn(BaseModel):
    scheme_id: uuid.UUID | None = None
    payment_method: PaymentMethod
    payment_date: date
    value_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    bank_account_id: uuid.UUID
    payer_name: str | None = Field(None, max_length=200)
    payer_reference: str | None = Field(None, max_length=80)
    bank_reference: str | None = Field(None, max_length=80)
    contribution_month: date | None = None
    notes: str | None = Field(None, max_length=2000)


class ReceiptConfirmIn(BaseModel):
    """Staff confirming a principal officer's payment notice."""

    value_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    bank_account_id: uuid.UUID
    bank_reference: str | None = Field(None, max_length=80)
    contribution_month: date | None = None
    notes: str | None = Field(None, max_length=2000)


class DeclineIn(BaseModel):
    reason: str = Field(max_length=2000)


class IdentifyIn(BaseModel):
    scheme_id: uuid.UUID
    note: str | None = Field(None, max_length=2000)


class ReceiptOut(BaseModel):
    id: uuid.UUID
    fund_id: uuid.UUID
    fund_code: str
    scheme_id: uuid.UUID | None
    employer: str | None
    status: ReceiptStatus
    source: ReceiptSource
    receipt_number: str | None
    notice_number: str | None
    payment_method: PaymentMethod
    notified_amount: Decimal | None
    amount: Decimal | None
    allocated_amount: Decimal
    unallocated: Decimal
    payment_date: date
    value_date: date | None
    bank_account_id: uuid.UUID | None
    bank_account: str | None
    payer_name: str | None
    payer_reference: str | None
    bank_reference: str | None
    contribution_month: date | None
    notes: str | None
    has_proof: bool
    proof_filename: str | None
    notified_by: str | None
    captured_by: str | None
    confirmed_by: str | None
    confirmed_at: datetime | None
    created_at: datetime
    rejection_reason: str | None
    approval_request_id: uuid.UUID | None
    journal_reference: str | None
    can_confirm: bool = False
    can_identify: bool = False


class AgeingBucketOut(BaseModel):
    label: str
    count: int
    amount: Decimal


class ReceiptPage(BaseModel):
    items: list[ReceiptOut]
    total: int
    unallocated_ageing: list[AgeingBucketOut]
    notices_waiting: int


class ScheduleCreateIn(BaseModel):
    scheme_id: uuid.UUID
    contribution_month: date
    supplementary: bool = False
    notes: str | None = Field(None, max_length=2000)
    # Start with a line per expected member at the expected amounts.
    prefill: bool = True


class ScheduleLineIn(BaseModel):
    account_code: str | None = Field(None, max_length=20)
    employee_no: str | None = Field(None, max_length=30)
    member_name: str | None = Field(None, max_length=200)
    pensionable_salary: Decimal | None = Field(None, ge=0, max_digits=18, decimal_places=2)
    employee: Decimal = Field(Decimal("0"), max_digits=18, decimal_places=2)
    employer: Decimal = Field(Decimal("0"), max_digits=18, decimal_places=2)
    voluntary: Decimal = Field(Decimal("0"), max_digits=18, decimal_places=2)
    severance: Decimal = Field(Decimal("0"), max_digits=18, decimal_places=2)


class ScheduleLineOut(BaseModel):
    id: uuid.UUID
    row_no: int
    member_id: uuid.UUID | None
    account_code: str | None
    employee_no: str | None
    member_name: str | None
    pensionable_salary: Decimal | None
    employee: Decimal
    employer: Decimal
    voluntary: Decimal
    severance: Decimal
    total: Decimal
    errors: list[str]
    warnings: list[str]

    model_config = {"from_attributes": True}


class ScheduleSummaryOut(BaseModel):
    id: uuid.UUID
    fund_id: uuid.UUID
    scheme_id: uuid.UUID
    employer: str
    contribution_month: date
    supplementary: bool
    reference: str
    status: ScheduleStatus
    source: ScheduleSource
    filename: str | None
    total_employee: Decimal
    total_employer: Decimal
    total_voluntary: Decimal
    total_severance: Decimal
    total: Decimal
    line_count: int
    error_count: int
    warning_count: int
    created_by: str | None
    created_at: datetime
    submitted_by: str | None
    submitted_at: datetime | None


class ScheduleOut(ScheduleSummaryOut):
    notes: str | None
    lines: list[ScheduleLineOut]
    can_edit: bool


class SchedulePage(BaseModel):
    items: list[ScheduleSummaryOut]
    total: int


class FeeLineOut(BaseModel):
    code: str
    name: str
    fee_type: str
    payer: str
    rate: Decimal
    amount: Decimal
    gl_code: str


class CandidateReceiptOut(BaseModel):
    receipt_id: uuid.UUID
    receipt_number: str
    value_date: date
    amount: Decimal
    available: Decimal
    suggested: Decimal


class AllocationOut(BaseModel):
    id: uuid.UUID
    status: str
    amount: Decimal
    net_to_members: Decimal
    journal_reference: str | None
    approval_request_id: uuid.UUID | None
    created_by: str | None
    approved_by: str | None
    posted_at: datetime | None
    receipts: list[str]


class AllocationPreviewOut(BaseModel):
    schedule_total: Decimal
    member_fees: Decimal
    employer_fees: Decimal
    needed: Decimal
    net_to_members: Decimal
    fees: list[FeeLineOut]
    candidates: list[CandidateReceiptOut]
    available_total: Decimal
    # Why it can't be allocated now (None when it can).
    blocker: str | None
    allocations: list[AllocationOut]
    pending_reversal_approval_id: uuid.UUID | None = None


class AllocationPickIn(BaseModel):
    receipt_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class AllocateIn(BaseModel):
    # None = take the employer's receipts oldest first.
    receipts: list[AllocationPickIn] | None = None


class ReverseIn(BaseModel):
    reason: str = Field(max_length=2000)
