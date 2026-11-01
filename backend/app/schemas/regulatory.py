import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.regulatory import TaxTableKind


class ParameterVersionOut(BaseModel):
    id: uuid.UUID
    value: Decimal
    display: str
    effective_from: date
    source: str | None


class ParameterOut(BaseModel):
    key: str
    label: str
    unit: str
    group: str
    help: str
    minimum: Decimal
    maximum: Decimal
    current: ParameterVersionOut | None
    # A version that starts after today, if one is scheduled.
    upcoming: ParameterVersionOut | None
    versions: list[ParameterVersionOut]
    pending_approval_id: uuid.UUID | None


class ParameterVersionIn(BaseModel):
    value: Decimal
    effective_from: date
    source: str | None = Field(default=None, max_length=500)


class TaxBandIn(BaseModel):
    lower: Decimal = Field(ge=0)
    rate_pct: Decimal = Field(ge=0, le=100)


class TaxBandOut(TaxBandIn):
    upper: Decimal | None


class TaxTableOut(BaseModel):
    id: uuid.UUID
    kind: TaxTableKind
    effective_from: date
    source: str | None
    bands: list[TaxBandOut]


class TaxTablesOut(BaseModel):
    kind: TaxTableKind
    label: str
    current: TaxTableOut | None
    upcoming: TaxTableOut | None
    versions: list[TaxTableOut]
    pending_approval_id: uuid.UUID | None


class TaxTableIn(BaseModel):
    effective_from: date
    source: str | None = Field(default=None, max_length=500)
    bands: list[TaxBandIn] = Field(min_length=1, max_length=20)


class TaxCalcOut(BaseModel):
    amount: Decimal
    tax: Decimal
    table_effective_from: date | None
