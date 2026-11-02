"""Contribution receipts (payment notices and confirmed receipts)

Revision ID: e3b8d5f1a274
Revises: d2a7c4e9b318
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3b8d5f1a274"
down_revision: Union[str, None] = "d2a7c4e9b318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contribution_receipt",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("scheme_id", sa.UUID(), sa.ForeignKey("scheme.id"), nullable=True, index=True),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("receipt_number", sa.String(30), nullable=True),
        sa.Column("notice_number", sa.String(30), nullable=True),
        sa.Column("payment_method", sa.String(20), nullable=False),
        sa.Column("notified_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("allocated_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("bank_account_id", sa.UUID(), sa.ForeignKey("fund_bank_account.id"), nullable=True),
        sa.Column("payer_name", sa.String(200), nullable=True),
        sa.Column("payer_reference", sa.String(80), nullable=True),
        sa.Column("bank_reference", sa.String(80), nullable=True),
        sa.Column("contribution_month", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("proof_storage_key", sa.String(300), nullable=True),
        sa.Column("proof_filename", sa.String(200), nullable=True),
        sa.Column("proof_content_type", sa.String(100), nullable=True),
        sa.Column("notified_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("captured_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("confirmed_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("journal_entry_id", sa.UUID(), sa.ForeignKey("journal_entry.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("fund_id", "receipt_number", name="uq_contribution_receipt_number"),
        sa.CheckConstraint("allocated_amount >= 0 AND (amount IS NULL OR allocated_amount <= amount)", name="ck_receipt_allocated"),
    )


def downgrade() -> None:
    op.drop_table("contribution_receipt")
