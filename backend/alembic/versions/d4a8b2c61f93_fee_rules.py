"""fee rules per fund

Revision ID: d4a8b2c61f93
Revises: c3f9a7d25e81
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4a8b2c61f93"
down_revision: Union[str, None] = "c3f9a7d25e81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fee_rule",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("scheme_id", sa.UUID(), sa.ForeignKey("scheme.id"), nullable=True, index=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("fee_type", sa.String(30), nullable=False),
        sa.Column("basis", sa.String(30), nullable=False),
        sa.Column("rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("payer", sa.String(20), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fund_id", "code", name="uq_fee_rule_fund_code"),
    )


def downgrade() -> None:
    op.drop_table("fee_rule")
