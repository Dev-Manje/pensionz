"""investment options per fund

Revision ID: a93e1f5b7c28
Revises: f2b8d4e61c07
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a93e1f5b7c28"
down_revision: Union[str, None] = "f2b8d4e61c07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investment_option",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("pricing_method", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("launch_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fund_id", "code", name="uq_investment_option_fund_code"),
    )


def downgrade() -> None:
    op.drop_table("investment_option")
