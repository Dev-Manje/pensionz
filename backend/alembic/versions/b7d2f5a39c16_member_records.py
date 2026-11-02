"""Beneficiary nominations, salary history and service periods

Revision ID: b7d2f5a39c16
Revises: a1c4e8f27b93
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2f5a39c16"
down_revision: Union[str, None] = "a1c4e8f27b93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _created() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "beneficiary_nomination",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("member_id", sa.UUID(), sa.ForeignKey("member.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("signed_date", sa.Date(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("approved_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        _created(),
        sa.UniqueConstraint("member_id", "version", name="uq_beneficiary_nomination_version"),
    )
    op.create_table(
        "beneficiary",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("nomination_id", sa.UUID(), sa.ForeignKey("beneficiary_nomination.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("relationship", sa.String(20), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("id_number", sa.String(40), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("address", sa.String(200), nullable=True),
        sa.Column("share_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("guardian_name", sa.String(200), nullable=True),
        sa.Column("guardian_relationship", sa.String(20), nullable=True),
        sa.Column("guardian_phone", sa.String(40), nullable=True),
        sa.Column("guardian_id_number", sa.String(40), nullable=True),
    )
    op.create_table(
        "member_salary",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("member_id", sa.UUID(), sa.ForeignKey("member.id"), nullable=False, index=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("basic_salary", sa.Numeric(18, 2), nullable=False),
        sa.Column("pensionable_salary", sa.Numeric(18, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        _created(),
        sa.UniqueConstraint("member_id", "effective_from", name="uq_member_salary_from"),
    )
    op.create_table(
        "member_service_period",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("member_id", sa.UUID(), sa.ForeignKey("member.id"), nullable=False, index=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("part_time_factor", sa.Numeric(5, 4), nullable=False, server_default="1"),
        sa.Column("note", sa.Text(), nullable=True),
        _created(),
    )


def downgrade() -> None:
    op.drop_table("member_service_period")
    op.drop_table("member_salary")
    op.drop_table("beneficiary")
    op.drop_table("beneficiary_nomination")
