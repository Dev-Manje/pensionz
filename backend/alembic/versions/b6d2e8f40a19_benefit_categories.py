"""benefit categories with effective-dated terms

Revision ID: b6d2e8f40a19
Revises: a93e1f5b7c28
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b6d2e8f40a19"
down_revision: Union[str, None] = "a93e1f5b7c28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "benefit_category",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("scheme_id", sa.UUID(), sa.ForeignKey("scheme.id"), nullable=False, index=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scheme_id", "code", name="uq_benefit_category_scheme_code"),
    )
    op.create_table(
        "benefit_category_terms",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("category_id", sa.UUID(), sa.ForeignKey("benefit_category.id"), nullable=False, index=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("design", sa.String(10), nullable=False),
        sa.Column("employee_rate_type", sa.String(10), nullable=False, server_default="percent"),
        sa.Column("employee_rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("employer_rate_type", sa.String(10), nullable=False, server_default="percent"),
        sa.Column("employer_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("salary_basis", sa.String(30), nullable=False, server_default="basic"),
        sa.Column("normal_retirement_age", sa.Integer(), nullable=False),
        sa.Column("min_entry_age", sa.Integer(), nullable=True),
        sa.Column("max_entry_age", sa.Integer(), nullable=True),
        sa.Column("waiting_period_months", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vesting_scale", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("default_investment_option_id", sa.UUID(), sa.ForeignKey("investment_option.id"), nullable=True),
        sa.Column("member_choice_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("avc_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("group_life_multiple", sa.Numeric(9, 4), nullable=True),
        sa.Column("accrual_denominator", sa.Integer(), nullable=True),
        sa.Column("final_salary_months", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("category_id", "effective_from", name="uq_benefit_category_terms_from"),
    )


def downgrade() -> None:
    op.drop_table("benefit_category_terms")
    op.drop_table("benefit_category")
