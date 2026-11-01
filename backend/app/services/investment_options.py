"""Investment options per fund (FR-CFG-007) via the shared FundConfig
maker-checker (approval kind "investment_option")."""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.fund import Fund, FundType
from app.models.investment import InvestmentOption, InvestmentOptionStatus, PricingMethod
from app.services.config_changes import FundConfig, as_date, enum_of


def _validate(db: Session, fund: Fund, values: dict, existing: InvestmentOption | None) -> None:
    if fund.fund_type == FundType.defined_benefit:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Defined benefit funds don't have member investment options")
    if existing is None and values["status"] != InvestmentOptionStatus.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A new investment option starts as active")
    if existing is not None and existing.pricing_method != values["pricing_method"]:
        # Money already credited under one method can't silently switch to the other.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The pricing method can't change — close this option and add a new one")


OPTIONS = FundConfig(
    kind="investment_option",
    label="Investment option",
    model=InvestmentOption,
    fields=("code", "name", "pricing_method", "status", "launch_date", "description"),
    converters={"pricing_method": enum_of(PricingMethod), "status": enum_of(InvestmentOptionStatus), "launch_date": as_date},
    validate=_validate,
)
