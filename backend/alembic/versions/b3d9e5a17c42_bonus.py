"""Declared bonus: declarations, runs and run lines

Revision ID: b3d9e5a17c42
Revises: a6c1f9e38b20
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3d9e5a17c42"
down_revision: Union[str, None] = "a6c1f9e38b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _stamps(updated: bool = True):
    cols = [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]
    if updated:
        cols.append(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    return cols


def upgrade() -> None:
    op.execute("CREATE SEQUENCE bonus_reference_seq START 1")
    op.create_table(
        "bonus_declaration",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("reference", sa.String(30), nullable=False, unique=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("components", postgresql.JSONB(), nullable=False),
        sa.Column("resolution", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("declared_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("approved_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        *_stamps(),
    )
    op.create_index("uq_bonus_declaration_period_kind", "bonus_declaration", ["fund_id", "period_start", "period_end", "kind"], unique=True)
    op.create_table(
        "bonus_run",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("declaration_id", sa.UUID(), sa.ForeignKey("bonus_declaration.id"), nullable=False, index=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("reference", sa.String(30), nullable=False, unique=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("member_ids", postgresql.JSONB(), nullable=True),
        sa.Column("as_at", sa.Date(), nullable=True),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("total_credit", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_debit", sa.Numeric(18, 2), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), sa.ForeignKey("journal_entry.id"), nullable=True),
        sa.Column("reversal_entry_id", sa.UUID(), sa.ForeignKey("journal_entry.id"), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
    )
    op.create_index("uq_bonus_run_final_live", "bonus_run", ["declaration_id"], unique=True,
                    postgresql_where=sa.text("kind = 'final' AND status IN ('draft', 'pending_approval', 'posted')"))
    op.create_table(
        "bonus_run_line",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("run_id", sa.UUID(), sa.ForeignKey("bonus_run.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.UUID(), sa.ForeignKey("member.id"), nullable=False, index=True),
        sa.Column("component", sa.String(20), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("opening_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("opening_bonus", sa.Numeric(18, 6), nullable=False),
        sa.Column("movements", sa.Numeric(18, 2), nullable=False),
        sa.Column("movements_bonus", sa.Numeric(18, 6), nullable=False),
        sa.Column("calculated", sa.Numeric(18, 2), nullable=False),
        sa.Column("already_credited", sa.Numeric(18, 2), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("member_transaction_id", sa.UUID(), sa.ForeignKey("member_transaction.id"), nullable=True),
        sa.Column("reversal_transaction_id", sa.UUID(), sa.ForeignKey("member_transaction.id"), nullable=True),
        *_stamps(updated=False),
    )


def downgrade() -> None:
    op.drop_table("bonus_run_line")
    op.drop_table("bonus_run")
    op.drop_table("bonus_declaration")
    op.execute("DROP SEQUENCE bonus_reference_seq")
