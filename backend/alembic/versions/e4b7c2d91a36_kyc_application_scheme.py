"""KYC applications made from the principal officer portal for an employer

Revision ID: e4b7c2d91a36
Revises: d8e3a61c5b72
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4b7c2d91a36"
down_revision: Union[str, None] = "d8e3a61c5b72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kyc_application", sa.Column("scheme_id", sa.UUID(), sa.ForeignKey("scheme.id"), nullable=True))
    op.create_index("ix_kyc_application_scheme_id", "kyc_application", ["scheme_id"])


def downgrade() -> None:
    op.drop_index("ix_kyc_application_scheme_id", table_name="kyc_application")
    op.drop_column("kyc_application", "scheme_id")
