"""Member enquiries and statements (FR-ENQ-001, 003, 008), from the member sub-ledger.

Balances are positive amounts owed to the member (legacy PFS stored them negative;
see docs/legacy/PFS-analysis.md). Everything here is a read of
`member_transaction` — nothing is stored.

- **Benefit statement** as at a date, legacy layout: employee account (EE
  contributions, bonus on them, AVC, bonus on AVC, transfers in, less withdrawals)
  and employer account (ER contributions, severance, bonus, less withdrawals).
- **Client statement** for a date range: opening balance, each transaction with
  debit / credit / running balance, aged analysis of contributions the employer
  still owes for the member (FR-MEM-012, the default decided for "what is aged").
- **Transaction trail** for a date range with totals per component.
- **Contributions trail** month by month (EE, company, EE earning, company
  earning, earning rate) and the **voluntary contributions trail**.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bonus import BonusDeclaration, BonusKind, BonusRun, BonusRunStatus
from app.models.ledger import Component, MemberTransaction
from app.models.member import Member
from app.models.reference import TransactionEffect
from app.services import arrears, ledger, periods

ZERO = Decimal("0.00")
EMPLOYEE_SIDE = (Component.employee, Component.voluntary, Component.transfer_in)
EMPLOYER_SIDE = (Component.employer, Component.severance)


def signed(t: MemberTransaction) -> Decimal:
    return t.amount if t.effect == TransactionEffect.credit else -t.amount


def transactions(db: Session, member: Member, *, start: date | None = None, end: date | None = None) -> list[MemberTransaction]:
    query = select(MemberTransaction).where(MemberTransaction.member_id == member.id)
    if start:
        query = query.where(MemberTransaction.transaction_date >= start)
    if end:
        query = query.where(MemberTransaction.transaction_date <= end)
    return list(db.execute(query.order_by(MemberTransaction.transaction_date, MemberTransaction.created_at)).scalars())


def balance_on(db: Session, member: Member, on: date) -> Decimal:
    return sum((signed(t) for t in transactions(db, member, end=on)), ZERO)


def contributions_up_to(rows: list[MemberTransaction]) -> date | None:
    """The latest contribution month credited (allocations not reversed)."""
    reversed_ids = {t.reverses_transaction_id for t in rows if t.reverses_transaction_id}
    months = [t.contribution_month for t in rows if t.transaction_code == 1 and t.contribution_month and t.id not in reversed_ids]
    return max(months, default=None)


# ---- benefit statement (FR-ENQ-003)


@dataclass
class BenefitStatement:
    member: Member
    as_at: date
    employee_lines: list[tuple[str, Decimal]]
    employer_lines: list[tuple[str, Decimal]]
    contributions_up_to: date | None

    @property
    def employee_total(self) -> Decimal:
        return sum((v for _, v in self.employee_lines), ZERO)

    @property
    def employer_total(self) -> Decimal:
        return sum((v for _, v in self.employer_lines), ZERO)

    @property
    def total(self) -> Decimal:
        return self.employee_total + self.employer_total


def benefit_statement(db: Session, member: Member, as_at: date) -> BenefitStatement:
    rows = transactions(db, member, end=as_at)
    sums: dict[tuple[Component, str], Decimal] = defaultdict(lambda: ZERO)
    for t in rows:
        group = ledger.code_group(t.transaction_code)
        sums[(t.component, "contributions" if group == "other" else group)] += signed(t)

    def g(comp, group):
        return sums[(comp, group)]

    employee = [
        ("Employee contributions", g(Component.employee, "contributions")),
        ("Bonus on employee contributions", g(Component.employee, "bonus")),
        ("Employee voluntary contributions", g(Component.voluntary, "contributions")),
        ("Bonus on voluntary contributions", g(Component.voluntary, "bonus")),
    ]
    if g(Component.transfer_in, "contributions") or g(Component.transfer_in, "bonus"):
        employee += [("Transfers in", g(Component.transfer_in, "contributions")),
                     ("Bonus on transfers in", g(Component.transfer_in, "bonus"))]
    employee.append(("Less employee withdrawals", sum((g(c, "withdrawals") for c in EMPLOYEE_SIDE), ZERO)))
    employer = [
        ("Employer contributions", g(Component.employer, "contributions")),
        ("Severance", g(Component.severance, "contributions")),
        ("Bonus on employer account", g(Component.employer, "bonus") + g(Component.severance, "bonus")),
        ("Less employer account withdrawals", sum((g(c, "withdrawals") for c in EMPLOYER_SIDE), ZERO)),
    ]
    return BenefitStatement(member, as_at, employee, employer, contributions_up_to(rows))


# ---- client statement (FR-ENQ-008)


@dataclass
class StatementLine:
    transaction_date: date
    description: str
    reference: str | None
    transaction: str
    component: Component
    debit: Decimal
    credit: Decimal
    balance: Decimal


@dataclass
class ClientStatement:
    member: Member
    start: date
    end: date
    opening: Decimal
    lines: list[StatementLine]
    ageing: list[tuple[str, Decimal]]

    @property
    def closing(self) -> Decimal:
        return self.lines[-1].balance if self.lines else self.opening


def _line_text(t: MemberTransaction) -> str:
    return t.description or t.transaction_name


def client_statement(db: Session, member: Member, start: date, end: date) -> ClientStatement:
    opening = balance_on(db, member, date.fromordinal(start.toordinal() - 1))
    running = opening
    lines = []
    for t in transactions(db, member, start=start, end=end):
        running += signed(t)
        lines.append(StatementLine(
            t.transaction_date, _line_text(t), t.reference, f"{t.transaction_code} {t.transaction_name}", t.component,
            t.amount if t.effect == TransactionEffect.debit else ZERO, t.amount if t.effect == TransactionEffect.credit else ZERO, running,
        ))
    return ClientStatement(member, start, end, opening, lines, ageing(db, member, end))


AGEING_LABELS = ["Not yet due"] + [label for _, _, label in arrears.BUCKETS]


def ageing(db: Session, member: Member, as_at: date) -> list[tuple[str, Decimal]]:
    """Contributions still owed for the member, by how long overdue (Not yet due, 1–30 … over 150 days)."""
    totals = {label: ZERO for label in AGEING_LABELS}
    for m in arrears.member_arrears(db, member, as_at):
        if m.arrears:
            totals[arrears.bucket(m.days_overdue) if m.days_overdue else "Not yet due"] += m.arrears
    return list(totals.items())


# ---- transaction trail (FR-ENQ-008)


@dataclass
class Trail:
    member: Member
    start: date
    end: date
    lines: list[StatementLine]
    totals: dict[Component, tuple[Decimal, Decimal]] = field(default_factory=dict)


def transaction_trail(db: Session, member: Member, start: date, end: date) -> Trail:
    statement = client_statement(db, member, start, end)
    totals: dict[Component, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for line in statement.lines:
        totals[line.component][0] += line.debit
        totals[line.component][1] += line.credit
    return Trail(member, start, end, statement.lines, {c: (d, cr) for c, (d, cr) in totals.items()})


# ---- contributions trails (FR-ENQ-008)


@dataclass
class TrailMonth:
    month: date
    employee: Decimal = ZERO
    company: Decimal = ZERO
    employee_earning: Decimal = ZERO
    company_earning: Decimal = ZERO
    voluntary: Decimal = ZERO
    voluntary_earning: Decimal = ZERO
    earning_rate: Decimal | None = None

    @property
    def earning(self) -> Decimal:
        return self.employee_earning + self.company_earning

    @property
    def total(self) -> Decimal:
        return self.employee + self.company + self.earning


def _rates_by_tag(db: Session, fund_id) -> dict[date, Decimal]:
    """Rate credited for each bonus period (by the period's tag month): the final rate when posted, else the interim."""
    rows = db.execute(
        select(BonusDeclaration.period_end, BonusDeclaration.kind, BonusDeclaration.rate)
        .join(BonusRun, BonusRun.declaration_id == BonusDeclaration.id)
        .where(BonusDeclaration.fund_id == fund_id, BonusRun.status == BonusRunStatus.posted)
    ).all()
    out: dict[date, Decimal] = {}
    for period_end, kind, rate in sorted(rows, key=lambda r: r[1] == BonusKind.final):
        out[periods.month_start(period_end)] = rate
    return out


def contributions_trail(db: Session, member: Member, start: date, end: date) -> list[TrailMonth]:
    months: dict[date, TrailMonth] = {}
    rates = _rates_by_tag(db, member.fund_id)

    def month(d: date) -> TrailMonth:
        return months.setdefault(d, TrailMonth(d, earning_rate=rates.get(d)))

    first, last = periods.month_start(start), periods.month_start(end)
    for t in transactions(db, member):
        tag = t.contribution_month or periods.month_start(t.transaction_date)
        if not (first <= tag <= last):
            continue
        group = ledger.code_group(t.transaction_code)
        if group == "withdrawals":
            continue
        amount, row = signed(t), month(tag)
        bonus = group == "bonus"
        if t.component == Component.employee or t.component == Component.transfer_in:
            if bonus:
                row.employee_earning += amount
            else:
                row.employee += amount
        elif t.component in EMPLOYER_SIDE:
            if bonus:
                row.company_earning += amount
            else:
                row.company += amount
        elif t.component == Component.voluntary:
            if bonus:
                row.voluntary_earning += amount
            else:
                row.voluntary += amount
    return [months[k] for k in sorted(months)]
