"""Members, status changes and employer/category history; employer ↔ KYC client

Revision ID: a1c4e8f27b93
Revises: e7b3c9a14d52
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1c4e8f27b93"
down_revision: Union[str, None] = "e7b3c9a14d52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fk(name: str, target: str, nullable: bool = True, index: bool = False) -> sa.Column:
    return sa.Column(name, sa.UUID(), sa.ForeignKey(target), nullable=nullable, index=index)


def _s(name: str, length: int, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.String(length), nullable=nullable)


def upgrade() -> None:
    # Generated account codes: <fund code><6 digits>.
    op.execute("CREATE SEQUENCE member_number_seq START 1")
    op.add_column("scheme", sa.Column("party_id", sa.UUID(), sa.ForeignKey("party.id"), nullable=True))
    op.create_index("ix_scheme_party_id", "scheme", ["party_id"])

    op.create_table(
        "member",
        sa.Column("id", sa.UUID(), primary_key=True),
        _fk("fund_id", "fund.id", nullable=False, index=True),
        _fk("scheme_id", "scheme.id", index=True),
        _fk("category_id", "benefit_category.id", index=True),
        _fk("party_id", "party.id", index=True),
        _s("account_code", 20, nullable=False),
        sa.Column("account_type_code", sa.String(10), nullable=False, server_default="MEM"),
        _s("old_member_no", 30), _s("employee_no", 30), _s("upid", 40), _s("bi_upid", 40),
        sa.Column("is_group_account", sa.Boolean(), nullable=False, server_default=sa.false()),
        _fk("group_account_id", "member.id"),
        _s("salutation", 20), _s("first_name", 80, nullable=False), _s("other_names", 120), _s("maiden_name", 80),
        _s("last_name", 80, nullable=False),
        _s("gender", 10, nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        _s("nationality", 2), _s("id_type", 20), _s("id_number", 40), _s("id_number_key", 40),
        _s("civil_status_on_entry", 20), _s("civil_status_current", 20), _s("civil_status_foreign", 40),
        _fk("birth_district_id", "district.id"), _s("birth_village", 120),
        _s("postal_address", 200), _fk("postal_district_id", "district.id"), _s("postal_village", 120),
        _s("physical_address", 200), _fk("home_district_id", "district.id"), _fk("home_ta_id", "traditional_authority.id"),
        _fk("home_village_id", "village.id"),
        _s("telephone", 40), _s("mobile", 40), _s("fax", 40), _s("email", 255), _s("preferred_contact", 10),
        _fk("bank_id", "bank.id"), _fk("bank_branch_id", "bank_branch.id"), _s("bank_account_name", 200), _s("bank_account_number", 40),
        _s("next_of_kin_name", 200), _s("next_of_kin_relationship", 20), _s("next_of_kin_phone", 40), _s("next_of_kin_email", 255),
        sa.Column("date_joined_fund", sa.Date(), nullable=False),
        sa.Column("date_joined_employer", sa.Date(), nullable=True),
        _s("status", 20, nullable=False),
        sa.Column("status_effective", sa.Date(), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("date_of_death", sa.Date(), nullable=True),
        sa.Column("regulatory_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fund_id", "account_code", name="uq_member_fund_account_code"),
    )
    op.create_index("ix_member_last_name", "member", ["last_name"])
    op.create_index("ix_member_status", "member", ["status"])
    op.create_index("ix_member_id_number_key", "member", ["id_number_key"])

    op.create_table(
        "member_status_change",
        sa.Column("id", sa.UUID(), primary_key=True),
        _fk("member_id", "member.id", nullable=False, index=True),
        _s("from_status", 20), _s("to_status", 20, nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _fk("requested_by_user_id", "user.id"), _fk("approved_by_user_id", "user.id"),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "member_assignment",
        sa.Column("id", sa.UUID(), primary_key=True),
        _fk("member_id", "member.id", nullable=False, index=True),
        _fk("scheme_id", "scheme.id"), _fk("category_id", "benefit_category.id"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        _s("reason", 30, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        _fk("approved_by_user_id", "user.id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("member_assignment")
    op.drop_table("member_status_change")
    op.drop_table("member")
    op.drop_index("ix_scheme_party_id", table_name="scheme")
    op.drop_column("scheme", "party_id")
    op.execute("DROP SEQUENCE member_number_seq")
