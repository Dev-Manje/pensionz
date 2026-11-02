"""Bulk member uploads

Revision ID: c9e4a1d7f205
Revises: b7d2f5a39c16
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9e4a1d7f205"
down_revision: Union[str, None] = "b7d2f5a39c16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "member_import",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("scheme_id", sa.UUID(), sa.ForeignKey("scheme.id"), nullable=True),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("rows", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("member_import")
