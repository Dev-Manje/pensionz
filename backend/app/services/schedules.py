"""Contribution schedules (FR-CON-001, FR-CON-003).

A schedule is one employer's member-by-member split of a month's
contributions. It is built as a **draft** — by uploading the template
(prefilled with expected amounts) or capturing lines — and every change
re-checks every line:

errors (block submission): no matching member; member of another employer
or fund; status that doesn't allow contributions; joined after the month;
member twice on the schedule; negative amounts or an empty line; AVC where
the category doesn't allow it; no category terms for the month; a percent
contribution below the statutory minimum (regulatory parameters
`min_employee_contribution_pct` / `min_employer_contribution_pct`, DC only).

warnings (allowed): amount differs from the category rate × salary; salary
differs from the member record; no salary to check rates against; member
already on another schedule for the month.

`submit` hands a draft without errors over for allocation (status ready);
`reopen` brings a ready schedule back to draft until it is allocated.
"""
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.category import BenefitCategory, BenefitDesign, RateType
from app.models.contribution import ContributionSchedule, ContributionScheduleLine, ScheduleSource, ScheduleStatus
from app.models.fund import Fund
from app.models.identity import User, UserRole
from app.models.member import Member
from app.models.mixins import utcnow
from app.models.scheme import Scheme
from app.services import audit, config_resolver, ledger, member_records, members, periods
from app.services.io import contribution_schedule as io_schedule

MAKERS = (UserRole.contributions_officer,)
ZERO = Decimal("0.00")
AMOUNTS = ("employee", "employer", "voluntary", "severance")


def month_end(month: date) -> date:
    return periods.next_month(month) - timedelta(days=1)


def _fmt(d: Decimal) -> str:
    return f"MWK {d:,.2f}"


# ---- expected contributions


@dataclass
class Expected:
    salary: Decimal | None
    employee: Decimal | None
    employer: Decimal | None
    employee_rate: Decimal | None
    employer_rate: Decimal | None


def _amount(rate_type: RateType, rate: Decimal | None, salary: Decimal | None) -> Decimal | None:
    if rate is None:
        return None
    if rate_type == RateType.fixed:
        return ledger.money(rate)
    return ledger.money(salary * rate / 100) if salary is not None else None


def expected_for(db: Session, member: Member, month: date) -> Expected:
    """What the category's rates give on the member's recorded salary for the month."""
    terms = config_resolver.category_terms(db, member.category_id, month_end(month)) if member.category_id else None
    salary_row = member_records.salary_on(db, member.id, month_end(month))
    salary = salary_row.pensionable_salary if salary_row else None
    if terms is None:
        return Expected(salary, None, None, None, None)
    return Expected(
        salary,
        _amount(terms.employee_rate_type, terms.employee_rate, salary),
        _amount(terms.employer_rate_type, terms.employer_rate, salary),
        terms.employee_rate if terms.employee_rate_type == RateType.percent else None,
        terms.employer_rate if terms.employer_rate_type == RateType.percent else None,
    )


def expected_members(db: Session, scheme: Scheme, month: date) -> list[Member]:
    """Members who should be on the employer's schedule for the month: active and joined by its end."""
    return list(db.execute(select(Member).where(
        Member.scheme_id == scheme.id, Member.status.in_(members.ACTIVITIES["contributions"]),
        Member.date_joined_fund <= month_end(month),
    ).order_by(Member.account_code)).scalars())


# ---- line checks


def _check_line(db: Session, schedule: ContributionSchedule, line: ContributionScheduleLine, seen: dict[uuid.UUID, int],
                others: dict[uuid.UUID, str]) -> None:
    errors: list[str] = []
    warnings: list[str] = []
    month = schedule.contribution_month
    member = None
    if line.account_code:
        member = db.execute(select(Member).where(Member.fund_id == schedule.fund_id, func.upper(Member.account_code) == line.account_code.upper())).scalar_one_or_none()
    elif line.employee_no:
        found = db.execute(select(Member).where(Member.scheme_id == schedule.scheme_id, Member.employee_no == line.employee_no)).scalars().all()
        if len(found) > 1:
            errors.append(f"More than one member has employee number {line.employee_no} — give the account code")
        member = found[0] if len(found) == 1 else None
    line.member_id = member.id if member else None
    if member is None:
        if not errors:
            errors.append("No member of this fund has that account code" if line.account_code else
                          "Give the member's account code (or a known employee number)")
    else:
        if not line.member_name:
            line.member_name = member.full_name
        if member.scheme_id != schedule.scheme_id:
            errors.append(f"{member.account_code} belongs to another employer")
        if not members.allows(member.status, "contributions"):
            errors.append(f"{member.account_code} is {members.STATUS_LABELS[member.status].lower()} — contributions aren't accepted")
        if member.date_joined_fund > month_end(month):
            errors.append(f"{member.account_code} joined on {member.date_joined_fund:%d %b %Y}, after this month")
        if member.id in seen:
            errors.append(f"{member.account_code} is already on row {seen[member.id]}")
        else:
            seen[member.id] = line.row_no
        if member.id in others:
            warnings.append(f"{member.account_code} is also on schedule {others[member.id]} for this month")

    amounts = [getattr(line, k) for k in AMOUNTS]
    if any(a < 0 for a in amounts):
        errors.append("Amounts can't be negative")
    elif not any(a > 0 for a in amounts):
        errors.append("The line has no contributions")

    if member is not None and member.scheme_id == schedule.scheme_id:
        _check_rates(db, member, line, month, errors, warnings)
    line.errors, line.warnings = errors, warnings


def _check_rates(db: Session, member: Member, line: ContributionScheduleLine, month: date, errors: list[str], warnings: list[str]) -> None:
    terms = config_resolver.category_terms(db, member.category_id, month_end(month)) if member.category_id else None
    if terms is None:
        errors.append(f"{member.account_code} has no benefit category terms in force for {periods.label(month)}")
        return
    if line.voluntary > 0 and not terms.avc_allowed:
        errors.append("Voluntary contributions aren't allowed in this member's category")
    recorded = member_records.salary_on(db, member.id, month_end(month))
    salary = line.pensionable_salary if line.pensionable_salary is not None else (recorded.pensionable_salary if recorded else None)
    if line.pensionable_salary is not None and recorded and line.pensionable_salary != recorded.pensionable_salary:
        warnings.append(f"Salary {_fmt(line.pensionable_salary)} differs from the member record ({_fmt(recorded.pensionable_salary)}) — "
                        "update it through a salary change")
    percent = terms.employee_rate_type == RateType.percent or (terms.employer_rate is not None and terms.employer_rate_type == RateType.percent)
    if salary is None and percent:
        warnings.append("No salary given or on record, so the rates can't be checked")
    for side, rate_type, rate, minimum_key in (
        ("employee", terms.employee_rate_type, terms.employee_rate, "min_employee_contribution_pct"),
        ("employer", terms.employer_rate_type, terms.employer_rate, "min_employer_contribution_pct"),
    ):
        amount = getattr(line, side)
        expected = _amount(rate_type, rate, salary)
        if terms.design == BenefitDesign.dc and salary:
            minimum_pct = config_resolver.regulatory(db, minimum_key, month_end(month))
            if minimum_pct is not None and amount < ledger.money(salary * minimum_pct / 100):
                errors.append(f"{side.capitalize()} contribution {_fmt(amount)} is below the statutory minimum of {minimum_pct.normalize():f}% "
                              f"({_fmt(ledger.money(salary * minimum_pct / 100))})")
                continue
        if expected is not None and amount != expected:
            basis = f"{rate.normalize():f}% of {_fmt(salary)}" if rate_type == RateType.percent else "the fixed amount"
            warnings.append(f"Expected {side} contribution {_fmt(expected)} ({basis})")


def recheck(db: Session, schedule: ContributionSchedule) -> None:
    """Re-validates every line and refreshes the totals. Does not commit."""
    db.flush()
    others_q = select(ContributionScheduleLine.member_id, ContributionSchedule.reference).join(
        ContributionSchedule, ContributionSchedule.id == ContributionScheduleLine.schedule_id
    ).where(ContributionSchedule.scheme_id == schedule.scheme_id, ContributionSchedule.contribution_month == schedule.contribution_month,
            ContributionSchedule.status != ScheduleStatus.cancelled, ContributionSchedule.id != schedule.id,
            ContributionScheduleLine.member_id.is_not(None))
    others = {m: ref for m, ref in db.execute(others_q)}
    seen: dict[uuid.UUID, int] = {}
    for line in sorted(schedule.lines, key=lambda l: l.row_no):
        _check_line(db, schedule, line, seen, others)
    for key in AMOUNTS:
        setattr(schedule, f"total_{key}", sum((getattr(l, key) for l in schedule.lines), ZERO))
    schedule.total = sum((l.total for l in schedule.lines), ZERO)
    schedule.line_count = len(schedule.lines)
    schedule.error_count = sum(1 for l in schedule.lines if l.errors)
    schedule.warning_count = sum(1 for l in schedule.lines if l.warnings)
    db.flush()


# ---- building a draft


def _require_draft(schedule: ContributionSchedule) -> None:
    if schedule.status != ScheduleStatus.draft:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft schedule can be changed — re-open it first")


def _scheme(db: Session, fund: Fund, scheme_id: uuid.UUID) -> Scheme:
    scheme = db.get(Scheme, scheme_id)
    if scheme is None or scheme.fund_id != fund.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That employer isn't part of this fund")
    return scheme


def _reference(db: Session, scheme: Scheme, month: date) -> str:
    base = f"{scheme.code}-{month:%Y%m}"
    n = db.execute(select(func.count()).where(ContributionSchedule.scheme_id == scheme.id,
                                              ContributionSchedule.contribution_month == month)).scalar()
    return base if n == 0 else f"{base}-S{n}"


def create(db: Session, user: User, fund: Fund, scheme_id: uuid.UUID, month: date, *, supplementary: bool,
           source: ScheduleSource, notes: str | None = None, prefill: bool = False) -> ContributionSchedule:
    scheme = _scheme(db, fund, scheme_id)
    month = periods.month_start(month)
    if month > periods.month_start(date.today()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Schedules can't be for a future month")
    if not supplementary:
        clash = db.execute(select(ContributionSchedule).where(
            ContributionSchedule.scheme_id == scheme.id, ContributionSchedule.contribution_month == month,
            ContributionSchedule.status != ScheduleStatus.cancelled, ContributionSchedule.supplementary.is_(False),
        )).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"{scheme.code} already has a schedule for {periods.label(month)} ({clash.reference}) — "
                                "change that one, or make this a supplementary schedule")
    schedule = ContributionSchedule(fund_id=fund.id, scheme_id=scheme.id, contribution_month=month, supplementary=supplementary,
                                    reference=_reference(db, scheme, month), status=ScheduleStatus.draft, source=source,
                                    notes=(notes or "").strip() or None, created_by_user_id=user.id)
    db.add(schedule)
    db.flush()
    if prefill:
        fill_expected(db, schedule, commit=False)
    recheck(db, schedule)
    audit.record(db, user.id, "contribution_schedule", schedule.id, "created",
                 after={"reference": schedule.reference, "source": source.value}, fund_id=fund.id)
    db.commit()
    db.refresh(schedule)
    return schedule


def fill_expected(db: Session, schedule: ContributionSchedule, *, commit: bool = True) -> ContributionSchedule:
    """Adds a line, at the expected amounts, for every expected member not on the schedule yet."""
    _require_draft(schedule)
    scheme = db.get(Scheme, schedule.scheme_id)
    present = {l.member_id for l in schedule.lines}
    row = max((l.row_no for l in schedule.lines), default=1)
    for m in expected_members(db, scheme, schedule.contribution_month):
        if m.id in present:
            continue
        e = expected_for(db, m, schedule.contribution_month)
        row += 1
        schedule.lines.append(ContributionScheduleLine(
            row_no=row, member_id=m.id, account_code=m.account_code, employee_no=m.employee_no, member_name=m.full_name,
            pensionable_salary=e.salary, employee=e.employee or ZERO, employer=e.employer or ZERO,
        ))
    recheck(db, schedule)
    if commit:
        db.commit()
        db.refresh(schedule)
    return schedule


@dataclass
class LineValues:
    account_code: str | None
    employee_no: str | None
    member_name: str | None
    pensionable_salary: Decimal | None
    employee: Decimal
    employer: Decimal
    voluntary: Decimal
    severance: Decimal


def _set(line: ContributionScheduleLine, v: LineValues) -> None:
    line.account_code = (v.account_code or "").strip().upper() or None
    line.employee_no = (v.employee_no or "").strip() or None
    line.member_name = (v.member_name or "").strip() or None
    line.pensionable_salary = ledger.money(v.pensionable_salary) if v.pensionable_salary is not None else None
    for k in AMOUNTS:
        setattr(line, k, ledger.money(getattr(v, k) or 0))


def add_line(db: Session, schedule: ContributionSchedule, v: LineValues) -> ContributionSchedule:
    _require_draft(schedule)
    line = ContributionScheduleLine(row_no=max((l.row_no for l in schedule.lines), default=1) + 1)
    _set(line, v)
    schedule.lines.append(line)
    recheck(db, schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def _line(schedule: ContributionSchedule, line_id: uuid.UUID) -> ContributionScheduleLine:
    line = next((l for l in schedule.lines if l.id == line_id), None)
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")
    return line


def update_line(db: Session, schedule: ContributionSchedule, line_id: uuid.UUID, v: LineValues) -> ContributionSchedule:
    _require_draft(schedule)
    _set(_line(schedule, line_id), v)
    recheck(db, schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def remove_line(db: Session, schedule: ContributionSchedule, line_id: uuid.UUID) -> ContributionSchedule:
    _require_draft(schedule)
    schedule.lines.remove(_line(schedule, line_id))
    recheck(db, schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def upload(db: Session, user: User, schedule: ContributionSchedule, filename: str, content: bytes) -> ContributionSchedule:
    """Replaces the draft's lines with the file's rows (problems become line errors)."""
    _require_draft(schedule)
    rows = io_schedule.read(filename, content)
    schedule.lines.clear()
    db.flush()
    unreadable: dict[int, list[str]] = {}
    for row_no, raw in rows:
        values: dict = {}
        for key in io_schedule.MONEY_KEYS:
            try:
                values[key] = io_schedule.parse_money(raw.get(key))
            except ValueError as e:
                unreadable.setdefault(row_no, []).append(f"{io_schedule.label(key)}: {e}")
                values[key] = None
        line = ContributionScheduleLine(row_no=row_no)
        _set(line, LineValues(raw.get("account_code"), raw.get("employee_no"), raw.get("member_name"), values["pensionable_salary"],
                              values["employee"] or ZERO, values["employer"] or ZERO, values["voluntary"] or ZERO, values["severance"] or ZERO))
        schedule.lines.append(line)
    schedule.source, schedule.filename = ScheduleSource.upload, filename[:200]
    recheck(db, schedule)
    # Unreadable amounts are reported on top of the line checks.
    for line in schedule.lines:
        if line.row_no in unreadable:
            line.errors = [*unreadable[line.row_no], *line.errors]
    schedule.error_count = sum(1 for l in schedule.lines if l.errors)
    audit.record(db, user.id, "contribution_schedule", schedule.id, "uploaded",
                 after={"filename": schedule.filename, "rows": schedule.line_count, "errors": schedule.error_count}, fund_id=schedule.fund_id)
    db.commit()
    db.refresh(schedule)
    return schedule


def template_for(db: Session, fund: Fund, scheme_id: uuid.UUID, month: date) -> tuple[str, bytes]:
    scheme = _scheme(db, fund, scheme_id)
    month = periods.month_start(month)
    rows = []
    for m in expected_members(db, scheme, month):
        e = expected_for(db, m, month)
        rows.append({"account_code": m.account_code, "employee_no": m.employee_no, "member_name": m.full_name,
                     "pensionable_salary": e.salary, "employee": e.employee, "employer": e.employer})
    return f"schedule-{scheme.code}-{month:%Y-%m}.xlsx", io_schedule.template(f"{scheme.code} — {scheme.name}", month, rows)


# ---- hand over


def submit(db: Session, user: User, schedule: ContributionSchedule) -> ContributionSchedule:
    _require_draft(schedule)
    recheck(db, schedule)
    if not schedule.lines:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The schedule has no lines")
    if schedule.error_count:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Fix the {schedule.error_count} line(s) with errors first")
    schedule.status, schedule.submitted_by_user_id, schedule.submitted_at = ScheduleStatus.ready, user.id, utcnow()
    audit.record(db, user.id, "contribution_schedule", schedule.id, "submitted", after={"total": schedule.total}, fund_id=schedule.fund_id)
    db.commit()
    db.refresh(schedule)
    return schedule


def reopen(db: Session, user: User, schedule: ContributionSchedule) -> ContributionSchedule:
    if schedule.status != ScheduleStatus.ready:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a schedule waiting for allocation can be re-opened")
    schedule.status, schedule.submitted_by_user_id, schedule.submitted_at = ScheduleStatus.draft, None, None
    audit.record(db, user.id, "contribution_schedule", schedule.id, "reopened", fund_id=schedule.fund_id)
    db.commit()
    db.refresh(schedule)
    return schedule


def cancel(db: Session, user: User, schedule: ContributionSchedule) -> ContributionSchedule:
    if schedule.status not in (ScheduleStatus.draft, ScheduleStatus.ready):
        raise HTTPException(status.HTTP_409_CONFLICT, "An allocated schedule can't be cancelled — reverse the allocation instead")
    schedule.status = ScheduleStatus.cancelled
    audit.record(db, user.id, "contribution_schedule", schedule.id, "cancelled", fund_id=schedule.fund_id)
    db.commit()
    db.refresh(schedule)
    return schedule
