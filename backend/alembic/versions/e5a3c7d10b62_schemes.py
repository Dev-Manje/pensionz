"""participating employers (schemes) and their principal officers

Revision ID: e5a3c7d10b62
Revises: d81f6b2c9a40
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5a3c7d10b62"
down_revision: Union[str, None] = "d81f6b2c9a40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheme",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("registration_number", sa.String(60), nullable=True),
        sa.Column("tpin", sa.String(30), nullable=True),
        sa.Column("join_date", sa.Date(), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("contribution_day", sa.Integer(), nullable=False),
        sa.Column("billing_frequency", sa.String(20), nullable=False, server_default="monthly"),
        *[sa.Column(f"address_line{i}", sa.String(120), nullable=True) for i in range(1, 4)],
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fund_id", "code", name="uq_scheme_fund_code"),
        sa.CheckConstraint("contribution_day BETWEEN 1 AND 28", name="ck_scheme_contribution_day"),
    )
    op.create_table(
        "scheme_officer",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("scheme_id", sa.UUID(), sa.ForeignKey("scheme.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scheme_id", "user_id", name="uq_scheme_officer"),
    )


def downgrade() -> None:
    op.drop_table("scheme_officer")
    op.drop_table("scheme")
