"""Employer applications made by principal officers in the portal

Revision ID: a6c1f9e38b20
Revises: e4b7c2d91a36
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a6c1f9e38b20"
down_revision: Union[str, None] = "e4b7c2d91a36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE employer_application_seq START 1")
    op.create_table(
        "employer_application",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("reference", sa.String(20), nullable=False, unique=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False),
        sa.Column("officer_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("categories", postgresql.JSONB(), nullable=False),
        sa.Column("final_terms", postgresql.JSONB(), nullable=True),
        sa.Column("kyc_application_id", sa.UUID(), sa.ForeignKey("kyc_application.id"), nullable=True),
        sa.Column("scheme_id", sa.UUID(), sa.ForeignKey("scheme.id"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_employer_application_fund_id", "employer_application", ["fund_id"])
    op.create_index("ix_employer_application_officer_user_id", "employer_application", ["officer_user_id"])
    op.create_index("ix_employer_application_status", "employer_application", ["status"])


def downgrade() -> None:
    op.drop_table("employer_application")
    op.execute("DROP SEQUENCE employer_application_seq")
