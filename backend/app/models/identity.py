import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPKMixin, str_enum


class UserRole(str, enum.Enum):
    """REQUIREMENTS.md §3. A user may hold several roles; checks are "has any of"."""

    admin = "admin"
    scheme_config_maker = "scheme_config_maker"
    scheme_config_checker = "scheme_config_checker"
    member_admin = "member_admin"
    member_checker = "member_checker"
    contributions_officer = "contributions_officer"
    contributions_checker = "contributions_checker"
    benefits_officer = "benefits_officer"
    benefits_checker = "benefits_checker"
    benefits_approver_l2 = "benefits_approver_l2"
    finance = "finance"
    finance_checker = "finance_checker"
    payroll_officer = "payroll_officer"
    compliance = "compliance"
    relationship_manager = "relationship_manager"
    auditor = "auditor"
    trustee = "trustee"
    # Portal users (outside the administrator's staff).
    principal_officer = "principal_officer"
    member = "member"
    individual = "individual"


PORTAL_ROLES = frozenset({UserRole.principal_officer, UserRole.member, UserRole.individual, UserRole.trustee})
STAFF_ROLES = frozenset(set(UserRole) - PORTAL_ROLES)


class UserStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"
    deactivated = "deactivated"


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(str_enum(UserStatus, 20), nullable=False, default=UserStatus.active)
    # Tokens issued before this are refused: changing/resetting a password
    # (or suspending the user) signs out every session.
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    role_assignments: Mapped[list["UserRoleAssignment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def roles(self) -> list[UserRole]:
        return sorted((a.role for a in self.role_assignments), key=lambda r: r.value)

    def has_role(self, role: UserRole) -> bool:
        return any(a.role == role for a in self.role_assignments)

    def has_any_role(self, *roles: UserRole) -> bool:
        return any(self.has_role(r) for r in roles)

    @property
    def is_staff(self) -> bool:
        return any(a.role in STAFF_ROLES for a in self.role_assignments)


class UserRoleAssignment(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "user_role_assignment"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_role_assignment"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole), nullable=False)

    user: Mapped["User"] = relationship(back_populates="role_assignments")


class PasswordResetToken(UUIDPKMixin, CreatedAtMixin, Base):
    """Single-use link to set a password: self-service reset (1 hour) or a
    staff-sent invitation (7 days). Only the SHA-256 of the token is stored."""

    __tablename__ = "password_reset_token"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, default="reset")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)


class OneTimeCode(UUIDPKMixin, CreatedAtMixin, Base):
    """A 6-digit code sent to the user (email now, SMS later) to confirm a
    sign-in or a money-affecting action. Only an HMAC of the code is stored;
    it works once, for `otp_minutes`, and dies after `otp_max_attempts` wrong tries."""

    __tablename__ = "one_time_code"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    # "sign_in", or an action key such as "remittance".
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(10), nullable=False, default="email")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
