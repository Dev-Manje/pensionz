import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.kyc import ApplicationStatus, ClientType, DocumentReview, RiskRating


class ApplicationCreate(BaseModel):
    client_type: ClientType
    data: dict = Field(default_factory=dict)


class ApplicationSave(BaseModel):
    data: dict


class SubmitIn(BaseModel):
    declaration_version_id: uuid.UUID
    # The person accepting, typed in full.
    accepted_by: str = Field(min_length=2, max_length=200)


class DocumentOut(BaseModel):
    id: uuid.UUID
    requirement: str
    doc_type: str
    doc_type_label: str
    doc_type_other: str | None
    issue_date: date | None
    expiry_date: date | None
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    uploaded_by: str | None
    review_status: DocumentReview
    review_reason: str | None
    reviewed_by: str | None


class DocTypeOut(BaseModel):
    code: str
    label: str
    max_age_months: int | None


class SlotOut(BaseModel):
    key: str
    label: str
    person: str | None
    types: list[DocTypeOut]
    issue_date: bool
    expiry_date: bool
    document: DocumentOut | None
    problems: list[str]


class PartyRef(BaseModel):
    id: uuid.UUID
    name: str
    identifier: str | None
    risk_rating: RiskRating
    kyc_review_due: date


class ApplicationSummary(BaseModel):
    id: uuid.UUID
    reference: str
    client_type: ClientType
    status: ApplicationStatus
    display_name: str
    captured_by: str | None
    applicant: str | None
    submitted_at: datetime | None
    risk_rating: RiskRating | None
    edd_required: bool
    reviewer: str | None
    updated_at: datetime


class ApplicationOut(ApplicationSummary):
    data: dict
    risk_reasons: list[str]
    review_note: str | None
    recommended_by: str | None
    decided_by: str | None
    decided_at: datetime | None
    decision_reason: str | None
    declaration_accepted_by: str | None
    declaration_accepted_at: datetime | None
    declaration_version: int | None
    party: PartyRef | None
    slots: list[SlotOut]
    # Everything still missing before it can be submitted (empty when complete).
    problems: list[str]
    # Staff only: existing clients with the same name or identifier.
    possible_duplicates: list[PartyRef]
    # A change to an approved client: answers that differ from the last approved application (field names).
    changed_fields: list[str] = []
    # Made from the principal officer portal for this employer.
    scheme_id: uuid.UUID | None = None
    # Refreshes an approved client (a change of details) rather than onboarding a new one.
    is_change: bool = False
    can_edit: bool
    can_start_review: bool
    can_review: bool
    can_senior_decide: bool


class ExpiringOut(BaseModel):
    kind: str
    party_id: uuid.UUID
    party_name: str
    label: str
    due: date
    days_left: int
    application_id: uuid.UUID | None


class DeclarationOut(BaseModel):
    id: uuid.UUID
    client_type: ClientType
    version: int
    title: str
    body: str


class DocumentReviewIn(BaseModel):
    accept: bool
    reason: str | None = None


class NoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class ApproveIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    risk_override: RiskRating | None = None


class SeniorDecisionIn(BaseModel):
    approve: bool
    reason: str | None = Field(default=None, max_length=2000)
