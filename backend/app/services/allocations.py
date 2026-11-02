"""Allocation of contribution schedules to members (FR-CON-005, FR-CON-006).

Rules decided with the user (2026-11-02):
- **Hold until resolved**: a schedule is allocated only when the employer's
  confirmed receipts pay for it exactly — schedule total plus fees the
  employer pays on top. Short money waits for the employer; money over the
  schedule stays unallocated on its receipt (GL 2100) for the next schedule,
  a refund or identification.
- **Fees by payer** (fee rules with basis "% of contributions" in force at the
  end of the contribution month; an employer's own rule replaces the
  fund-wide rule of the same type): payer member → taken out of each member's
  contribution per component; payer employer → on top of the schedule; payer
  fund → not charged here (fee runs). Other bases (% of assets, flat per
  member) are charged by fee runs, not at allocation.

Posting (one entry): for each member and component, Initial Allocation
(type 1: Dr 2100 / Cr 2000) of the net amount; for each fee, Dr 2100 / Cr
its payable account. Σ Dr 2100 = money taken from the receipts.
Maker: contributions officer; checker: contributions checker (kind
"contribution_allocation").
"""
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.contribution import (
    AllocationReceipt, AllocationStatus, ContributionAllocation, ContributionReceipt, ContributionSchedule, ReceiptStatus, ScheduleStatus,
)
from app.models.fee import FeeBasis, FeePayer, FeeType
from app.models.fund import Fund, FundType
from app.models.identity import User, UserRole
from app.models.ledger import Component
from app.models.member import Member
from app.models.mixins import utcnow
from app.models.scheme import Scheme
from app.services import approvals, audit, fee_rules, ledger, notifications, periods, receipts, schedules

KIND = "contribution_allocation"
MAKERS = (UserRole.contributions_officer,)
CHECKERS = frozenset({UserRole.contributions_checker})
ZERO = Decimal("0.00")
INITIAL_ALLOCATION = 1
FEE_GL = {FeeType.administration: "2500", FeeType.risk_premium: "2400", FeeType.investment_management: "2450",
          FeeType.statutory_levy: "2350", FeeType.other: "2500"}
COMPONENTS = {"employee": Component.employee, "employer": Component.employer, "voluntary": Component.voluntary, "severance": Component.severance}


# ---- fee plan


@dataclass
class FeeLine:
    code: str
    name: str
    fee_type: str
    payer: str
    rate: Decimal
    amount: Decimal
    gl_code: str

    def as_dict(self) -> dict:
        return {"code": self.code, "name": self.name, "fee_type": self.fee_type, "payer": self.payer, "rate": str(self.rate),
                "amount": str(self.amount), "gl_code": self.gl_code}


@dataclass
class Plan:
    schedule_total: Decimal
    fees: list[FeeLine]
    # line id → component → amount taken out of that member's contribution
    deductions: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(lambda: ZERO)))

    @property
    def member_fees(self) -> Decimal:
        return sum((f.amount for f in self.fees if f.payer == FeePayer.member.value), ZERO)

    @property
    def employer_fees(self) -> Decimal:
        return sum((f.amount for f in self.fees if f.payer == FeePayer.employer.value), ZERO)

    @property
    def needed(self) -> Decimal:
        return self.schedule_total + self.employer_fees

    @property
    def net_to_members(self) -> Decimal:
        return self.schedule_total - self.member_fees


def plan_for(db: Session, schedule: ContributionSchedule) -> Plan:
    plan = Plan(schedule.total, [])
    as_of = schedules.month_end(schedule.contribution_month)
    for rule in fee_rules.rules_in_force(db, schedule.fund_id, schedule.scheme_id, as_of):
        if rule.basis != FeeBasis.pct_contributions or rule.payer == FeePayer.fund:
            continue
        if rule.payer == FeePayer.member:
            amount = ZERO
            for line in schedule.lines:
                for key in schedules.AMOUNTS:
                    part = ledger.money(getattr(line, key) * rule.rate / 100)
                    if part:
                        plan.deductions[line.id][key] += part
                        amount += part
        else:
            amount = ledger.money(schedule.total * rule.rate / 100)
        if amount:
            plan.fees.append(FeeLine(rule.code, rule.name, rule.fee_type.value, rule.payer.value, rule.rate, amount, FEE_GL[rule.fee_type]))
    for line_id, parts in plan.deductions.items():
        line = next(l for l in schedule.lines if l.id == line_id)
        if any(parts[k] > getattr(line, k) for k in parts):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Fees on row {line.row_no} are more than the contribution — check the fee rules")
    return plan


# ---- receipts


def held(db: Session, receipt_id: uuid.UUID, *, excluding: uuid.UUID | None = None) -> Decimal:
    """Amount of the receipt promised to allocations still waiting for approval."""
    q = select(func.coalesce(func.sum(AllocationReceipt.amount), 0)).join(
        ContributionAllocation, ContributionAllocation.id == AllocationReceipt.allocation_id
    ).where(AllocationReceipt.receipt_id == receipt_id, ContributionAllocation.status == AllocationStatus.pending_approval)
    if excluding is not None:
        q = q.where(ContributionAllocation.id != excluding)
    return Decimal(db.execute(q).scalar())


def available(db: Session, receipt: ContributionReceipt, *, excluding: uuid.UUID | None = None) -> Decimal:
    if receipt.status != ReceiptStatus.confirmed:
        return ZERO
    return receipt.amount - receipt.allocated_amount - held(db, receipt.id, excluding=excluding)


def candidate_receipts(db: Session, schedule: ContributionSchedule) -> list[tuple[ContributionReceipt, Decimal]]:
    """The employer's confirmed receipts with money left, oldest value date first."""
    rows = db.execute(select(ContributionReceipt).where(
        ContributionReceipt.fund_id == schedule.fund_id, ContributionReceipt.scheme_id == schedule.scheme_id,
        ContributionReceipt.status == ReceiptStatus.confirmed, ContributionReceipt.amount > ContributionReceipt.allocated_amount,
    ).order_by(ContributionReceipt.value_date, ContributionReceipt.receipt_number)).scalars().all()
    out = [(r, available(db, r)) for r in rows]
    return [(r, a) for r, a in out if a > 0]


def auto_pick(candidates: list[tuple[ContributionReceipt, Decimal]], needed: Decimal) -> list[tuple[uuid.UUID, Decimal]]:
    picks, left = [], needed
    for r, a in candidates:
        if left <= 0:
            break
        take = min(a, left)
        picks.append((r.id, take))
        left -= take
    return picks


# ---- propose


def _check_schedule(db: Session, schedule: ContributionSchedule) -> Fund:
    fund = db.get(Fund, schedule.fund_id)
    if fund.fund_type == FundType.defined_benefit:
        raise HTTPException(status.HTTP_409_CONFLICT, "Allocating defined-benefit contributions comes with DB administration (later phase)")
    if schedule.status != ScheduleStatus.ready:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a schedule submitted for allocation can be allocated")
    schedules.recheck(db, schedule)
    if schedule.error_count:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{schedule.error_count} line(s) no longer pass the checks (e.g. a member's status changed) — re-open the schedule and fix them")
    return fund


def live_allocation(db: Session, schedule_id: uuid.UUID) -> ContributionAllocation | None:
    return db.execute(select(ContributionAllocation).where(
        ContributionAllocation.schedule_id == schedule_id,
        ContributionAllocation.status.in_((AllocationStatus.pending_approval, AllocationStatus.posted)),
    )).scalar_one_or_none()


def _fmt(d: Decimal) -> str:
    return f"MWK {d:,.2f}"


def propose(db: Session, user: User, schedule: ContributionSchedule, picks: list[tuple[uuid.UUID, Decimal]] | None) -> ApprovalRequest:
    fund = _check_schedule(db, schedule)
    if live_allocation(db, schedule.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This schedule already has an allocation waiting for approval or posted")
    plan = plan_for(db, schedule)
    if picks is None:
        picks = auto_pick(candidate_receipts(db, schedule), plan.needed)
    chosen: list[tuple[ContributionReceipt, Decimal]] = []
    for receipt_id, amount in picks:
        amount = ledger.money(amount)
        r = db.get(ContributionReceipt, receipt_id)
        if r is None or r.fund_id != schedule.fund_id or r.scheme_id != schedule.scheme_id or r.status != ReceiptStatus.confirmed:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use confirmed receipts from this schedule's employer")
        if amount <= 0 or amount > available(db, r):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Receipt {r.receipt_number} has {_fmt(available(db, r))} available")
        chosen.append((r, amount))
    if len({r.id for r, _ in chosen}) != len(chosen):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use each receipt once")
    covered = sum((a for _, a in chosen), ZERO)
    if covered != plan.needed:
        short = plan.needed - covered
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"The schedule needs {_fmt(plan.needed)} but the receipts cover {_fmt(covered)} — "
            + (f"{_fmt(short)} short; hold the schedule until the employer pays the difference" if short > 0
               else f"{_fmt(-short)} too much; take less from the receipts (the rest stays unallocated)"),
        )
    scheme = db.get(Scheme, schedule.scheme_id)
    allocation = ContributionAllocation(
        fund_id=fund.id, scheme_id=scheme.id, schedule_id=schedule.id, status=AllocationStatus.pending_approval,
        schedule_total=plan.schedule_total, member_fees=plan.member_fees, employer_fees=plan.employer_fees, amount=plan.needed,
        net_to_members=plan.net_to_members, fees=[f.as_dict() for f in plan.fees], created_by_user_id=user.id,
    )
    allocation.receipts = [AllocationReceipt(receipt_id=r.id, amount=a) for r, a in chosen]
    db.add(allocation)
    db.flush()
    request = approvals.submit(
        db, user, KIND, entity_type="contribution_allocation", entity_id=allocation.id,
        summary=f"Allocate {schedule.reference} ({_fmt(plan.net_to_members)} to {schedule.line_count} members) for {scheme.code}",
        payload={
            "employer": f"{scheme.code} — {scheme.name}", "schedule": schedule.reference, "month": periods.label(schedule.contribution_month),
            "members": schedule.line_count, "schedule_total": _fmt(plan.schedule_total),
            "fees_from_members": _fmt(plan.member_fees), "fees_from_employer": _fmt(plan.employer_fees),
            "from_receipts": "; ".join(f"{r.receipt_number} {_fmt(a)}" for r, a in chosen),
            "credited_to_members": _fmt(plan.net_to_members),
            "fees": "; ".join(f"{f.name} {f.rate.normalize():f}% ({f.payer}) {_fmt(f.amount)}" for f in plan.fees) or "None",
        },
        fund_id=fund.id,
    )
    allocation.approval_request_id = request.id
    audit.record(db, user.id, "contribution_allocation", allocation.id, "proposed", after={"amount": plan.needed}, fund_id=fund.id)
    db.commit()
    db.refresh(request)
    return request


# ---- approve


def _apply(db: Session, request: ApprovalRequest, checker: User) -> None:
    allocation = db.execute(select(ContributionAllocation).where(ContributionAllocation.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one()
    if allocation.status != AllocationStatus.pending_approval:
        raise HTTPException(status.HTTP_409_CONFLICT, "This allocation is no longer waiting for approval")
    schedule = db.execute(select(ContributionSchedule).where(ContributionSchedule.id == allocation.schedule_id).with_for_update()).scalar_one()
    fund = _check_schedule(db, schedule)
    plan = plan_for(db, schedule)
    if plan.needed != allocation.amount or plan.net_to_members != allocation.net_to_members:
        raise HTTPException(status.HTTP_409_CONFLICT, "The schedule or the fee rules changed since this was sent — reject it and allocate again")
    for part in allocation.receipts:
        r = db.execute(select(ContributionReceipt).where(ContributionReceipt.id == part.receipt_id).with_for_update()).scalar_one()
        if part.amount > available(db, r, excluding=allocation.id):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Receipt {r.receipt_number} no longer has enough money available")
        r.allocated_amount += part.amount
    month_label = periods.label(schedule.contribution_month)
    members = {m.id: m for m in db.execute(select(Member).where(Member.id.in_({l.member_id for l in schedule.lines}))).scalars()}
    postings: list[ledger.MemberPosting] = []
    for line in schedule.lines:
        for key, component in COMPONENTS.items():
            gross = getattr(line, key)
            if gross <= 0:
                continue
            fee = plan.deductions[line.id][key] if line.id in plan.deductions else ZERO
            text = f"Contributions {month_label}" + (f" ({_fmt(gross)} less fees {_fmt(fee)})" if fee else "")
            postings.append(ledger.MemberPosting(members[line.member_id], INITIAL_ALLOCATION, component, gross - fee,
                                                 reference=schedule.reference, description=text, contribution_month=schedule.contribution_month))
    fee_lines = []
    for f in plan.fees:
        fee_lines += [ledger.dr(ledger.UNALLOCATED, f.amount, scheme_id=schedule.scheme_id, description=f.name),
                      ledger.cr(f.gl_code, f.amount, scheme_id=schedule.scheme_id, description=f.name)]
    entry, _ = ledger.post_member_transactions(
        db, fund.id, entity_type="contribution_allocation", entity_id=allocation.id,
        entry_date=receipts.posting_date(db, fund.id, receipts.today()),
        description=f"Initial allocation {schedule.reference} — {month_label}", postings=postings, other_lines=fee_lines, user=checker,
    )
    allocation.status, allocation.journal_entry_id = AllocationStatus.posted, entry.id
    allocation.approved_by_user_id, allocation.posted_at = checker.id, utcnow()
    schedule.status = ScheduleStatus.allocated
    audit.record(db, checker.id, "contribution_allocation", allocation.id, "posted",
                 after={"journal": ledger.entry_ref(entry), "net_to_members": allocation.net_to_members}, fund_id=fund.id)
    scheme = db.get(Scheme, schedule.scheme_id)
    for officer in scheme.officers:
        notifications._notify(db, officer.user, "contributions.allocated", f"{month_label} contributions allocated",
                               f"Schedule {schedule.reference} ({_fmt(schedule.total)}) has been credited to {schedule.line_count} members.",
                               link=f"/po/remittances", entity_type="contribution_schedule", entity_id=schedule.id)


def _on_reject(db: Session, request: ApprovalRequest, user: User) -> None:
    allocation = db.get(ContributionAllocation, uuid.UUID(request.entity_id))
    if allocation is not None and allocation.status == AllocationStatus.pending_approval:
        allocation.status = AllocationStatus.cancelled if user.id == request.initiated_by_user_id else AllocationStatus.rejected


approvals.register(approvals.ApprovalKind(name=KIND, label="Allocate contributions", checker_roles=CHECKERS, apply=_apply, on_reject=_on_reject))


# ---- reversal (FR-CON-007)

REVERSAL_KIND = "allocation_reversal"


def propose_reversal(db: Session, user: User, schedule: ContributionSchedule, reason: str) -> ApprovalRequest:
    """Asks to undo a posted allocation; a contributions checker approves."""
    if not reason or len(reason.strip()) < 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say why the allocation has to be reversed")
    allocation = live_allocation(db, schedule.id)
    if allocation is None or allocation.status != AllocationStatus.posted:
        raise HTTPException(status.HTTP_409_CONFLICT, "This schedule has no posted allocation to reverse")
    _check_balances(db, allocation)
    scheme = db.get(Scheme, schedule.scheme_id)
    request = approvals.submit(
        db, user, REVERSAL_KIND, entity_type="contribution_allocation", entity_id=allocation.id,
        summary=f"Reverse allocation of {schedule.reference} ({_fmt(allocation.net_to_members)}) for {scheme.code}",
        payload={"employer": f"{scheme.code} — {scheme.name}", "schedule": schedule.reference,
                 "month": periods.label(schedule.contribution_month), "members": schedule.line_count,
                 "taken_back_from_members": _fmt(allocation.net_to_members), "returned_to_unallocated": _fmt(allocation.amount),
                 "reason": reason.strip()},
        fund_id=allocation.fund_id,
    )
    audit.record(db, user.id, "contribution_allocation", allocation.id, "reversal_requested", after={"reason": reason.strip()},
                 fund_id=allocation.fund_id)
    db.commit()
    db.refresh(request)
    return request


def _check_balances(db: Session, allocation: ContributionAllocation) -> None:
    """Members must still hold what the allocation credited (nothing paid out since)."""
    from app.models.ledger import MemberTransaction

    credited = db.execute(select(MemberTransaction).where(MemberTransaction.journal_entry_id == allocation.journal_entry_id)).scalars().all()
    for t in credited:
        by_component = ledger.member_balances_by_component(db, t.member_id).get(t.component, {})
        if sum(by_component.values(), ZERO) < t.amount:
            member = db.get(Member, t.member_id)
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"{member.account_code} no longer holds {_fmt(t.amount)} of {t.component.value} money — "
                                "it has been paid out or moved, so this allocation can't be reversed")


def _apply_reversal(db: Session, request: ApprovalRequest, checker: User) -> None:
    from app.models.ledger import JournalEntry

    allocation = db.execute(select(ContributionAllocation).where(ContributionAllocation.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one()
    if allocation.status != AllocationStatus.posted:
        raise HTTPException(status.HTTP_409_CONFLICT, "This allocation isn't posted any more")
    _check_balances(db, allocation)
    schedule = db.execute(select(ContributionSchedule).where(ContributionSchedule.id == allocation.schedule_id).with_for_update()).scalar_one()
    entry = db.get(JournalEntry, allocation.journal_entry_id)
    reversal = ledger.reverse(db, entry, user=checker, entry_date=receipts.posting_date(db, allocation.fund_id, receipts.today()),
                              reason=request.payload["reason"])
    for part in allocation.receipts:
        r = db.execute(select(ContributionReceipt).where(ContributionReceipt.id == part.receipt_id).with_for_update()).scalar_one()
        r.allocated_amount -= part.amount
    allocation.status = AllocationStatus.reversed
    # Back to "ready": re-open it to correct, then allocate again.
    schedule.status = ScheduleStatus.ready
    audit.record(db, checker.id, "contribution_allocation", allocation.id, "reversed",
                 after={"journal": ledger.entry_ref(reversal), "reason": request.payload["reason"]}, fund_id=allocation.fund_id)


approvals.register(approvals.ApprovalKind(
    name=REVERSAL_KIND, label="Reverse contribution allocation", checker_roles=CHECKERS, apply=_apply_reversal,
))
