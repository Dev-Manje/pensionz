"""ledger set-up and reference lists: account & transaction types, districts,
TAs, villages, countries, reference items

Revision ID: c3f9a7d25e81
Revises: b6d2e8f40a19
Create Date: 2026-11-01

Seeds only established facts: the legacy account types and transaction codes
1–6 (REQUIREMENTS FR-CFG-005/006, with GL codes from the *proposed* chart of
accounts — to confirm with finance), Malawi's 28 districts, ISO 3166
countries, and the permit types listed in FR-ONB-I08. TAs and villages are
entered through Setup.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3f9a7d25e81"
down_revision: Union[str, None] = "b6d2e8f40a19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACCOUNT_TYPES = [("PF", "Pension Fund", "fund"), ("MEM", "Member Account", "member"), ("COMP", "Company Account", "employer"),
                 ("RES", "Reserve Account", "reserve"), ("SHARE", "Share", "other")]
# code, name, effect, reversal, debit GL, credit GL (proposed chart: 2000 member credits, 2100 unallocated,
# 2200 benefits payable, 2600 reserve)
TRANSACTION_TYPES = [
    (1, "Initial Allocation", "credit", 2, "2100", "2000"),
    (2, "Reversal Initial Allocation", "debit", 1, "2000", "2100"),
    (3, "Withdrawal", "debit", 4, "2000", "2200"),
    (4, "Reversal Withdrawal", "credit", 3, "2200", "2000"),
    (5, "Bonus Reversal", "debit", 6, "2000", "2600"),
    (6, "Bonus", "credit", 5, "2600", "2000"),
]
DISTRICTS = {
    "northern": ["Chitipa", "Karonga", "Likoma", "Mzimba", "Nkhata Bay", "Rumphi"],
    "central": ["Dedza", "Dowa", "Kasungu", "Lilongwe", "Mchinji", "Nkhotakota", "Ntcheu", "Ntchisi", "Salima"],
    "southern": ["Balaka", "Blantyre", "Chikwawa", "Chiradzulu", "Machinga", "Mangochi", "Mulanje", "Mwanza", "Neno",
                 "Nsanje", "Phalombe", "Thyolo", "Zomba"],
}
REFERENCE_ITEMS = {
    "relationship": [("SPOUSE", "Spouse"), ("CHILD", "Child"), ("PARENT", "Parent"), ("SIBLING", "Brother or sister"),
                     ("GRANDCHILD", "Grandchild"), ("GRANDPARENT", "Grandparent"), ("GUARDIAN", "Guardian"),
                     ("RELATIVE", "Other relative"), ("OTHER", "Other")],
    "id_type": [("NATID", "National ID"), ("PASSPORT", "Passport"), ("DRIVING", "Driving licence"),
                ("VOTER", "Voter registration card"), ("BIRTH", "Birth certificate")],
    "permit_type": [("EMPLOYMENT", "Employment permit"), ("STUDY", "Study permit"), ("TEMP_RES", "Temporary residence permit"),
                    ("BUS_RES", "Business residence permit"), ("PERM_RES", "Permanent residence permit"),
                    ("DIPLOMATIC", "Diplomatic"), ("TECH_ASSIST", "Technical assistance")],
    "salutation": [("MR", "Mr"), ("MRS", "Mrs"), ("MS", "Ms"), ("MISS", "Miss"), ("DR", "Dr"), ("PROF", "Prof"),
                   ("REV", "Rev"), ("HON", "Hon")],
}


def _id() -> sa.Column:
    return sa.Column("id", sa.UUID(), primary_key=True)


def _created() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def _active() -> sa.Column:
    return sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true())


def upgrade() -> None:
    from app.data.countries import COUNTRIES

    account_type = op.create_table(
        "account_type", _id(),
        sa.Column("code", sa.String(10), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("ledger_behaviour", sa.String(20), nullable=False),
        _active(), _created(),
    )
    transaction_type = op.create_table(
        "transaction_type", _id(),
        sa.Column("code", sa.Integer(), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("effect", sa.String(10), nullable=False),
        sa.Column("reversal_code", sa.Integer(), nullable=True),
        sa.Column("debit_gl_code", sa.String(20), nullable=True),
        sa.Column("credit_gl_code", sa.String(20), nullable=True),
        _active(), _created(),
    )
    district = op.create_table(
        "district", _id(),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("region", sa.String(20), nullable=False),
        _active(), _created(),
    )
    op.create_table(
        "traditional_authority", _id(),
        sa.Column("district_id", sa.UUID(), sa.ForeignKey("district.id"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        _active(), _created(),
        sa.UniqueConstraint("district_id", "name", name="uq_traditional_authority_name"),
    )
    op.create_table(
        "village", _id(),
        sa.Column("traditional_authority_id", sa.UUID(), sa.ForeignKey("traditional_authority.id"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        _active(), _created(),
        sa.UniqueConstraint("traditional_authority_id", "name", name="uq_village_name"),
    )
    country = op.create_table(
        "country", _id(),
        sa.Column("code", sa.String(2), nullable=False, unique=True),
        sa.Column("code3", sa.String(3), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        _active(), _created(),
    )
    reference_item = op.create_table(
        "reference_item", _id(),
        sa.Column("list_key", sa.String(30), nullable=False, index=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        _active(), _created(),
        sa.UniqueConstraint("list_key", "code", name="uq_reference_item_code"),
    )

    op.bulk_insert(account_type, [{"id": uuid.uuid4(), "code": c, "name": n, "ledger_behaviour": b, "active": True} for c, n, b in ACCOUNT_TYPES])
    op.bulk_insert(transaction_type, [
        {"id": uuid.uuid4(), "code": c, "name": n, "effect": e, "reversal_code": r, "debit_gl_code": dr, "credit_gl_code": cr, "active": True}
        for c, n, e, r, dr, cr in TRANSACTION_TYPES
    ])
    op.bulk_insert(district, [{"id": uuid.uuid4(), "name": n, "region": region, "active": True}
                              for region, names in DISTRICTS.items() for n in names])
    op.bulk_insert(country, [{"id": uuid.uuid4(), "code": a2, "code3": a3, "name": n, "active": True} for a2, a3, n in COUNTRIES])
    op.bulk_insert(reference_item, [
        {"id": uuid.uuid4(), "list_key": key, "code": code, "name": name, "sort_order": i, "active": True}
        for key, items in REFERENCE_ITEMS.items() for i, (code, name) in enumerate(items)
    ])


def downgrade() -> None:
    for table in ("reference_item", "country", "village", "traditional_authority", "district", "transaction_type", "account_type"):
        op.drop_table(table)
