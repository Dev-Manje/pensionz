"""Expected contributions, arrears, late-payment interest and ageing
(FR-CON-002, FR-CON-008, FR-MEM-012).

Arrears are worked out, not posted (cash-to-suspense recipe, decided
2026-11-02): for each employer and contribution month,

    expected  = Σ category rate × salary on record for members in service that month
    paid      = Σ gross contributions on the employer's allocated schedules for
                that month (a reversed allocation puts its schedule back to
                "ready", so it no longer counts)
    arrears   = expected − paid, once the due date has passed

The due date is the employer's contribution day in the following month. Age
is days past the due date, bucketed 1–30 / 31–60 / 61–90 / 91–120 / 121–150 /
over 150 (legacy aged analysis). Late-payment interest = arrears × rate ×
days / 365 at the regulatory `late_payment_interest_pct` in force on the due
date; with no rate set, no interest is shown. Charging the interest (Dr 1200 /
Cr 4300) waits for finance to confirm the recipe.

"In service that month" uses the member record as it stands: joined by the
month end, not exited/deceased before the month started, not currently
inactive, and still with this employer (employer transfers aren't traced
back yet).
"""
import calendar
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.contribution import ContributionSchedule, ScheduleStatus
from app.models.member import Member, MemberStatus
from app.models.scheme import Scheme, SchemeStatus
from app.services import config_resolver, ledger, periods, schedules

ZERO = Decimal("0.00")
MAX_MONTHS = 24
BUCKETS = ((1, 30, "1–30 days"), (31, 60, "31–60 days"), (61, 90, "61–90 days"), (91, 120, "91–120 days"),
           (121, 150, "121–150 days"), (151, None, "Over 150 days"))


def due_date(scheme: Scheme, month: date) -> date:
    nxt = periods.next_month(month)
    return nxt.replace(day=min(scheme.contribution_day, calendar.monthrange(nxt.year, nxt.month)[1]))


def bucket(days: int) -> str:
    if days <= 0:
        return "Not yet due"
    return next(label for lo, hi, label in BUCKETS if days >= lo and (hi is None or days <= hi))


def _months(first: date, last: date) -> list[date]:
    out, m = [], periods.month_start(first)
    while m <= last:
        out.append(m)
        m = periods.next_month(m)
    return out[-MAX_MONTHS:]


def in_service(member: Member, month: date) -> bool:
    if member.date_joined_fund > schedules.month_end(month):
        return False
    if member.exit_date and member.exit_date < month:
        return False
    if member.date_of_death and member.date_of_death < month:
        return False
    return member.status != MemberStatus.inactive


def interest(db: Session, amount: Decimal, due: date, as_at: date) -> Decimal | None:
    rate = config_resolver.regulatory(db, "late_payment_interest_pct", due)
    days = (as_at - due).days
    if rate is None or days <= 0 or amount <= 0:
        return None if rate is None else ZERO
    return ledger.money(amount * rate / 100 * days / 365)


def _scheduled_gross(db: Session, scheme_id: uuid.UUID) -> dict[tuple[uuid.UUID, date], Decimal]:
    """Gross contributions per (member, month) on allocated schedules — what the employer actually paid."""
    out: dict[tuple[uuid.UUID, date], Decimal] = {}
    for s in db.execute(select(ContributionSchedule).where(
        ContributionSchedule.scheme_id == scheme_id, ContributionSchedule.status == ScheduleStatus.allocated,
    )).scalars():
        for line in s.lines:
            if line.member_id:
                key = (line.member_id, s.contribution_month)
                out[key] = out.get(key, ZERO) + line.total
    return out


@dataclass
class MonthArrears:
    month: date
    due_date: date
    members_expected: int
    members_without_estimate: int
    expected: Decimal
    paid: Decimal
    arrears: Decimal
    days_overdue: int
    bucket: str
    interest: Decimal | None
    status: str  # paid | part_paid | unpaid | not_due


@dataclass
class SchemeArrears:
    scheme: Scheme
    months: list[MonthArrears] = field(default_factory=list)

    @property
    def total_arrears(self) -> Decimal:
        return sum((m.arrears for m in self.months if m.days_overdue > 0), ZERO)

    @property
    def total_interest(self) -> Decimal | None:
        values = [m.interest for m in self.months if m.interest is not None]
        return sum(values, ZERO) if values else None


def scheme_arrears(db: Session, scheme: Scheme, as_at: date) -> SchemeArrears:
    members = list(db.execute(select(Member).where(Member.scheme_id == scheme.id)).scalars())
    out = SchemeArrears(scheme)
    if not members:
        return out
    first = max(scheme.join_date or date.min, min(m.date_joined_fund for m in members))
    last = periods.month_start(as_at)
    paid_by = _scheduled_gross(db, scheme.id)
    for month in _months(first, last):
        due = due_date(scheme, month)
        expected = paid = ZERO
        count = missing = 0
        for m in members:
            if not in_service(m, month):
                continue
            count += 1
            e = schedules.expected_for(db, m, month)
            if e.employee is None and e.employer is None:
                missing += 1
            expected += (e.employee or ZERO) + (e.employer or ZERO)
            paid += paid_by.get((m.id, month), ZERO)
        if count == 0:
            continue
        days = (as_at - due).days
        owing = max(expected - paid, ZERO)
        status_ = "not_due" if days <= 0 and paid < expected else "paid" if paid >= expected else "part_paid" if paid > 0 else "unpaid"
        out.months.append(MonthArrears(month, due, count, missing, expected, paid, owing, max(days, 0), bucket(days) if owing else "—",
                                       interest(db, owing, due, as_at) if days > 0 else None, status_))
    return out


def fund_arrears(db: Session, fund_id: uuid.UUID, as_at: date, scheme_id: uuid.UUID | None = None) -> list[SchemeArrears]:
    q = select(Scheme).where(Scheme.fund_id == fund_id, Scheme.status != SchemeStatus.exited).order_by(Scheme.code)
    if scheme_id:
        q = q.where(Scheme.id == scheme_id)
    return [scheme_arrears(db, s, as_at) for s in db.execute(q).scalars()]


def ageing(results: list[SchemeArrears]) -> list[dict]:
    totals = {label: ZERO for _, _, label in BUCKETS}
    for r in results:
        for m in r.months:
            if m.days_overdue > 0 and m.arrears > 0:
                totals[m.bucket] += m.arrears
    return [{"label": label, "amount": amount} for label, amount in totals.items()]


# ---- one member (FR-MEM-012)


@dataclass
class MemberMonth:
    month: date
    expected: Decimal | None
    credited: Decimal
    arrears: Decimal
    days_overdue: int
    bucket: str


def member_arrears(db: Session, member: Member, as_at: date) -> list[MemberMonth]:
    if member.scheme_id is None:
        return []
    scheme = db.get(Scheme, member.scheme_id)
    paid_by = _scheduled_gross(db, scheme.id)
    out = []
    for month in _months(max(scheme.join_date or date.min, member.date_joined_fund), periods.month_start(as_at)):
        if not in_service(member, month):
            continue
        e = schedules.expected_for(db, member, month)
        expected = None if e.employee is None and e.employer is None else (e.employee or ZERO) + (e.employer or ZERO)
        credited = paid_by.get((member.id, month), ZERO)
        days = (as_at - due_date(scheme, month)).days
        owing = max((expected or ZERO) - credited, ZERO)
        out.append(MemberMonth(month, expected, credited, owing, max(days, 0), bucket(days) if owing else "—"))
    return out
