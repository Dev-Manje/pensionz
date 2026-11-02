import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.contribution import PaymentMethod, ReceiptSource, ReceiptStatus


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
