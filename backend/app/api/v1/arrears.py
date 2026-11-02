import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.api.v1.members import get_member
from app.core.database import get_db
from app.models.identity import User
from app.services import arrears, fund_access, schedules
from app.services.schedules import ZERO

router = APIRouter(tags=["arrears"])


class MonthOut(BaseModel):
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
    status: str


class EmployerArrearsOut(BaseModel):
    scheme_id: uuid.UUID
    employer: str
    total_arrears: Decimal
    total_interest: Decimal | None
    months_in_arrears: int
    oldest_bucket: str | None
    months: list[MonthOut]


class BucketOut(BaseModel):
    label: str
    amount: Decimal


class ArrearsOut(BaseModel):
    as_at: date
    interest_rate_set: bool
    total_arrears: Decimal
    total_interest: Decimal | None
    ageing: list[BucketOut]
    employers: list[EmployerArrearsOut]


class ExpectedLineOut(BaseModel):
    member_id: uuid.UUID
    account_code: str
    name: str
    salary: Decimal | None
    employee: Decimal | None
    employer: Decimal | None


class ExpectedOut(BaseModel):
    month: date
    due_date: date
    total_employee: Decimal
    total_employer: Decimal
    total: Decimal
    lines: list[ExpectedLineOut]


class MemberMonthOut(BaseModel):
    month: date
    expected: Decimal | None
    credited: Decimal
    arrears: Decimal
    days_overdue: int
    bucket: str


class MemberArrearsOut(BaseModel):
    total_arrears: Decimal
    ageing: list[BucketOut]
    months: list[MemberMonthOut]


@router.get("/funds/{fund_id}/arrears", response_model=ArrearsOut)
def fund_arrears(fund_id: uuid.UUID, as_at: date | None = None, scheme_id: uuid.UUID | None = None,
                 db: Session = Depends(get_db), user: User = Depends(require_staff)) -> ArrearsOut:
    """Expected vs paid contributions per employer and month, with ageing and late-payment interest (not posted)."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    as_at = as_at or date.today()
    results = arrears.fund_arrears(db, fund.id, as_at, scheme_id)
    employers = []
    for r in results:
        overdue = [m for m in r.months if m.days_overdue > 0 and m.arrears > 0]
        employers.append(EmployerArrearsOut(
            scheme_id=r.scheme.id, employer=f"{r.scheme.code} — {r.scheme.name}", total_arrears=r.total_arrears,
            total_interest=r.total_interest, months_in_arrears=len(overdue), oldest_bucket=overdue[0].bucket if overdue else None,
            months=[MonthOut(**vars(m)) for m in reversed(r.months)],
        ))
    interests = [e.total_interest for e in employers if e.total_interest is not None]
    return ArrearsOut(
        as_at=as_at, interest_rate_set=arrears.config_resolver.regulatory(db, "late_payment_interest_pct", as_at) is not None,
        total_arrears=sum((e.total_arrears for e in employers), ZERO), total_interest=sum(interests, ZERO) if interests else None,
        ageing=[BucketOut(**b) for b in arrears.ageing(results)], employers=employers,
    )


@router.get("/funds/{fund_id}/expected-contributions", response_model=ExpectedOut)
def expected(fund_id: uuid.UUID, scheme_id: uuid.UUID, month: date, db: Session = Depends(get_db),
             user: User = Depends(require_staff)) -> ExpectedOut:
    """The expected schedule for an employer and month (FR-CON-002): active members × category rates on salary."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    scheme = schedules._scheme(db, fund, scheme_id)
    month = month.replace(day=1)
    lines = []
    for m in schedules.expected_members(db, scheme, month):
        e = schedules.expected_for(db, m, month)
        lines.append(ExpectedLineOut(member_id=m.id, account_code=m.account_code, name=m.full_name, salary=e.salary,
                                     employee=e.employee, employer=e.employer))
    ee = sum((l.employee or ZERO for l in lines), ZERO)
    er = sum((l.employer or ZERO for l in lines), ZERO)
    return ExpectedOut(month=month, due_date=arrears.due_date(scheme, month), total_employee=ee, total_employer=er, total=ee + er, lines=lines)


@router.get("/members/{member_id}/arrears", response_model=MemberArrearsOut)
def member_arrears(member_id: uuid.UUID, as_at: date | None = None, db: Session = Depends(get_db),
                   user: User = Depends(require_staff)) -> MemberArrearsOut:
    """Months the member's employer hasn't paid in full, aged from the due date (FR-MEM-012)."""
    member = get_member(db, user, member_id)
    months = arrears.member_arrears(db, member, as_at or date.today())
    totals = {label: ZERO for _, _, label in arrears.BUCKETS}
    for m in months:
        if m.days_overdue > 0 and m.arrears > 0:
            totals[m.bucket] += m.arrears
    return MemberArrearsOut(total_arrears=sum(totals.values(), ZERO), ageing=[BucketOut(label=k, amount=v) for k, v in totals.items()],
                            months=[MemberMonthOut(**vars(m)) for m in reversed(months)])
