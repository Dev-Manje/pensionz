import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.api.v1.approvals import _name
from app.api.v1.members import get_member
from app.core.database import get_db
from app.models.identity import User
from app.models.ledger import Component, JournalEntry, MemberTransaction
from app.models.member import Member
from app.schemas.ledger import (
    AccountBalanceOut, ChartOut, ComponentBalanceOut, JournalEntryOut, JournalPage, LedgerLineOut, MemberLedgerOut, MemberTransactionOut,
    TieOutOut,
)
from app.services import fund_access, ledger

router = APIRouter(tags=["ledger"])

ZERO = Decimal("0")


@router.get("/funds/{fund_id}/ledger/accounts", response_model=ChartOut)
def chart(fund_id: uuid.UUID, period: date | None = None, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> ChartOut:
    """The fund's chart of accounts with balances (a trial balance), optionally up to a processing month."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    balances = ledger.account_balances(db, fund.id, up_to_period=ledger.periods.month_start(period) if period else None)
    t = ledger.tie_out(db, fund.id)
    return ChartOut(
        accounts=[AccountBalanceOut(id=b.account.id, code=b.account.code, name=b.account.name, account_class=b.account.account_class,
                                    debit=b.debit, credit=b.credit, balance=b.balance) for b in balances],
        tie_out=TieOutOut(debits=t.debits, credits=t.credits, balanced=t.balanced, member_credits_gl=t.member_credits_gl,
                          member_sub_ledger=t.member_sub_ledger, ties=t.ties),
    )


def entry_out(db: Session, entry: JournalEntry, codes: dict[uuid.UUID, str]) -> JournalEntryOut:
    reversed_by = ledger.reversal_of(db, entry.id)
    reverses = db.get(JournalEntry, entry.reverses_entry_id) if entry.reverses_entry_id else None
    return JournalEntryOut(
        id=entry.id, reference=ledger.entry_ref(entry), entry_date=entry.entry_date, period=entry.period, entity_type=entry.entity_type,
        entity_id=entry.entity_id, description=entry.description, total=sum((l.debit for l in entry.lines), ZERO),
        reverses=ledger.entry_ref(reverses) if reverses else None, reversed_by=ledger.entry_ref(reversed_by) if reversed_by else None,
        created_by=_name(db, entry.created_by_user_id),
        lines=[LedgerLineOut(code=l.gl_account.code, account_name=l.gl_account.name, debit=l.debit, credit=l.credit, member_id=l.member_id,
                             member_code=codes.get(l.member_id) if l.member_id else None, component=l.component, description=l.description)
               for l in entry.lines],
    )


@router.get("/funds/{fund_id}/ledger/entries", response_model=JournalPage)
def entries(
    fund_id: uuid.UUID, period: date | None = None, entity_type: str | None = None, account: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db), user: User = Depends(require_staff),
) -> JournalPage:
    """Journal entries, newest first; filter by processing month, business event or GL account code."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    query = select(JournalEntry).where(JournalEntry.fund_id == fund.id)
    if period:
        query = query.where(JournalEntry.period == ledger.periods.month_start(period))
    if entity_type:
        query = query.where(JournalEntry.entity_type == entity_type)
    if account:
        from app.models.ledger import GLAccount, LedgerLine
        query = query.where(JournalEntry.id.in_(
            select(LedgerLine.entry_id).join(GLAccount, GLAccount.id == LedgerLine.gl_account_id)
            .where(LedgerLine.fund_id == fund.id, GLAccount.code == account)
        ))
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar()
    rows = db.execute(query.order_by(JournalEntry.number.desc()).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    member_ids = {l.member_id for e in rows for l in e.lines if l.member_id}
    codes = dict(db.execute(select(Member.id, Member.account_code).where(Member.id.in_(member_ids))).all()) if member_ids else {}
    return JournalPage(items=[entry_out(db, e, codes) for e in rows], total=total)


@router.get("/members/{member_id}/transactions", response_model=MemberLedgerOut)
def member_transactions(
    member_id: uuid.UUID, component: Component | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db), user: User = Depends(require_staff),
) -> MemberLedgerOut:
    """The member's account: balance by component and transactions, newest first."""
    member = get_member(db, user, member_id)
    by_component = ledger.member_balances_by_component(db, member.id)
    components = []
    for comp in Component:
        codes = by_component.get(comp)
        if not codes:
            continue
        group = {g: sum((v for c, v in codes.items() if ledger.code_group(c) == g), ZERO) for g in ("contributions", "bonus", "withdrawals", "other")}
        components.append(ComponentBalanceOut(component=comp, balance=sum(codes.values(), ZERO), **group))
    query = select(MemberTransaction).where(MemberTransaction.member_id == member.id)
    if component:
        query = query.where(MemberTransaction.component == component)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar()
    rows = db.execute(query.order_by(MemberTransaction.transaction_date.desc(), MemberTransaction.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).scalars().all()
    reversed_ids = set(db.execute(select(MemberTransaction.reverses_transaction_id).where(
        MemberTransaction.reverses_transaction_id.in_([r.id for r in rows]))).scalars()) if rows else set()
    entries = {e.id: e for e in db.execute(select(JournalEntry).where(JournalEntry.id.in_({r.journal_entry_id for r in rows}))).scalars()} if rows else {}
    return MemberLedgerOut(
        balance=ledger.member_balance(db, member.id), components=components, total=total,
        transactions=[MemberTransactionOut(
            id=r.id, transaction_date=r.transaction_date, period=r.period, transaction_code=r.transaction_code, transaction_name=r.transaction_name,
            effect=r.effect, component=r.component, amount=r.amount, contribution_month=r.contribution_month, reference=r.reference,
            description=r.description, journal_reference=ledger.entry_ref(entries[r.journal_entry_id]), reversed=r.id in reversed_ids,
            is_reversal=r.reverses_transaction_id is not None,
        ) for r in rows],
    )
