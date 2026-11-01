import uuid
from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.models.investment import InvestmentOptionStatus, PricingMethod
from app.schemas.fund import CODE_RE, _Clean


class InvestmentOptionIn(_Clean):
    code: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=2, max_length=120)
    pricing_method: PricingMethod = PricingMethod.declared_rate
    status: InvestmentOptionStatus = InvestmentOptionStatus.active
    launch_date: date | None = None
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.upper()
        if not CODE_RE.match(value):
            raise ValueError("Use up to 10 letters or digits (/, _ and - allowed after the first)")
        return value


class InvestmentOptionOut(BaseModel):
    id: uuid.UUID
    fund_id: uuid.UUID
    code: str
    name: str
    pricing_method: PricingMethod
    status: InvestmentOptionStatus
    launch_date: date | None
    description: str | None
    pending_approval_id: uuid.UUID | None
