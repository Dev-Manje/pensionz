"""Contribution schedules and their lines

Revision ID: f4c9e6a2b385
Revises: e3b8d5f1a274
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4c9e6a2b385"
down_revision: Union[str, None] = "e3b8d5f1a274"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _money(name: str) -> sa.Column:
    return sa.Column(name, sa.Numeric(18, 2), nullable=False, server_default="0")


def upgrade() -> None:
    op.create_table(
        "contribution_schedule",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("scheme_id", sa.UUID(), sa.ForeignKey("scheme.id"), nullable=False, index=True),
        sa.Column("contribution_month", sa.Date(), nullable=False, index=True),
        sa.Column("supplementary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        _money("total_employee"), _money("total_employer"), _money("total_voluntary"), _money("total_severance"), _money("total"),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("submitted_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # One main schedule per employer per month (supplementary ones are extra).
    op.create_index("uq_contribution_schedule_main", "contribution_schedule", ["scheme_id", "contribution_month"], unique=True,
                    postgresql_where=sa.text("status <> 'cancelled' AND NOT supplementary"))
    op.create_table(
        "contribution_schedule_line",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("schedule_id", sa.UUID(), sa.ForeignKey("contribution_schedule.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.UUID(), sa.ForeignKey("member.id"), nullable=True, index=True),
        sa.Column("account_code", sa.String(20), nullable=True),
        sa.Column("employee_no", sa.String(30), nullable=True),
        sa.Column("member_name", sa.String(200), nullable=True),
        sa.Column("pensionable_salary", sa.Numeric(18, 2), nullable=True),
        _money("employee"), _money("employer"), _money("voluntary"), _money("severance"),
        sa.Column("errors", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_table("contribution_schedule_line")
    op.drop_index("uq_contribution_schedule_main", table_name="contribution_schedule")
    op.drop_table("contribution_schedule")
