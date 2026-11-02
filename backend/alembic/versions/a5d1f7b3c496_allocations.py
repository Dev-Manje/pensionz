"""Contribution allocations and the receipts that pay for them

Revision ID: a5d1f7b3c496
Revises: f4c9e6a2b385
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a5d1f7b3c496"
down_revision: Union[str, None] = "f4c9e6a2b385"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contribution_allocation",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("scheme_id", sa.UUID(), sa.ForeignKey("scheme.id"), nullable=False, index=True),
        sa.Column("schedule_id", sa.UUID(), sa.ForeignKey("contribution_schedule.id"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("schedule_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("member_fees", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("employer_fees", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("net_to_members", sa.Numeric(18, 2), nullable=False),
        sa.Column("fees", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("journal_entry_id", sa.UUID(), sa.ForeignKey("journal_entry.id"), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("approved_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # A schedule has at most one allocation waiting or in force.
    op.create_index("uq_contribution_allocation_live", "contribution_allocation", ["schedule_id"], unique=True,
                    postgresql_where=sa.text("status IN ('pending_approval', 'posted')"))
    op.create_table(
        "contribution_allocation_receipt",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("allocation_id", sa.UUID(), sa.ForeignKey("contribution_allocation.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("receipt_id", sa.UUID(), sa.ForeignKey("contribution_receipt.id"), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_allocation_receipt_positive"),
    )


def downgrade() -> None:
    op.drop_table("contribution_allocation_receipt")
    op.drop_index("uq_contribution_allocation_live", table_name="contribution_allocation")
    op.drop_table("contribution_allocation")
