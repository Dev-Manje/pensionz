"""Member portal login link

Revision ID: c8e2f4a61d07
Revises: b3d9e5a17c42
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8e2f4a61d07"
down_revision: Union[str, None] = "b3d9e5a17c42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("member", sa.Column("portal_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True))
    op.create_index("ix_member_portal_user_id", "member", ["portal_user_id"])


def downgrade() -> None:
    op.drop_index("ix_member_portal_user_id", table_name="member")
    op.drop_column("member", "portal_user_id")
