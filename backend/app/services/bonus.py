"""Declared bonus / earnings (FR-EAR-001…004).

Method (decided by the user 2026-11-03), per member and component:

    bonus = opening balance × rate × days in period / 365
          + Σ each movement in the period × rate × days from its date to the period end / 365

- rate is % per annum from the declaration; days count both ends (a movement on
  the last day earns one day; the opening balance earns the whole period);
- movements are every non-bonus transaction in the period — allocations count
  positive, their reversals and withdrawals negative — so money that left
  stops earning from the day it left;
- earning components are on the declaration (default EE, ER, AVC, transfer-in);
- a member who exits in the period is calculated to their exit date;
- each member/component is rounded 2 dp half-up once, at the end;
- what was already credited for the same period (an interim run) is deducted:
  a positive difference posts Bonus (type 6, Dr 2600 / Cr 2000), a negative
  one Bonus Reversal (type 5) — the interim → final true-up.

Declarations: maker = finance, checker = finance checker (kind "bonus_declaration").
Runs: preview (draft) → send → finance checker approves → posted in one entry
(kind "bonus_run"); figures are recalculated at approval and must match the
preview. Reversal of a whole run or chosen members: kind "bonus_reversal".
"""
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.bonus import BonusDeclaration, BonusKind, BonusRun, BonusRunLine, BonusRunStatus as RS
from app.models.fund import Fund, FundType
from app.models.identity import User, UserRole
from app.models.ledger import Component, MemberTransaction
from app.models.member import Member
from app.models.mixins import utcnow
from app.models.reference import TransactionEffect
from app.services import approvals, audit, ledger, periods

MAKERS = (UserRole.finance,)
CHECKERS = frozenset({UserRole.finance_checker})
BONUS = 6
BONUS_REVERSAL = 5
BONUS_CODES = (BONUS, BONUS_REVERSAL)
DEFAULT_COMPONENTS = [Component.employee.value, Component.employer.value, Component.voluntary.value, Component.transfer_in.value]
BONUS_FUND_TYPES = (FundType.standalone_dc, FundType.umbrella_dc, FundType.personal_pension, FundType.minors_trust)
YEAR = Decimal(365)
ZERO = Decimal("0")


def _reference(db: Session, prefix: str) -> str:
    number = db.execute(text("SELECT nextval('bonus_reference_seq')")).scalar_one()
    return f"{prefix}-{date.today().year}-{number:05d}"


def period_tag(declaration: BonusDeclaration) -> date:
    """What bonus member transactions for this period carry in `contribution_month`."""
    return periods.month_start(declaration.period_end)


def _bonus_tag(t: MemberTransaction) -> date:
    return t.contribution_month or periods.month_start(t.transaction_date)


# ---- declarations


def propose_declaration(db: Session, maker: User, fund: Fund, *, kind: BonusKind, period_start: date, period_end: date,
                        rate: Decimal, components: list[Component] | None, resolution: str | None, notes: str | None) -> ApprovalRequest:
    if fund.fund_type not in BONUS_FUND_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Declared bonus applies to defined contribution funds")
    if period_end < period_start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The period can't end before it starts")
    if (period_end - period_start).days > 366:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A bonus period can be at most a year")
    if rate < 0 or rate > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The rate must be between 0% and 100% a year")
    comps = sorted({c.value for c in (components or [Component(c) for c in DEFAULT_COMPONENTS])})
    if not comps:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose at least one component that earns bonus")
    same = db.execute(select(BonusDeclaration.reference).where(
        BonusDeclaration.fund_id == fund.id, BonusDeclaration.kind == kind,
        BonusDeclaration.period_start <= period_end, BonusDeclaration.period_end >= period_start,
    )).scalars().first()
    if same:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{same} already declares a {kind.value} rate for an overlapping period")
    waiting = db.execute(select(ApprovalRequest.id).where(
        ApprovalRequest.kind == "bonus_declaration", ApprovalRequest.status == ApprovalStatus.pending,
        ApprovalRequest.fund_id == fund.id, ApprovalRequest.payload["kind"].astext == kind.value,
        ApprovalRequest.payload["period_start"].astext <= period_end.isoformat(),
        ApprovalRequest.payload["period_end"].astext >= period_start.isoformat(),
    )).first()
    if waiting:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A {kind.value} rate for an overlapping period is already waiting for approval")
    request = approvals.submit(
        db, maker, "bonus_declaration", entity_type="bonus_declaration", entity_id=None,
        summary=f"{kind.value.capitalize()} bonus {rate.normalize():f}% a year for {fund.code}, "
                f"{period_start:%d %b %Y} – {period_end:%d %b %Y}",
        payload={"kind": kind.value, "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
                 "rate": f"{rate:f}", "components": comps, "resolution": resolution, "notes": notes},
        fund_id=fund.id,
    )
    db.commit()
    db.refresh(request)
    return request


def _apply_declaration(db: Session, request: ApprovalRequest, checker: User) -> None:
    d = request.payload
    kind = BonusKind(d["kind"])
    start, end = date.fromisoformat(d["period_start"]), date.fromisoformat(d["period_end"])
    clash = db.execute(select(BonusDeclaration.reference).where(
        BonusDeclaration.fund_id == request.fund_id, BonusDeclaration.kind == kind,
        BonusDeclaration.period_start <= end, BonusDeclaration.period_end >= start,
    )).scalars().first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{clash} was declared for an overlapping period in the meantime")
    row = BonusDeclaration(
        fund_id=request.fund_id, reference=_reference(db, "BON"), kind=kind, period_start=start, period_end=end,
        rate=Decimal(d["rate"]), components=d["components"], resolution=d.get("resolution"), notes=d.get("notes"),
        declared_by_user_id=request.initiated_by_user_id, approved_by_user_id=checker.id,
    )
    db.add(row)
    db.flush()
    request.entity_id = str(row.id)
    audit.record(db, checker.id, "bonus_declaration", row.id, "declared", after=d | {"reference": row.reference}, fund_id=row.fund_id)


approvals.register(approvals.ApprovalKind(name="bonus_declaration", label="Bonus declaration", checker_roles=CHECKERS,
                                          apply=_apply_declaration))


# ---- calculation


@dataclass
class Calc:
    member: Member
    component: Component
    to_date: date
    days: int
    opening_balance: Decimal
    opening_bonus: Decimal
    movements: Decimal
    movements_bonus: Decimal
    calculated: Decimal
    already_credited: Decimal

    @property
    def amount(self) -> Decimal:
        return self.calculated - self.already_credited


def _signed(t: MemberTransaction) -> Decimal:
    return t.amount if t.effect == TransactionEffect.credit else -t.amount


def member_end(member: Member, declaration: BonusDeclaration, as_at: date | None) -> date | None:
    """The member's last day of the period, or None if they left before it began."""
    left = min((d for d in (member.exit_date, member.date_of_death) if d), default=None)
    end = declaration.period_end if as_at is None else min(as_at, declaration.period_end)
    if left is not None:
        if left < declaration.period_start:
            return None
        end = min(end, left)
    return end


def calculate(db: Session, declaration: BonusDeclaration, member: Member, to_date: date) -> list[Calc]:
    start, rate, tag = declaration.period_start, declaration.rate / Decimal(100), period_tag(declaration)
    days_total = (to_date - start).days + 1
    comps = [Component(c) for c in declaration.components]
    rows = db.execute(select(MemberTransaction).where(
        MemberTransaction.member_id == member.id, MemberTransaction.component.in_(comps),
    )).scalars().all()
    out = []
    for comp in comps:
        opening = movements = movements_bonus = already = ZERO
        for t in (r for r in rows if r.component == comp):
            amount = _signed(t)
            if t.transaction_code in BONUS_CODES:
                bonus_tag = _bonus_tag(t)
                if bonus_tag == tag:
                    already += amount
                elif bonus_tag < periods.month_start(start):
                    opening += amount
                continue
            if t.transaction_date < start:
                opening += amount
            elif t.transaction_date <= to_date:
                movements += amount
                movements_bonus += amount * rate * Decimal((to_date - t.transaction_date).days + 1) / YEAR
        if not (opening or movements or already):
            continue
        opening_bonus = opening * rate * Decimal(days_total) / YEAR
        calculated = max(ledger.money(opening_bonus + movements_bonus), ZERO)
        out.append(Calc(member, comp, to_date, days_total, ledger.money(opening), opening_bonus.quantize(Decimal("0.000001"), ROUND_HALF_UP),
                        ledger.money(movements), movements_bonus.quantize(Decimal("0.000001"), ROUND_HALF_UP), calculated, ledger.money(already)))
    return out


def _members(db: Session, run: BonusRun) -> list[Member]:
    query = select(Member).where(Member.fund_id == run.fund_id)
    if run.member_ids is not None:
        query = query.where(Member.id.in_([uuid.UUID(m) for m in run.member_ids]))
    return list(db.execute(query.order_by(Member.account_code)).scalars())


def _calculate_run(db: Session, run: BonusRun, declaration: BonusDeclaration) -> list[Calc]:
    out = []
    for member in _members(db, run):
        end = member_end(member, declaration, run.as_at if run.kind == BonusKind.interim and not _left_in_period(member, declaration) else None)
        if end is None:
            continue
        out += [c for c in calculate(db, declaration, member, end) if c.amount != 0 or c.calculated != 0]
    return out


def _left_in_period(member: Member, declaration: BonusDeclaration) -> bool:
    left = min((d for d in (member.exit_date, member.date_of_death) if d), default=None)
    return left is not None and declaration.period_start <= left <= declaration.period_end


def _fill(run: BonusRun, calcs: list[Calc]) -> None:
    run.lines.clear()
    for i, c in enumerate(calcs, start=1):
        run.lines.append(BonusRunLine(
            position=i, member_id=c.member.id, component=c.component, to_date=c.to_date, days=c.days,
            opening_balance=c.opening_balance, opening_bonus=c.opening_bonus, movements=c.movements, movements_bonus=c.movements_bonus,
            calculated=c.calculated, already_credited=c.already_credited, amount=c.amount,
        ))
    run.total_credit = sum((c.amount for c in calcs if c.amount > 0), ZERO)
    run.total_debit = -sum((c.amount for c in calcs if c.amount < 0), ZERO)
    run.member_count = len({c.member.id for c in calcs if c.amount != 0})


# ---- runs


def default_posting_date(db: Session, fund_id: uuid.UUID) -> date:
    current = periods.current(db, fund_id)
    if current is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The fund has no open processing month — open one first")
    today = date.today()
    if periods.month_start(today) == current.period:
        return today
    if current.period < periods.month_start(today):
        return periods.next_month(current.period) - timedelta(days=1)
    return current.period


def create_run(db: Session, maker: User, declaration: BonusDeclaration, *, member_ids: list[uuid.UUID] | None,
               as_at: date | None, posting_date: date | None) -> BonusRun:
    fund = db.get(Fund, declaration.fund_id)
    if declaration.kind == BonusKind.final:
        if declaration.period_end >= date.today():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A final rate is credited after the period has ended — use an interim rate for members leaving now")
        live = db.execute(select(BonusRun.reference).where(
            BonusRun.declaration_id == declaration.id, BonusRun.kind == BonusKind.final,
            BonusRun.status.in_((RS.draft, RS.pending_approval, RS.posted)),
        )).scalar_one_or_none()
        if live:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{live} is already the final run for this declaration — reverse it first to run again")
        member_ids, as_at = None, None
    else:
        if not member_ids:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose the members leaving who get the interim rate")
        as_at = as_at or min(date.today(), declaration.period_end)
        if as_at < declaration.period_start:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Calculate to a date inside the period")
        found = db.execute(select(Member.id).where(Member.fund_id == fund.id, Member.id.in_(member_ids))).scalars().all()
        if len(set(found)) != len(set(member_ids)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Some of those members aren't in this fund")
    posting_date = posting_date or default_posting_date(db, fund.id)
    periods.require_open(db, fund.id, posting_date)
    run = BonusRun(
        declaration_id=declaration.id, fund_id=fund.id, reference=_reference(db, "BR"), kind=declaration.kind, status=RS.draft,
        member_ids=[str(m) for m in dict.fromkeys(member_ids)] if member_ids else None, as_at=as_at, posting_date=posting_date,
        created_by_user_id=maker.id,
    )
    db.add(run)
    db.flush()
    _fill(run, _calculate_run(db, run, declaration))
    audit.record(db, maker.id, "bonus_run", run.id, "previewed",
                 after={"reference": run.reference, "credit": run.total_credit, "debit": run.total_debit}, fund_id=fund.id)
    db.commit()
    db.refresh(run)
    return run


def _require_status(run: BonusRun, *allowed: RS) -> None:
    if run.status not in allowed:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{run.reference} is {run.status.value.replace('_', ' ')}")


def recalculate(db: Session, user: User, run: BonusRun) -> BonusRun:
    _require_status(run, RS.draft)
    _fill(run, _calculate_run(db, run, db.get(BonusDeclaration, run.declaration_id)))
    audit.record(db, user.id, "bonus_run", run.id, "recalculated", fund_id=run.fund_id)
    db.commit()
    db.refresh(run)
    return run


def discard(db: Session, user: User, run: BonusRun) -> BonusRun:
    _require_status(run, RS.draft)
    run.status = RS.discarded
    audit.record(db, user.id, "bonus_run", run.id, "discarded", fund_id=run.fund_id)
    db.commit()
    db.refresh(run)
    return run


def submit_run(db: Session, maker: User, run: BonusRun) -> ApprovalRequest:
    _require_status(run, RS.draft)
    if not any(line.amount for line in run.lines):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to post — every member's bonus is already credited")
    declaration = db.get(BonusDeclaration, run.declaration_id)
    fund = db.get(Fund, run.fund_id)
    run.status = RS.pending_approval
    request = approvals.submit(
        db, maker, "bonus_run", entity_type="bonus_run", entity_id=run.id,
        summary=f"Post {run.kind.value} bonus {run.reference} for {fund.code} ({declaration.reference}, "
                f"{declaration.rate.normalize():f}% a year): {run.member_count} members",
        payload={"reference": run.reference, "declaration": declaration.reference, "rate": f"{declaration.rate.normalize():f}% a year",
                 "period": f"{declaration.period_start:%d %b %Y} – {declaration.period_end:%d %b %Y}",
                 "members": run.member_count, "bonus_credited": f"{run.total_credit:,.2f}", "bonus_reversed": f"{run.total_debit:,.2f}",
                 "posting_date": run.posting_date.isoformat()},
        fund_id=run.fund_id,
    )
    db.commit()
    db.refresh(request)
    return request


def _post_run(db: Session, request: ApprovalRequest, checker: User) -> None:
    run = db.execute(select(BonusRun).where(BonusRun.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one()
    _require_status(run, RS.pending_approval)
    declaration = db.get(BonusDeclaration, run.declaration_id)
    fresh = _calculate_run(db, run, declaration)
    previewed = sorted((str(l.member_id), l.component.value, l.amount) for l in run.lines if l.amount)
    now = sorted((str(c.member.id), c.component.value, c.amount) for c in fresh if c.amount)
    if previewed != now:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Members' balances changed since the preview — reject this, recalculate the run and send it again")
    tag = period_tag(declaration)
    members = {m.id: m for m in _members(db, run)}
    posted_lines = [l for l in run.lines if l.amount]
    postings = [ledger.MemberPosting(
        members[l.member_id], BONUS if l.amount > 0 else BONUS_REVERSAL, l.component, abs(l.amount), reference=run.reference,
        description=f"{run.kind.value.capitalize()} bonus {declaration.rate.normalize():f}% p.a. "
                    f"{declaration.period_start:%d %b %Y} – {l.to_date:%d %b %Y}",
        contribution_month=tag,
    ) for l in posted_lines]
    entry, rows = ledger.post_member_transactions(
        db, run.fund_id, entity_type="bonus_run", entity_id=run.id, entry_date=run.posting_date,
        description=f"{run.kind.value.capitalize()} bonus {run.reference} ({declaration.reference})", postings=postings, user=checker,
    )
    for line, row in zip(posted_lines, rows):
        line.member_transaction_id = row.id
    run.status, run.journal_entry_id, run.posted_at = RS.posted, entry.id, utcnow()
    audit.record(db, checker.id, "bonus_run", run.id, "posted",
                 after={"entry": ledger.entry_ref(entry), "credit": run.total_credit, "debit": run.total_debit}, fund_id=run.fund_id)


def _run_rejected(db: Session, request: ApprovalRequest, checker: User) -> None:
    run = db.get(BonusRun, uuid.UUID(request.entity_id))
    if run is not None and run.status == RS.pending_approval:
        run.status = RS.draft  # back to the maker to recalculate or discard


approvals.register(approvals.ApprovalKind(name="bonus_run", label="Bonus run", checker_roles=CHECKERS, apply=_post_run,
                                          on_reject=_run_rejected))


# ---- reversal (type 5 for credited bonus, type 6 for a true-up that took bonus back)


def _open_lines(run: BonusRun, member_ids: list[uuid.UUID] | None) -> list[BonusRunLine]:
    lines = [l for l in run.lines if l.member_transaction_id and not l.reversal_transaction_id]
    if member_ids:
        wanted = set(member_ids)
        lines = [l for l in lines if l.member_id in wanted]
    return lines


def propose_reversal(db: Session, maker: User, run: BonusRun, *, member_ids: list[uuid.UUID] | None, reason: str) -> ApprovalRequest:
    _require_status(run, RS.posted)
    lines = _open_lines(run, member_ids)
    if not lines:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to reverse — those members' bonus is already reversed")
    whole = not member_ids or len(lines) == len(_open_lines(run, None))
    members = {m.id: m for m in db.execute(select(Member).where(Member.id.in_({l.member_id for l in lines}))).scalars()}
    request = approvals.submit(
        db, maker, "bonus_reversal", entity_type="bonus_run", entity_id=run.id,
        summary=f"Reverse bonus {run.reference}" + ("" if whole else f" for {len(members)} member(s)") + f": {reason}"[:200],
        payload={"reference": run.reference, "scope": "whole run" if whole else "chosen members",
                 "members": sorted(m.account_code for m in members.values()), "reason": reason,
                 "_member_ids": [str(m) for m in member_ids] if member_ids else None},
        fund_id=run.fund_id,
    )
    db.commit()
    db.refresh(request)
    return request


def _apply_reversal(db: Session, request: ApprovalRequest, checker: User) -> None:
    run = db.execute(select(BonusRun).where(BonusRun.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one()
    _require_status(run, RS.posted)
    ids = request.payload.get("_member_ids")
    lines = _open_lines(run, [uuid.UUID(m) for m in ids] if ids else None)
    if not lines:
        raise HTTPException(status.HTTP_409_CONFLICT, "Those members' bonus was reversed in the meantime")
    originals = {t.id: t for t in db.execute(select(MemberTransaction).where(
        MemberTransaction.id.in_([l.member_transaction_id for l in lines]))).scalars()}
    members = {m.id: m for m in db.execute(select(Member).where(Member.id.in_({l.member_id for l in lines}))).scalars()}
    reason = request.payload["reason"]
    postings = []
    for l in lines:
        t = originals[l.member_transaction_id]
        postings.append(ledger.MemberPosting(
            members[l.member_id], BONUS_REVERSAL if t.transaction_code == BONUS else BONUS, t.component, t.amount,
            reference=run.reference, description=f"Reversal: {reason}"[:300], contribution_month=t.contribution_month, reverses=t,
        ))
    entry, rows = ledger.post_member_transactions(
        db, run.fund_id, entity_type="bonus_reversal", entity_id=run.id, entry_date=default_posting_date(db, run.fund_id),
        description=f"Reversal of bonus {run.reference}: {reason}", postings=postings, user=checker,
    )
    for line, row in zip(lines, rows):
        line.reversal_transaction_id = row.id
    if not _open_lines(run, None):
        run.status, run.reversal_entry_id = RS.reversed, entry.id
    audit.record(db, checker.id, "bonus_run", run.id, "reversed",
                 after={"entry": ledger.entry_ref(entry), "lines": len(lines), "reason": reason}, fund_id=run.fund_id)


approvals.register(approvals.ApprovalKind(name="bonus_reversal", label="Bonus reversal", checker_roles=CHECKERS, apply=_apply_reversal))


# ---- queries


def pending_request_id(db: Session, run: BonusRun) -> uuid.UUID | None:
    return db.execute(select(ApprovalRequest.id).where(
        ApprovalRequest.entity_id == str(run.id), ApprovalRequest.kind.in_(("bonus_run", "bonus_reversal")),
        ApprovalRequest.status == ApprovalStatus.pending,
    )).scalar_one_or_none()


def declarations(db: Session, fund_id: uuid.UUID) -> list[BonusDeclaration]:
    return list(db.execute(select(BonusDeclaration).where(BonusDeclaration.fund_id == fund_id)
                           .order_by(BonusDeclaration.period_start.desc(), BonusDeclaration.kind)).scalars())


def runs_for(db: Session, declaration_id: uuid.UUID) -> list[BonusRun]:
    return list(db.execute(select(BonusRun).where(BonusRun.declaration_id == declaration_id, BonusRun.status != RS.discarded)
                           .order_by(BonusRun.created_at.desc())).scalars())


def member_bonus_history(db: Session, member_id: uuid.UUID) -> list[MemberTransaction]:
    return list(db.execute(select(MemberTransaction).where(
        MemberTransaction.member_id == member_id, MemberTransaction.transaction_code.in_(BONUS_CODES),
    ).order_by(MemberTransaction.transaction_date, MemberTransaction.created_at)).scalars())

