"""A member's beneficiary nominations, salary history and service history
(FR-MEM-008, FR-MEM-009), each through maker-checker (member checker):

- `beneficiary_nomination` — a whole signed nomination replaces the current one; shares
  total exactly 100%; beneficiaries under 18 need a guardian; every version is kept;
- `member_salary` — a monthly salary from a date (a second version on the same date
  corrects it); the latest version on or before a date applies (`salary_on`);
- `member_service` — the whole list of service periods (for DB benefits), gaps being
  breaks and part-time periods counting at their factor (`service_years`)."""
import calendar
import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.identity import User
from app.models.member import Beneficiary, BeneficiaryNomination, Member, MemberSalary, MemberServicePeriod, MemberStatus
from app.models.reference import ReferenceItem, ReferenceList
from app.schemas.member import NominationIn, SalaryIn, ServiceIn
from app.services import approvals, audit
from app.services.kyc import today
from app.services.members import CHECKERS, age_on

KIND_NOMINATION = "beneficiary_nomination"
KIND_SALARY = "member_salary"
KIND_SERVICE = "member_service"

CENT = Decimal("0.01")
YEARS_DP = Decimal("0.0001")
# Members who can still nominate / have salaries recorded.
NOMINATING = frozenset({MemberStatus.active, MemberStatus.inactive, MemberStatus.deferred, MemberStatus.pensioner})
SALARIED = frozenset({MemberStatus.active, MemberStatus.inactive})


def _bad(message: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, message)


def pending_id(db: Session, kind: str, member_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(select(ApprovalRequest.id).where(
        ApprovalRequest.kind == kind, ApprovalRequest.entity_id == str(member_id), ApprovalRequest.status == ApprovalStatus.pending,
    )).scalar_one_or_none()


def _lock(db: Session, request: ApprovalRequest) -> Member:
    member = db.execute(select(Member).where(Member.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That member no longer exists")
    return member


def _money(value: Decimal) -> str:
    return f"MWK {value:,.2f}"


def _date(value: date | None) -> str:
    return value.strftime("%d %b %Y").lstrip("0") if value else "open"


# ---- beneficiaries (FR-MEM-008)


def relationship_names(db: Session) -> dict[str, str]:
    return dict(db.execute(select(ReferenceItem.code, ReferenceItem.name).where(ReferenceItem.list_key == ReferenceList.relationship)).all())


def current_nomination(db: Session, member_id: uuid.UUID) -> BeneficiaryNomination | None:
    return db.execute(select(BeneficiaryNomination).where(
        BeneficiaryNomination.member_id == member_id, BeneficiaryNomination.is_current.is_(True))).scalar_one_or_none()


def is_minor(born: date | None, on: date | None = None) -> bool:
    return born is not None and age_on(born, on or today()) < 18


def _check_nomination(db: Session, member: Member, data: NominationIn) -> None:
    if member.status not in NOMINATING:
        raise _bad(f"A member who is {member.status.value} can't make a new nomination")
    if data.signed_date > today():
        raise _bad("The signed date can't be in the future")
    names = relationship_names(db)
    total = sum((b.share_pct for b in data.beneficiaries), Decimal("0"))
    if total.quantize(CENT) != Decimal("100.00"):
        raise _bad(f"Shares must add up to 100% (they add up to {total.quantize(CENT)}%)")
    seen = set()
    for i, b in enumerate(data.beneficiaries, start=1):
        who = b.full_name or f"Beneficiary {i}"
        key = b.full_name.strip().lower()
        if key in seen:
            raise _bad(f"{who} is listed twice")
        seen.add(key)
        if b.relationship not in names:
            raise _bad(f"{who}: choose the relationship from the list")
        if b.date_of_birth and b.date_of_birth > today():
            raise _bad(f"{who}: the date of birth can't be in the future")
        if is_minor(b.date_of_birth):
            if not (b.guardian_name and b.guardian_relationship and b.guardian_phone):
                raise _bad(f"{who} is under 18 — give the guardian's name, relationship and phone")
            if b.guardian_relationship not in names:
                raise _bad(f"{who}: choose the guardian's relationship from the list")


def _lines(db: Session, beneficiaries: list[dict]) -> list[str]:
    names = relationship_names(db)
    out = []
    for b in beneficiaries:
        born = date.fromisoformat(b["date_of_birth"]) if b.get("date_of_birth") else None
        line = f"{b['full_name']} ({names.get(b['relationship'], b['relationship'])}) — {Decimal(b['share_pct']):.2f}%"
        if born:
            line += f", born {_date(born)}"
        if b.get("guardian_name") and is_minor(born):
            line += f"; guardian {b['guardian_name']} ({names.get(b.get('guardian_relationship'), '')}, {b.get('guardian_phone')})"
        out.append(line)
    return out


def _as_dicts(nomination: BeneficiaryNomination | None) -> list[dict]:
    if nomination is None:
        return []
    return [audit._jsonable({
        "full_name": b.full_name, "relationship": b.relationship_code, "date_of_birth": b.date_of_birth, "id_number": b.id_number,
        "phone": b.phone, "email": b.email, "address": b.address, "share_pct": b.share_pct, "guardian_name": b.guardian_name,
        "guardian_relationship": b.guardian_relationship, "guardian_phone": b.guardian_phone, "guardian_id_number": b.guardian_id_number,
    }) for b in nomination.beneficiaries]


def propose_nomination(db: Session, maker: User, member: Member, data: NominationIn) -> ApprovalRequest:
    _check_nomination(db, member, data)
    raw = audit._jsonable([b.model_dump() for b in data.beneficiaries])
    current = current_nomination(db, member.id)
    request = approvals.submit(
        db, maker, KIND_NOMINATION, entity_type="member", entity_id=member.id,
        summary=f"Beneficiary nomination for {member.account_code} {member.full_name} ({len(raw)} beneficiar{'y' if len(raw) == 1 else 'ies'})",
        payload={"action": "nominate", "signed_date": _date(data.signed_date), "beneficiaries": _lines(db, raw), "note": data.note,
                 "_signed_date": data.signed_date, "_beneficiaries": raw},
        previous={"signed_date": _date(current.signed_date) if current else None, "beneficiaries": _lines(db, _as_dicts(current)),
                  "note": current.note if current else None},
        fund_id=member.fund_id,
    )
    db.commit()
    db.refresh(request)
    return request


def _apply_nomination(db: Session, request: ApprovalRequest, checker: User) -> None:
    member = _lock(db, request)
    p = request.payload
    data = NominationIn(signed_date=p["_signed_date"], note=p.get("note"), beneficiaries=p["_beneficiaries"])
    _check_nomination(db, member, data)
    version = (db.execute(select(func.max(BeneficiaryNomination.version)).where(BeneficiaryNomination.member_id == member.id)).scalar() or 0) + 1
    current = current_nomination(db, member.id)
    if current is not None:
        current.is_current = False
        db.flush()
    nomination = BeneficiaryNomination(member_id=member.id, version=version, signed_date=data.signed_date, note=data.note,
                                       requested_by_user_id=request.initiated_by_user_id, approved_by_user_id=checker.id,
                                       approval_request_id=request.id)
    for i, b in enumerate(data.beneficiaries):
        values = b.model_dump()
        values["relationship_code"] = values.pop("relationship")
        nomination.beneficiaries.append(Beneficiary(position=i, **values))
    db.add(nomination)
    db.flush()
    audit.record(db, checker.id, "member", member.id, "beneficiaries_nominated",
                 before={"version": current.version if current else None}, after={"version": version, "beneficiaries": len(data.beneficiaries)},
                 fund_id=member.fund_id)


# ---- salary (FR-MEM-009)


def salary_on(db: Session, member_id: uuid.UUID, as_of: date) -> MemberSalary | None:
    return db.execute(select(MemberSalary).where(MemberSalary.member_id == member_id, MemberSalary.effective_from <= as_of)
                      .order_by(MemberSalary.effective_from.desc()).limit(1)).scalar_one_or_none()


def _check_salary(member: Member, data: SalaryIn) -> None:
    if member.status not in SALARIED:
        raise _bad(f"Salaries are recorded only for active or inactive members (this member is {member.status.value})")
    earliest = min(d for d in (member.date_joined_employer, member.date_joined_fund) if d)
    if data.effective_from < earliest:
        raise _bad(f"The salary can't start before the member joined ({_date(earliest)})")
    if data.effective_from > today() + timedelta(days=366):
        raise _bad("The salary can't start more than a year from now")


def propose_salary(db: Session, maker: User, member: Member, data: SalaryIn) -> ApprovalRequest:
    _check_salary(member, data)
    pensionable = data.pensionable_salary or data.basic_salary
    existing = db.execute(select(MemberSalary).where(MemberSalary.member_id == member.id, MemberSalary.effective_from == data.effective_from)).scalar_one_or_none()
    before = salary_on(db, member.id, data.effective_from)
    request = approvals.submit(
        db, maker, KIND_SALARY, entity_type="member", entity_id=member.id,
        summary=(f"{'Correct' if existing else 'New'} salary for {member.account_code} {member.full_name} from {_date(data.effective_from)}: "
                 f"{_money(pensionable)} pensionable"),
        payload={"action": "correct" if existing else "salary", "effective_from": _date(data.effective_from),
                 "basic_salary": _money(data.basic_salary), "pensionable_salary": _money(pensionable), "note": data.note,
                 "_values": audit._jsonable({"effective_from": data.effective_from, "basic_salary": data.basic_salary,
                                             "pensionable_salary": pensionable, "note": data.note})},
        previous={"effective_from": _date(before.effective_from) if before else None,
                  "basic_salary": _money(before.basic_salary) if before else None,
                  "pensionable_salary": _money(before.pensionable_salary) if before else None, "note": before.note if before else None},
        fund_id=member.fund_id,
    )
    db.commit()
    db.refresh(request)
    return request


def _apply_salary(db: Session, request: ApprovalRequest, checker: User) -> None:
    member = _lock(db, request)
    v = request.payload["_values"]
    data = SalaryIn(**v)
    _check_salary(member, data)
    row = db.execute(select(MemberSalary).where(MemberSalary.member_id == member.id, MemberSalary.effective_from == data.effective_from)).scalar_one_or_none()
    before = audit._jsonable({"basic_salary": row.basic_salary, "pensionable_salary": row.pensionable_salary}) if row else None
    if row is None:
        row = MemberSalary(member_id=member.id, effective_from=data.effective_from)
        db.add(row)
    row.basic_salary, row.pensionable_salary, row.note = data.basic_salary, data.pensionable_salary, data.note
    row.approved_by_user_id, row.approval_request_id = checker.id, request.id
    db.flush()
    audit.record(db, checker.id, "member", member.id, "salary_recorded", before=before, after=v, fund_id=member.fund_id)


# ---- service (FR-MEM-009)


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def period_years(start: date, end: date, factor: Decimal = Decimal("1")) -> Decimal:
    """Service from `start` to `end` (both inclusive) in years: whole months ÷ 12 plus
    leftover days ÷ 365.25, times the part-time factor, to 4 dp."""
    stop = end + timedelta(days=1)
    months = (stop.year - start.year) * 12 + stop.month - start.month
    while months > 0 and _add_months(start, months) > stop:
        months -= 1
    days = (stop - _add_months(start, months)).days
    years = (Decimal(months) / 12 + Decimal(days) / Decimal("365.25")) * factor
    return years.quantize(YEARS_DP, rounding=ROUND_HALF_UP)


def service_years(periods: list[MemberServicePeriod], as_of: date) -> Decimal:
    """Pensionable service up to `as_of` (an open period runs to it)."""
    total = Decimal("0")
    for p in periods:
        if p.start_date > as_of:
            continue
        end = min(p.end_date or as_of, as_of)
        total += period_years(p.start_date, end, p.part_time_factor)
    return total.quantize(YEARS_DP)


def service_periods(db: Session, member_id: uuid.UUID) -> list[MemberServicePeriod]:
    return list(db.execute(select(MemberServicePeriod).where(MemberServicePeriod.member_id == member_id)
                           .order_by(MemberServicePeriod.start_date)).scalars())


def _check_service(member: Member, data: ServiceIn) -> None:
    periods = sorted(data.periods, key=lambda p: p.start_date)
    for i, p in enumerate(periods, start=1):
        if p.start_date < member.date_of_birth:
            raise _bad(f"Period {i} starts before the member was born")
        if p.start_date > today():
            raise _bad(f"Period {i} starts in the future")
        if p.end_date and p.end_date < p.start_date:
            raise _bad(f"Period {i} ends before it starts")
        if p.end_date and p.end_date > today():
            raise _bad(f"Period {i} ends in the future — leave the end date empty for current service")
    for a, b in zip(periods, periods[1:]):
        if a.end_date is None:
            raise _bad("Only the latest period can be open (no end date)")
        if b.start_date <= a.end_date:
            raise _bad(f"Periods overlap around {_date(b.start_date)}")


def _period_lines(periods) -> list[str]:
    out = []
    for p in sorted(periods, key=lambda p: p.start_date):
        line = f"{_date(p.start_date)} – {_date(p.end_date)}"
        if Decimal(p.part_time_factor) != 1:
            line += f" at {Decimal(p.part_time_factor) * 100:.0f}% part-time"
        if p.note:
            line += f" ({p.note})"
        out.append(line)
    return out


def propose_service(db: Session, maker: User, member: Member, data: ServiceIn) -> ApprovalRequest:
    _check_service(member, data)
    current = service_periods(db, member.id)
    ordered = sorted(data.periods, key=lambda p: p.start_date)
    raw = audit._jsonable([p.model_dump() for p in ordered])
    key = lambda p: (p.start_date, p.end_date, Decimal(p.part_time_factor), p.note)  # noqa: E731
    if [key(p) for p in ordered] == [key(p) for p in current]:
        raise _bad("Nothing has changed")
    request = approvals.submit(
        db, maker, KIND_SERVICE, entity_type="member", entity_id=member.id,
        summary=f"Service history for {member.account_code} {member.full_name}: {data.reason}"[:300],
        payload={"action": "service", "periods": _period_lines(data.periods), "reason": data.reason, "_periods": raw},
        previous={"periods": _period_lines(current), "reason": None},
        fund_id=member.fund_id,
    )
    db.commit()
    db.refresh(request)
    return request


def _apply_service(db: Session, request: ApprovalRequest, checker: User) -> None:
    member = _lock(db, request)
    data = ServiceIn(periods=request.payload["_periods"], reason=request.payload["reason"])
    _check_service(member, data)
    before = _period_lines(service_periods(db, member.id))
    for row in service_periods(db, member.id):
        db.delete(row)
    db.flush()
    for p in data.periods:
        db.add(MemberServicePeriod(member_id=member.id, **p.model_dump()))
    db.flush()
    audit.record(db, checker.id, "member", member.id, "service_changed", before={"periods": before},
                 after={"periods": _period_lines(data.periods), "reason": data.reason}, fund_id=member.fund_id)


for _kind, _label, _apply in ((KIND_NOMINATION, "Beneficiary nomination", _apply_nomination),
                              (KIND_SALARY, "Member salary", _apply_salary), (KIND_SERVICE, "Member service history", _apply_service)):
    approvals.register(approvals.ApprovalKind(name=_kind, label=_label, checker_roles=CHECKERS, apply=_apply))
