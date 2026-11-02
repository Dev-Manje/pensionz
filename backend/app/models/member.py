"""Members (FR-MEM) — the legacy "Account Setup" record and its history.

A member belongs to a fund and, in employer funds, to a participating
employer (scheme) and benefit category. Every change to the record goes
through maker-checker (services/members.py); the history tables keep what
the record looked like before:

- `member_assignment` — which employer/category the member was in, from when;
- `member_status_change` — every status transition with its reason.

Places (home district/TA/village, district of birth, postal district) refer to
the Setup lists; bank and branch to the bank list. Personal pension and minors'
trust funds have no employers, so their members have no scheme or category."""
import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPKMixin, str_enum


class MemberStatus(str, enum.Enum):
    """Legacy Active / Inactive / Deceased, extended (FR-MEM-005)."""

    active = "active"
    # Still employed but not contributing (e.g. unpaid leave).
    inactive = "inactive"
    # Left employment, benefit kept in the fund (paid-up).
    deferred = "deferred"
    # Retired and drawing an in-fund pension.
    pensioner = "pensioner"
    # Benefit paid out or transferred; the record is kept.
    exited = "exited"
    deceased = "deceased"


class AssignmentReason(str, enum.Enum):
    joined = "joined"
    category_move = "category_move"
    employer_transfer = "employer_transfer"


class Member(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "member"
    __table_args__ = (UniqueConstraint("fund_id", "account_code", name="uq_member_fund_account_code"),)

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    scheme_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("scheme.id"), nullable=True, index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("benefit_category.id"), nullable=True, index=True)
    # The approved KYC client (FR-ONB-105); required for personal pension holders.
    party_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("party.id"), nullable=True, index=True)

    # Identifiers
    account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    account_type_code: Mapped[str] = mapped_column(String(10), nullable=False, default="MEM")
    old_member_no: Mapped[str | None] = mapped_column(String(30), nullable=True)
    employee_no: Mapped[str | None] = mapped_column(String(30), nullable=True)
    upid: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bi_upid: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_group_account: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    group_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("member.id"), nullable=True)

    # Person
    salutation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    other_names: Mapped[str | None] = mapped_column(String(120), nullable=True)
    maiden_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    nationality: Mapped[str | None] = mapped_column(String(2), nullable=True)
    id_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    id_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Upper-case without spaces or dashes, for duplicate matching (FR-MEM-011).
    id_number_key: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    civil_status_on_entry: Mapped[str | None] = mapped_column(String(20), nullable=True)
    civil_status_current: Mapped[str | None] = mapped_column(String(20), nullable=True)
    civil_status_foreign: Mapped[str | None] = mapped_column(String(40), nullable=True)
    birth_district_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("district.id"), nullable=True)
    birth_village: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Addresses and contact
    postal_address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    postal_district_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("district.id"), nullable=True)
    postal_village: Mapped[str | None] = mapped_column(String(120), nullable=True)
    physical_address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    home_district_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("district.id"), nullable=True)
    home_ta_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("traditional_authority.id"), nullable=True)
    home_village_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("village.id"), nullable=True)
    telephone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fax: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_contact: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Bank (benefit payments)
    bank_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bank.id"), nullable=True)
    bank_branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bank_branch.id"), nullable=True)
    bank_account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Next of kin
    next_of_kin_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    next_of_kin_relationship: Mapped[str | None] = mapped_column(String(20), nullable=True)
    next_of_kin_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    next_of_kin_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Membership
    date_joined_fund: Mapped[date] = mapped_column(Date, nullable=False)
    date_joined_employer: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[MemberStatus] = mapped_column(str_enum(MemberStatus, 20), nullable=False, default=MemberStatus.active, index=True)
    status_effective: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_of_death: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Regulatory Authority Data tab: free key/value pairs until the regulator's field list is known.
    regulatory_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.other_names, self.last_name) if p)


class MemberStatusChange(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "member_status_change"

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("member.id"), nullable=False, index=True)
    from_status: Mapped[MemberStatus | None] = mapped_column(str_enum(MemberStatus, 20), nullable=True)
    to_status: Mapped[MemberStatus] = mapped_column(str_enum(MemberStatus, 20), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class MemberAssignment(UUIDPKMixin, CreatedAtMixin, Base):
    """The employer and category a member was in over time; the open row
    (`effective_to` empty) matches the member record."""

    __tablename__ = "member_assignment"

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("member.id"), nullable=False, index=True)
    scheme_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("scheme.id"), nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("benefit_category.id"), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[AssignmentReason] = mapped_column(str_enum(AssignmentReason, 30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)


class BeneficiaryNomination(UUIDPKMixin, CreatedAtMixin, Base):
    """One signed nomination form (FR-MEM-008). A new approved nomination
    replaces the current one; earlier versions are kept as history. At death
    the trustees decide — nominations guide, they don't bind."""

    __tablename__ = "beneficiary_nomination"
    __table_args__ = (UniqueConstraint("member_id", "version", name="uq_beneficiary_nomination_version"),)

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("member.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    signed_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    beneficiaries: Mapped[list["Beneficiary"]] = relationship(
        back_populates="nomination", lazy="selectin", order_by="Beneficiary.position", cascade="all, delete-orphan"
    )


class Beneficiary(UUIDPKMixin, Base):
    __tablename__ = "beneficiary"

    nomination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("beneficiary_nomination.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    relationship_code: Mapped[str] = mapped_column("relationship", String(20), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    id_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    share_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    # Required for beneficiaries under 18.
    guardian_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    guardian_relationship: Mapped[str | None] = mapped_column(String(20), nullable=True)
    guardian_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    guardian_id_number: Mapped[str | None] = mapped_column(String(40), nullable=True)

    nomination: Mapped["BeneficiaryNomination"] = relationship(back_populates="beneficiaries")


class MemberSalary(UUIDPKMixin, CreatedAtMixin, Base):
    """Monthly salary from a date (FR-MEM-009); the latest version on or before a date applies."""

    __tablename__ = "member_salary"
    __table_args__ = (UniqueConstraint("member_id", "effective_from", name="uq_member_salary_from"),)

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("member.id"), nullable=False, index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    basic_salary: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    pensionable_salary: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class MemberServicePeriod(UUIDPKMixin, CreatedAtMixin, Base):
    """A period of pensionable service (FR-MEM-009, DB benefits). Gaps between
    periods are breaks in service; part-time service counts at its factor."""

    __tablename__ = "member_service_period"

    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("member.id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    part_time_factor: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("1"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportStatus(str, enum.Enum):
    # Checked; the maker can download the errors and submit the valid rows.
    validated = "validated"
    pending_approval = "pending_approval"
    imported = "imported"
    rejected = "rejected"
    # Withdrawn by the maker, or replaced by a fresh upload.
    cancelled = "cancelled"


class MemberImport(UUIDPKMixin, TimestampMixin, Base):
    """A bulk member upload (FR-MEM-006): every row with its values, errors and
    warnings. Only rows without errors are imported, after a member checker approves."""

    __tablename__ = "member_import"

    fund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fund.id"), nullable=False, index=True)
    scheme_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("scheme.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ImportStatus] = mapped_column(str_enum(ImportStatus, 20), nullable=False, default=ImportStatus.validated, index=True)
    # [{"row": 2, "values": {...}, "errors": [...], "warnings": [...], "member_id": null}]
    rows: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
