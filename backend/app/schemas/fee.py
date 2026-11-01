import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.fee import FeeBasis, FeeFrequency, FeePayer, FeeType
from app.schemas.fund import CODE_RE, _Clean

SIX_DP = Decimal("0.000001")


class FeeRuleIn(_Clean):
    code: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=2, max_length=120)
    scheme_id: uuid.UUID | None = None
    fee_type: FeeType
    basis: FeeBasis
    rate: Decimal = Field(ge=0)
    payer: FeePayer
    frequency: FeeFrequency
    effective_from: date
    effective_to: date | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.upper()
        if not CODE_RE.match(value):
            raise ValueError("Use up to 10 letters or digits (/, _ and - allowed after the first)")
        return value

    @field_validator("rate")
    @classmethod
    def _rate(cls, value: Decimal) -> Decimal:
        # Stored to 6 dp, so compare like with like when spotting changes.
        return value.quantize(SIX_DP)


class FeeRuleOut(BaseModel):
    id: uuid.UUID
    fund_id: uuid.UUID
    code: str
    name: str
    scheme_id: uuid.UUID | None
    employer: str | None
    fee_type: FeeType
    basis: FeeBasis
    rate: Decimal
    payer: FeePayer
    frequency: FeeFrequency
    effective_from: date
    effective_to: date | None
    pending_approval_id: uuid.UUID | None
