import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.ledger import AccountClass, Component
from app.models.reference import TransactionEffect


class AccountBalanceOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    account_class: AccountClass
    debit: Decimal
    credit: Decimal
    balance: Decimal


class TieOutOut(BaseModel):
    debits: Decimal
    credits: Decimal
    balanced: bool
    member_credits_gl: Decimal
    member_sub_ledger: Decimal
    ties: bool


class ChartOut(BaseModel):
    accounts: list[AccountBalanceOut]
    tie_out: TieOutOut
    # Reminder shown on screen until finance confirms the chart (TASKS.md open decision).
    chart_status: str = "proposed"


class LedgerLineOut(BaseModel):
    code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    member_id: uuid.UUID | None
    member_code: str | None = None
    component: Component | None
    description: str | None


class JournalEntryOut(BaseModel):
    id: uuid.UUID
    reference: str
    entry_date: date
    period: date
    entity_type: str
    entity_id: str | None
    description: str
    total: Decimal
    reverses: str | None = None
    reversed_by: str | None = None
    created_by: str | None = None
    lines: list[LedgerLineOut]


class JournalPage(BaseModel):
    items: list[JournalEntryOut]
    total: int


class MemberTransactionOut(BaseModel):
    id: uuid.UUID
    transaction_date: date
    period: date
    transaction_code: int
    transaction_name: str
    effect: TransactionEffect
    component: Component
    amount: Decimal
    contribution_month: date | None
    reference: str | None
    description: str | None
    journal_reference: str
    reversed: bool
    is_reversal: bool


class ComponentBalanceOut(BaseModel):
    component: Component
    contributions: Decimal
    bonus: Decimal
    withdrawals: Decimal
    other: Decimal
    balance: Decimal


class MemberLedgerOut(BaseModel):
    balance: Decimal
    components: list[ComponentBalanceOut]
    transactions: list[MemberTransactionOut]
    total: int
