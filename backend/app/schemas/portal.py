import uuid

from pydantic import BaseModel

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
