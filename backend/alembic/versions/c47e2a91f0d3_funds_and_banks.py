"""funds, trustees, fund bank accounts, user fund access, banks & branches

Revision ID: c47e2a91f0d3
Revises: b1e58cad77d5
Create Date: 2026-11-01

Seeds the Malawi commercial banks with their main-town branches as a starter
list; the reference-data screen (FR-CFG-010) maintains it from here on.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c47e2a91f0d3"
down_revision: Union[str, None] = "b1e58cad77d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MAIN_TOWNS = ["Blantyre", "Lilongwe", "Mzuzu", "Zomba"]
BANKS = [
    ("National Bank of Malawi", "NBM"),
    ("Standard Bank Malawi", "Standard Bank"),
    ("FDH Bank", "FDH"),
    ("NBS Bank", "NBS"),
    ("First Capital Bank Malawi", "First Capital"),
    ("Ecobank Malawi", "Ecobank"),
    ("CDH Investment Bank", "CDH"),
    ("Centenary Bank Malawi", "Centenary"),
]


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.UUID(), primary_key=True)


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    bank = op.create_table(
        "bank",
        _uuid_pk(),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("short_name", sa.String(30), nullable=True),
        sa.Column("swift_code", sa.String(11), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        _created_at(),
    )
    branch = op.create_table(
        "bank_branch",
        _uuid_pk(),
        sa.Column("bank_id", sa.UUID(), sa.ForeignKey("bank.id"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(20), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _created_at(),
        sa.UniqueConstraint("bank_id", "name", name="uq_bank_branch_name"),
    )

    op.create_table(
        "fund",
        _uuid_pk(),
        sa.Column("code", sa.String(10), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("fund_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("registration_number", sa.String(60), nullable=True),
        sa.Column("tpin", sa.String(30), nullable=True),
        sa.Column("financial_year_end_month", sa.Integer(), nullable=True),
        *[sa.Column(f"address_line{i}", sa.String(120), nullable=True) for i in range(1, 6)],
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("fax", sa.String(40), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(40), nullable=True),
        sa.Column("contact_alt_phone", sa.String(40), nullable=True),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("financial_year_end_month BETWEEN 1 AND 12", name="ck_fund_fye_month"),
    )
    op.create_table(
        "fund_trustee",
        _uuid_pk(),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("designation", sa.String(100), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("appointed_on", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        _created_at(),
    )
    op.create_table(
        "fund_bank_account",
        _uuid_pk(),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("bank_id", sa.UUID(), sa.ForeignKey("bank.id"), nullable=False),
        sa.Column("branch_id", sa.UUID(), sa.ForeignKey("bank_branch.id"), nullable=True),
        sa.Column("account_name", sa.String(200), nullable=False),
        sa.Column("account_number", sa.String(30), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="MWK"),
        sa.Column("purpose", sa.String(20), nullable=False, server_default="general"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        _created_at(),
    )
    op.create_table(
        "user_fund_access",
        _uuid_pk(),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("granted_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        _created_at(),
        sa.UniqueConstraint("user_id", "fund_id", name="uq_user_fund_access"),
    )

    bank_rows, branch_rows = [], []
    for order, (name, short) in enumerate(BANKS, start=1):
        bank_id = uuid.uuid4()
        bank_rows.append({"id": bank_id, "name": name, "short_name": short, "active": True, "sort_order": order})
        branch_rows += [{"id": uuid.uuid4(), "bank_id": bank_id, "name": town, "active": True} for town in MAIN_TOWNS]
    op.bulk_insert(bank, bank_rows)
    op.bulk_insert(branch, branch_rows)


def downgrade() -> None:
    op.drop_table("user_fund_access")
    op.drop_table("fund_bank_account")
    op.drop_table("fund_trustee")
    op.drop_table("fund")
    op.drop_table("bank_branch")
    op.drop_table("bank")
