"""One-time codes for portal sign-in and money-affecting actions

Revision ID: d8e3a61c5b72
Revises: a5d1f7b3c496
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8e3a61c5b72"
down_revision: Union[str, None] = "a5d1f7b3c496"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "one_time_code",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False, server_default="email"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("one_time_code")
