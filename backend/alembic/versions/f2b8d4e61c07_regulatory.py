"""regulatory parameters and tax tables (effective-dated)

Revision ID: f2b8d4e61c07
Revises: e5a3c7d10b62
Create Date: 2026-11-01

No figures are seeded here: values are entered (and approved) through the
Regulatory screen; the dev seed adds the working defaults from TASKS.md.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b8d4e61c07"
down_revision: Union[str, None] = "e5a3c7d10b62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "regulatory_parameter_version",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("key", sa.String(60), nullable=False, index=True),
        sa.Column("value", sa.Numeric(18, 6), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("key", "effective_from", name="uq_regulatory_parameter_version"),
    )
    op.create_table(
        "tax_table",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("kind", "effective_from", name="uq_tax_table_version"),
    )
    op.create_table(
        "tax_band",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("table_id", sa.UUID(), sa.ForeignKey("tax_table.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("lower", sa.Numeric(18, 2), nullable=False),
        sa.Column("rate_pct", sa.Numeric(9, 6), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tax_band")
    op.drop_table("tax_table")
    op.drop_table("regulatory_parameter_version")
