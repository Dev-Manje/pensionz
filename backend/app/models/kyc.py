"""Client onboarding & KYC (FR-ONB). An application collects one client's
details and documents (corporate, group or individual); compliance reviews it;
approval creates (or refreshes) the `Party` — the client the rest of the
system links to (employers in Phase 3/5, members in Phase 3/7)."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPKMixin, str_enum


class ClientType(str, enum.Enum):
    corporate = "corporate"
    group = "group"
    individual = "individual"


class ApplicationStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    in_review = "in_review"
    # Sent back to the applicant to fix details or re-upload documents.
    returned = "returned"
    # High risk: compliance recommends approval, an administrator must approve (EDD).
    awaiting_senior_approval = "awaiting_senior_approval"
    approved = "approved"
    rejected = "rejected"


class RiskRating(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class DocumentReview(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class DeclarationVersion(UUIDPKMixin, CreatedAtMixin, Base):
    """The declaration an applicant accepts, kept word for word per version."""

    __tablename__ = "declaration_version"
    __table_args__ = (UniqueConstraint("client_type", "version", name="uq_declaration_version"),)

    client_type: Mapped[ClientType] = mapped_column(str_enum(ClientType, 20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)


class Party(UUIDPKMixin, TimestampMixin, Base):
    """An approved client. KYC review dates and risk live here; the
    application that last refreshed it is kept for the evidence."""

    __tablename__ = "party"

    client_type: Mapped[ClientType] = mapped_column(str_enum(ClientType, 20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # Registration number (corporate) or ID number (individual), for staff-side duplicate matching.
    identifier: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    risk_rating: Mapped[RiskRating] = mapped_column(str_enum(RiskRating, 10), nullable=False)
    is_pep: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kyc_approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kyc_review_due: Mapped[date] = mapped_column(Date, nullable=False)
    latest_application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class KycApplication(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "kyc_application"

    reference: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    client_type: Mapped[ClientType] = mapped_column(str_enum(ClientType, 20), nullable=False)
    status: Mapped[ApplicationStatus] = mapped_column(str_enum(ApplicationStatus, 30), nullable=False, default=ApplicationStatus.draft, index=True)
    # The applicant's answers, shaped per client type (services/kyc_forms.py); checked fully on submit.
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # Staff capturing a paper form, or the portal user applying for themselves / their organisation.
    captured_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    applicant_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True, index=True)
    # Refreshing an existing client's KYC.
    party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("party.id"), nullable=True, index=True)

    declaration_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("declaration_version.id"), nullable=True)
    declaration_accepted_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    declaration_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declaration_accepted_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    risk_rating: Mapped[RiskRating | None] = mapped_column(str_enum(RiskRating, 10), nullable=True)
    # Why the rules gave that rating, e.g. ["Director is a politically exposed person"].
    risk_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    edd_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents: Mapped[list["KycDocument"]] = relationship(
        back_populates="application", lazy="selectin", order_by="KycDocument.uploaded_at"
    )


class KycDocument(UUIDPKMixin, Base):
    """One uploaded piece of evidence for a requirement (services/kyc_forms.REQUIREMENTS).
    A re-upload supersedes the earlier file, which is kept for the record."""

    __tablename__ = "kyc_document"

    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kyc_application.id"), nullable=False, index=True)
    # e.g. "proof_of_address", or "director_id:2" for the third director.
    requirement: Mapped[str] = mapped_column(String(60), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(60), nullable=False)
    # When doc_type is "other": what the document is.
    doc_type_other: Mapped[str | None] = mapped_column(String(120), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[DocumentReview] = mapped_column(str_enum(DocumentReview, 10), nullable=False, default=DocumentReview.pending)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    application: Mapped["KycApplication"] = relationship(back_populates="documents")
