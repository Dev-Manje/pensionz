"""Fund ledgers (FR-ACC-001…003, pz-accounting).

- `post(...)` writes one balanced journal entry: Σ debits = Σ credits within
  the fund, every line on one side only, amounts rounded half-up to 2 dp,
  dated in the fund's open processing month (409 otherwise). Callers pass the
  business event (`entity_type`, `entity_id`) the entry belongs to.
- `post_member_transactions(...)` is the same post driven by member
  transactions: each transaction type (Setup → Transaction types) names its
  debit and credit GL codes, so an Initial Allocation of 1,000 is Dr 2100 /
  Cr 2000 with the member and component on both lines. Extra lines (fees,
  premiums) go in the same entry.
- `reverse(...)` mirrors an entry into the open month and gives every member
  transaction its paired reversal type. An entry is reversed at most once,
  and a reversal is never reversed — post the original again instead.

The chart is the *proposed* chart (pz-accounting) — finance still to confirm.
Each fund gets it the first time its ledger is used (`ensure_chart`).
"""
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import case, exists, func, select, text
from sqlalchemy.orm import Session

from app.models.identity import User
from app.models.ledger import DEBIT_NORMAL, AccountClass, Book, Component, GLAccount, JournalEntry, LedgerLine, MemberTransaction
from app.models.member import Member
from app.models.reference import TransactionEffect, TransactionType
from app.services import audit, periods

CENT = Decimal("0.01")
ZERO = Decimal("0")

MEMBER_CREDITS = "2000"
UNALLOCATED = "2100"

# Legacy transaction codes grouped the way the benefit statement shows them.
_CODE_GROUPS = {1: "contributions", 2: "contributions", 3: "withdrawals", 4: "withdrawals", 5: "bonus", 6: "bonus"}


def code_group(code: int) -> str:
    return _CODE_GROUPS.get(code, "other")

# code, name, class — proposed fund chart (pz-accounting), to confirm with finance.
FUND_CHART: list[tuple[str, str, AccountClass]] = [
    ("1000", "Fund Bank — Contributions Collection", AccountClass.asset),
    ("1010", "Fund Bank — Benefits Payment", AccountClass.asset),
    ("1100", "Investments at Fair Value", AccountClass.asset),
    ("1200", "Contributions Receivable", AccountClass.asset),
    ("1300", "Investment Income Receivable", AccountClass.asset),
    ("2000", "Member Fund Credits", AccountClass.liability),
    ("2100", "Unallocated Contributions", AccountClass.liability),
    ("2200", "Benefits Payable", AccountClass.liability),
    ("2300", "PAYE / Benefit Tax Payable", AccountClass.liability),
    ("2350", "Statutory Levies Payable", AccountClass.liability),
    ("2400", "Risk Premiums Payable", AccountClass.liability),
    ("2450", "Investment Management Fees Payable", AccountClass.liability),
    ("2500", "Administration Fees Payable", AccountClass.liability),
    ("2600", "Forfeiture / Reserve Account", AccountClass.liability),
    ("2700", "Pensioners Payable", AccountClass.liability),
    ("2800", "Refunds Payable to Employers", AccountClass.liability),
    ("3000", "DB Fund Reserve / Surplus", AccountClass.equity),
    ("4000", "Contributions Income (DB)", AccountClass.income),
    ("4100", "Investment Income", AccountClass.income),
    ("4200", "Fair Value Gains/Losses", AccountClass.income),
    ("4300", "Late-Payment Interest from Employers", AccountClass.income),
    ("5000", "Benefits Paid (DB)", AccountClass.expense),
    ("5100", "Administration Fees", AccountClass.expense),
    ("5200", "Investment Management Fees", AccountClass.expense),
    ("5300", "Statutory Levies", AccountClass.expense),
]
ADMIN_CHART: list[tuple[str, str, AccountClass]] = [
    ("1500", "Fees Receivable from Funds", AccountClass.asset),
    ("1510", "Administrator Operating Bank", AccountClass.asset),
    ("4500", "Administration Fee Income", AccountClass.income),
]


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Line:
    code: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    member_id: uuid.UUID | None = None
    scheme_id: uuid.UUID | None = None
    component: Component | None = None
    description: str | None = None


def dr(code: str, amount, **kw) -> Line:
    return Line(code, debit=money(amount), **kw)


def cr(code: str, amount, **kw) -> Line:
    return Line(code, credit=money(amount), **kw)


@dataclass
class MemberPosting:
    member: Member
    transaction_code: int
    component: Component
    amount: Decimal
    reference: str | None = None
    description: str | None = None
    contribution_month: date | None = None
    reverses: MemberTransaction | None = field(default=None)


# ---- chart


def ensure_chart(db: Session, fund_id: uuid.UUID | None) -> dict[str, GLAccount]:
    """The fund's accounts by code (the administrator book when `fund_id` is None),
    creating any missing accounts of the proposed chart."""
    book = Book.fund if fund_id is not None else Book.administrator
    rows = db.execute(select(GLAccount).where(GLAccount.fund_id.is_(None) if fund_id is None else GLAccount.fund_id == fund_id)).scalars().all()
    by_code = {row.code: row for row in rows}
    added = False
    for code, name, cls in (FUND_CHART if fund_id is not None else ADMIN_CHART):
        if code not in by_code:
            row = GLAccount(fund_id=fund_id, book=book, code=code, name=name, account_class=cls)
            db.add(row)
            by_code[code] = row
            added = True
    if added:
        db.flush()
    return by_code


# ---- posting


def _transaction_type(db: Session, code: int) -> TransactionType:
    row = db.execute(select(TransactionType).where(TransactionType.code == code)).scalar_one_or_none()
    if row is None or not row.active:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Transaction type {code} doesn't exist or is retired — check Setup → Transaction types")
    if not row.debit_gl_code or not row.credit_gl_code:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Transaction type {code} ({row.name}) has no GL accounts — set them in Setup → Transaction types")
    return row


def _next_number(db: Session, fund_id: uuid.UUID | None, book: Book) -> int:
    # Serialise numbering per book and fund for the rest of the transaction.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"journal:{book.value}:{fund_id}"})
    current = db.execute(
        select(func.max(JournalEntry.number)).where(
            JournalEntry.book == book, JournalEntry.fund_id.is_(None) if fund_id is None else JournalEntry.fund_id == fund_id,
        )
    ).scalar()
    return (current or 0) + 1


def post(
    db: Session,
    fund_id: uuid.UUID | None,
    *,
    entity_type: str,
    entity_id: object | None,
    entry_date: date,
    description: str,
    lines: list[Line],
    user: User | None,
    reverses: JournalEntry | None = None,
) -> JournalEntry:
    """Writes one balanced entry. Does not commit."""
    book = Book.fund if fund_id is not None else Book.administrator
    period = periods.require_open(db, fund_id, entry_date).period if fund_id is not None else periods.month_start(entry_date)
    lines = [line for line in lines if line.debit or line.credit]
    if not lines:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to post — every amount is zero")
    for line in lines:
        line.debit, line.credit = money(line.debit), money(line.credit)
        if line.debit < 0 or line.credit < 0 or (line.debit and line.credit):
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Ledger line on {line.code} must be a positive debit or credit")
    total_dr, total_cr = sum(l.debit for l in lines), sum(l.credit for l in lines)
    if total_dr != total_cr:
        # A bug upstream must fail loudly rather than unbalance the fund's books.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Unbalanced post for {entity_type} {entity_id}: debits {total_dr} ≠ credits {total_cr}")
    chart = ensure_chart(db, fund_id)
    missing = sorted({l.code for l in lines if l.code not in chart or not chart[l.code].active})
    if missing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"GL account(s) {', '.join(missing)} aren't in this fund's chart of accounts")
    entry = JournalEntry(
        fund_id=fund_id, book=book, number=_next_number(db, fund_id, book), entry_date=entry_date, period=period,
        entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None, description=description[:300],
        reverses_entry_id=reverses.id if reverses else None, created_by_user_id=user.id if user else None,
    )
    db.add(entry)
    db.flush()
    for position, line in enumerate(lines, start=1):
        db.add(LedgerLine(
            entry_id=entry.id, fund_id=fund_id, gl_account_id=chart[line.code].id, position=position, debit=line.debit, credit=line.credit,
            member_id=line.member_id, scheme_id=line.scheme_id, component=line.component, description=line.description,
        ))
    db.flush()
    db.refresh(entry)
    return entry


def post_member_transactions(
    db: Session,
    fund_id: uuid.UUID,
    *,
    entity_type: str,
    entity_id: object | None,
    entry_date: date,
    description: str,
    postings: list[MemberPosting],
    other_lines: list[Line] | None = None,
    user: User | None,
) -> tuple[JournalEntry, list[MemberTransaction]]:
    """One entry for a batch of member transactions plus any extra lines. Does not commit."""
    lines: list[Line] = []
    resolved: list[tuple[MemberPosting, TransactionType]] = []
    for p in postings:
        if p.member.fund_id != fund_id:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Member {p.member.account_code} isn't in this fund")
        p.amount = money(p.amount)
        if p.amount <= 0:
            continue
        tt = _transaction_type(db, p.transaction_code)
        tag = {"member_id": p.member.id, "scheme_id": p.member.scheme_id, "component": p.component, "description": p.description}
        lines += [dr(tt.debit_gl_code, p.amount, **tag), cr(tt.credit_gl_code, p.amount, **tag)]
        resolved.append((p, tt))
    entry = post(db, fund_id, entity_type=entity_type, entity_id=entity_id, entry_date=entry_date, description=description,
                 lines=lines + list(other_lines or []), user=user)
    return entry, _record(db, entry, resolved, user)


def _record(db: Session, entry: JournalEntry, resolved: list[tuple[MemberPosting, TransactionType]], user: User | None) -> list[MemberTransaction]:
    rows = []
    for p, tt in resolved:
        row = MemberTransaction(
            member_id=p.member.id, fund_id=entry.fund_id, transaction_code=tt.code, transaction_name=tt.name, effect=tt.effect,
            component=p.component, amount=p.amount, transaction_date=entry.entry_date, period=entry.period,
            contribution_month=p.contribution_month, reference=p.reference, description=p.description,
            journal_entry_id=entry.id, reverses_transaction_id=p.reverses.id if p.reverses else None,
            created_by_user_id=user.id if user else None,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def reversal_of(db: Session, entry_id: uuid.UUID) -> JournalEntry | None:
    return db.execute(select(JournalEntry).where(JournalEntry.reverses_entry_id == entry_id)).scalar_one_or_none()


def reverse(
    db: Session, entry: JournalEntry, *, user: User | None, entry_date: date, reason: str,
    entity_type: str | None = None, entity_id: object | None = None,
) -> JournalEntry:
    """Posts the mirror image of `entry` (dated in the open month) and gives each
    of its member transactions the paired reversal type, so balances return
    exactly to where they were. Does not commit."""
    if entry.reverses_entry_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This entry is itself a reversal and can't be reversed — post the original again instead")
    # Lock the original so two reversals can't race.
    db.execute(select(JournalEntry.id).where(JournalEntry.id == entry.id).with_for_update())
    if reversal_of(db, entry.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{entry_ref(entry)} has already been reversed")
    originals = db.execute(select(MemberTransaction).where(MemberTransaction.journal_entry_id == entry.id)).scalars().all()
    members = {m.id: m for m in db.execute(select(Member).where(Member.id.in_({t.member_id for t in originals}))).scalars()}
    resolved: list[tuple[MemberPosting, TransactionType]] = []
    for t in originals:
        tt = _transaction_type(db, t.transaction_code)
        if tt.reversal_code is None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Transaction type {tt.code} ({tt.name}) has no reversal type — set it in Setup")
        resolved.append((MemberPosting(members[t.member_id], tt.reversal_code, t.component, t.amount, reference=t.reference,
                                       description=f"Reversal: {reason}"[:300], contribution_month=t.contribution_month, reverses=t),
                         _transaction_type(db, tt.reversal_code)))
    mirrored = [Line(line.gl_account.code, debit=line.credit, credit=line.debit, member_id=line.member_id, scheme_id=line.scheme_id,
                     component=line.component, description=line.description) for line in entry.lines]
    reversal = post(db, entry.fund_id, entity_type=entity_type or entry.entity_type,
                    entity_id=entity_id if entity_id is not None else entry.entity_id, entry_date=entry_date,
                    description=f"Reversal of {entry_ref(entry)}: {reason}", lines=mirrored, user=user, reverses=entry)
    _record(db, reversal, resolved, user)
    audit.record(db, user.id if user else None, "journal_entry", entry.id, "reversed",
                 after={"reversal": entry_ref(reversal), "reason": reason}, fund_id=entry.fund_id)
    return reversal


# ---- balances


@dataclass
class AccountBalance:
    account: GLAccount
    debit: Decimal
    credit: Decimal

    @property
    def balance(self) -> Decimal:
        """In the account's normal direction (assets/expenses debit, the rest credit)."""
        return self.debit - self.credit if self.account.account_class in DEBIT_NORMAL else self.credit - self.debit


def account_balances(db: Session, fund_id: uuid.UUID | None, *, up_to_period: date | None = None) -> list[AccountBalance]:
    chart = ensure_chart(db, fund_id)
    query = select(LedgerLine.gl_account_id, func.coalesce(func.sum(LedgerLine.debit), 0), func.coalesce(func.sum(LedgerLine.credit), 0)) \
        .join(JournalEntry, JournalEntry.id == LedgerLine.entry_id) \
        .where(LedgerLine.fund_id.is_(None) if fund_id is None else LedgerLine.fund_id == fund_id)
    if up_to_period is not None:
        query = query.where(JournalEntry.period <= up_to_period)
    sums = {row[0]: (Decimal(row[1]), Decimal(row[2])) for row in db.execute(query.group_by(LedgerLine.gl_account_id))}
    return [AccountBalance(a, *sums.get(a.id, (ZERO, ZERO))) for a in sorted(chart.values(), key=lambda a: a.code)]


def gl_balance(db: Session, fund_id: uuid.UUID, code: str) -> Decimal:
    return next((b.balance for b in account_balances(db, fund_id) if b.account.code == code), ZERO)


def _case_signed():
    return case((MemberTransaction.effect == TransactionEffect.credit, MemberTransaction.amount), else_=-MemberTransaction.amount)


def member_balance(db: Session, member_id: uuid.UUID) -> Decimal:
    return Decimal(db.execute(
        select(func.coalesce(func.sum(_case_signed()), 0)).where(MemberTransaction.member_id == member_id)
    ).scalar())


def member_balances_by_component(db: Session, member_id: uuid.UUID) -> dict[Component, dict[int, Decimal]]:
    """{component: {transaction code: signed total}} — credits positive, debits negative."""
    rows = db.execute(
        select(MemberTransaction.component, MemberTransaction.transaction_code, func.sum(_case_signed()))
        .where(MemberTransaction.member_id == member_id)
        .group_by(MemberTransaction.component, MemberTransaction.transaction_code)
    ).all()
    out: dict[Component, dict[int, Decimal]] = defaultdict(dict)
    for component, code, total in rows:
        out[component][code] = Decimal(total)
    return out


def members_total(db: Session, fund_id: uuid.UUID) -> Decimal:
    return Decimal(db.execute(
        select(func.coalesce(func.sum(_case_signed()), 0)).where(MemberTransaction.fund_id == fund_id)
    ).scalar())


@dataclass
class TieOut:
    debits: Decimal
    credits: Decimal
    member_credits_gl: Decimal
    member_sub_ledger: Decimal

    @property
    def balanced(self) -> bool:
        return self.debits == self.credits

    @property
    def ties(self) -> bool:
        return self.member_credits_gl == self.member_sub_ledger


def tie_out(db: Session, fund_id: uuid.UUID) -> TieOut:
    """Σ debits = Σ credits, and Σ member balances = GL 2000 (FR-ACC-004)."""
    balances = account_balances(db, fund_id)
    gl = next((b.balance for b in balances if b.account.code == MEMBER_CREDITS), ZERO)
    return TieOut(sum((b.debit for b in balances), ZERO), sum((b.credit for b in balances), ZERO), gl, members_total(db, fund_id))


def has_postings(db: Session, fund_id: uuid.UUID, period: date) -> bool:
    return bool(db.execute(select(exists().where(JournalEntry.fund_id == fund_id, JournalEntry.period == period))).scalar())


def entry_ref(entry: JournalEntry) -> str:
    return f"JE-{entry.number:06d}"
