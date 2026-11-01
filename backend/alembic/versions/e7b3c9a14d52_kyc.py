"""KYC applications, documents, declarations and parties

Revision ID: e7b3c9a14d52
Revises: d4a8b2c61f93
Create Date: 2026-11-02

Seeds version 1 of each declaration (neutral wording adapted from the source
form — the product is unbranded; compliance should confirm) and a neutral
KYC product list.
"""
import uuid
from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7b3c9a14d52"
down_revision: Union[str, None] = "d4a8b2c61f93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMMON = (
    "{we_cap} undertake to tell the administrator promptly of any change to this information.\n\n"
    "{we_cap} consent to the administrator sharing this information with the funds it administers, their trustees, "
    "the administrator's group companies and business units, and regulators, to provide the services and meet legal "
    "obligations.\n\n"
    "Confidentiality: this information is collected under the Data Protection Act. It will be kept confidential, "
    "protected and used only for these purposes."
)
DECLARATIONS = {
    "corporate": ("Declaration by the organisation", "We"),
    "group": ("Declaration by the group's signatories", "We, the signatories,"),
    "individual": ("Declaration", "I"),
}


def _body(we: str) -> str:
    we_cap = we.split(",")[0]
    return (
        f"{we} declare that the information in this application and the documents provided are true, correct and complete.\n\n"
        f"{we_cap} understand that false or misleading information, or leaving out information, may lead to the application being "
        "declined or the relationship being ended, and may be reported to the authorities.\n\n"
        + _COMMON.format(we_cap=we_cap)
    )


PRODUCTS = [("GROUP_PENSION", "Group / employer pension"), ("PERSONAL_PENSION", "Personal pension"),
            ("GROUP_LIFE", "Group life assurance"), ("GROUP_FUNERAL", "Group funeral cover"), ("INVESTMENTS", "Investments")]


def upgrade() -> None:
    op.execute("CREATE SEQUENCE kyc_reference_seq START 1")
    declaration = op.create_table(
        "declaration_version",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("client_type", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("client_type", "version", name="uq_declaration_version"),
    )
    op.create_table(
        "party",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("client_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, index=True),
        sa.Column("identifier", sa.String(60), nullable=True, index=True),
        sa.Column("risk_rating", sa.String(10), nullable=False),
        sa.Column("is_pep", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("kyc_approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kyc_review_due", sa.Date(), nullable=False),
        sa.Column("latest_application_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    user_fk = lambda name: sa.Column(name, sa.UUID(), sa.ForeignKey("user.id"), nullable=True)  # noqa: E731
    op.create_table(
        "kyc_application",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("reference", sa.String(20), nullable=False, unique=True),
        sa.Column("client_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("display_name", sa.String(200), nullable=False, server_default=""),
        user_fk("captured_by_user_id"),
        sa.Column("applicant_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True, index=True),
        sa.Column("party_id", sa.UUID(), sa.ForeignKey("party.id"), nullable=True, index=True),
        sa.Column("declaration_version_id", sa.UUID(), sa.ForeignKey("declaration_version.id"), nullable=True),
        sa.Column("declaration_accepted_by", sa.String(200), nullable=True),
        sa.Column("declaration_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declaration_accepted_ip", sa.String(64), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_rating", sa.String(10), nullable=True),
        sa.Column("risk_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("edd_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        user_fk("reviewer_user_id"),
        sa.Column("review_note", sa.Text(), nullable=True),
        user_fk("recommended_by_user_id"),
        user_fk("decided_by_user_id"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_kyc_application_status", "kyc_application", ["status"])
    op.create_table(
        "kyc_document",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("application_id", sa.UUID(), sa.ForeignKey("kyc_application.id"), nullable=False, index=True),
        sa.Column("requirement", sa.String(60), nullable=False),
        sa.Column("doc_type", sa.String(60), nullable=False),
        sa.Column("doc_type_other", sa.String(120), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("storage_key", sa.String(200), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(60), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        user_fk("uploaded_by_user_id"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("review_status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("review_reason", sa.Text(), nullable=True),
        user_fk("reviewed_by_user_id"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.bulk_insert(declaration, [
        {"id": uuid.uuid4(), "client_type": ct, "version": 1, "title": title, "body": _body(we), "effective_from": date(2026, 1, 1)}
        for ct, (title, we) in DECLARATIONS.items()
    ])
    op.bulk_insert(sa.table("reference_item", sa.column("id", sa.UUID()), sa.column("list_key", sa.String), sa.column("code", sa.String),
                            sa.column("name", sa.String), sa.column("sort_order", sa.Integer), sa.column("active", sa.Boolean)),
                   [{"id": uuid.uuid4(), "list_key": "kyc_product", "code": c, "name": n, "sort_order": i, "active": True}
                    for i, (c, n) in enumerate(PRODUCTS)])


def downgrade() -> None:
    op.execute("DELETE FROM reference_item WHERE list_key = 'kyc_product'")
    op.drop_table("kyc_document")
    op.drop_index("ix_kyc_application_status", table_name="kyc_application")
    op.drop_table("kyc_application")
    op.drop_table("party")
    op.drop_table("declaration_version")
    op.execute("DROP SEQUENCE kyc_reference_seq")
