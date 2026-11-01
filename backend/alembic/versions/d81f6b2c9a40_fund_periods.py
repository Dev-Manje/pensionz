"""processing month per fund

Revision ID: d81f6b2c9a40
Revises: c47e2a91f0d3
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d81f6b2c9a40"
down_revision: Union[str, None] = "c47e2a91f0d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fund_period",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fund_id", "period", name="uq_fund_period"),
        sa.CheckConstraint("extract(day from period) = 1", name="ck_fund_period_first_of_month"),
    )
    op.create_index("uq_fund_period_one_open", "fund_period", ["fund_id"], unique=True, postgresql_where=sa.text("status = 'open'"))


def downgrade() -> None:
    op.drop_index("uq_fund_period_one_open", table_name="fund_period")
    op.drop_table("fund_period")
