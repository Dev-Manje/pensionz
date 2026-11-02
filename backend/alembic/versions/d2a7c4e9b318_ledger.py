"""Fund ledgers: chart of accounts, journal entries, ledger lines, member transactions

Revision ID: d2a7c4e9b318
Revises: c9e4a1d7f205
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2a7c4e9b318"
down_revision: Union[str, None] = "c9e4a1d7f205"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gl_account",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=True, index=True),
        sa.Column("book", sa.String(20), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("account_class", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("fund_id", "code", name="uq_gl_account_fund_code"),
    )
    op.create_index("uq_gl_account_admin_code", "gl_account", ["code"], unique=True, postgresql_where=sa.text("fund_id IS NULL"))

    op.create_table(
        "journal_entry",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=True, index=True),
        sa.Column("book", sa.String(20), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False, index=True),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("reverses_entry_id", sa.UUID(), sa.ForeignKey("journal_entry.id"), nullable=True, unique=True),
        sa.Column("created_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_journal_entry_entity", "journal_entry", ["entity_type", "entity_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_journal_entry_number ON journal_entry "
        "(book, coalesce(fund_id, '00000000-0000-0000-0000-000000000000'::uuid), number)"
    )

    op.create_table(
        "ledger_line",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("entry_id", sa.UUID(), sa.ForeignKey("journal_entry.id"), nullable=False, index=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=True, index=True),
        sa.Column("gl_account_id", sa.UUID(), sa.ForeignKey("gl_account.id"), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("member_id", sa.UUID(), sa.ForeignKey("member.id"), nullable=True, index=True),
        sa.Column("scheme_id", sa.UUID(), sa.ForeignKey("scheme.id"), nullable=True, index=True),
        sa.Column("component", sa.String(20), nullable=True),
        sa.Column("description", sa.String(300), nullable=True),
        sa.CheckConstraint("(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)", name="ck_ledger_line_one_side"),
    )

    op.create_table(
        "member_transaction",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("member_id", sa.UUID(), sa.ForeignKey("member.id"), nullable=False, index=True),
        sa.Column("fund_id", sa.UUID(), sa.ForeignKey("fund.id"), nullable=False, index=True),
        sa.Column("transaction_code", sa.Integer(), nullable=False),
        sa.Column("transaction_name", sa.String(80), nullable=False),
        sa.Column("effect", sa.String(10), nullable=False),
        sa.Column("component", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False, index=True),
        sa.Column("contribution_month", sa.Date(), nullable=True),
        sa.Column("reference", sa.String(60), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("journal_entry_id", sa.UUID(), sa.ForeignKey("journal_entry.id"), nullable=False, index=True),
        sa.Column("reverses_transaction_id", sa.UUID(), sa.ForeignKey("member_transaction.id"), nullable=True, unique=True),
        sa.Column("created_by_user_id", sa.UUID(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_member_transaction_positive"),
    )

    # Books are immutable (FR-ACC-003): the database refuses updates and deletes.
    op.execute("""
        CREATE OR REPLACE FUNCTION pz_refuse_ledger_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ledger rows are immutable — post a reversal instead';
        END;
        $$ LANGUAGE plpgsql
    """)
    for table in ("journal_entry", "ledger_line", "member_transaction"):
        op.execute(f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION pz_refuse_ledger_change()")


def downgrade() -> None:
    for table in ("journal_entry", "ledger_line", "member_transaction"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS pz_refuse_ledger_change()")
    op.drop_table("member_transaction")
    op.drop_table("ledger_line")
    op.execute("DROP INDEX IF EXISTS uq_journal_entry_number")
    op.drop_table("journal_entry")
    op.drop_index("uq_gl_account_admin_code", table_name="gl_account")
    op.drop_table("gl_account")
