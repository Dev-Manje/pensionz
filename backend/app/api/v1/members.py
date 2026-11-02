import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import _name, to_out
from app.core.database import get_db
from app.models.category import BenefitCategory
from app.models.fund import Fund
from app.models.identity import User
from app.models.kyc import Party
from app.models.member import BeneficiaryNomination, Member, MemberAssignment, MemberSalary, MemberStatus, MemberStatusChange
from app.models.scheme import Scheme
from app.schemas.approval import ApprovalOut
from app.schemas.member import (
    AssignmentOut, BeneficiaryOut, DuplicateOut, EmploymentRecordsOut, KycStatusOut, MemberCreateIn, MemberDetailsIn, MemberOut,
    MemberSummaryOut, NominationIn, NominationOut, NominationsOut, SalaryIn, SalaryOut, ServiceIn, ServicePeriodOut, StatusChangeIn,
    StatusChangeOut,
)
from app.services import fund_access
from app.services import member_records as records
from app.services import members as service

router = APIRouter(tags=["members"])

maker = require_roles(*service.MAKERS)
capture_roles = require_roles(*service.MAKERS, *service.CHECKERS)


class MemberPage(BaseModel):
    items: list[MemberSummaryOut]
    total: int


def get_member(db: Session, user: User, member_id: uuid.UUID) -> Member:
    member = db.get(Member, member_id)
    if member is None or not fund_access.can_access(db, user, member.fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return member


@router.get("/members", response_model=MemberPage)
def list_members(
    fund_id: uuid.UUID | None = None, scheme_id: uuid.UUID | None = None, status_filter: MemberStatus | None = Query(None, alias="status"),
    q: str | None = None, group_accounts: bool = False, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db), user: User = Depends(require_staff),
) -> MemberPage:
    """Members in the funds the user administers; search by name, account code, employee number or ID number."""
    query = select(Member, Fund.code, Scheme.code, BenefitCategory.code).join(Fund, Fund.id == Member.fund_id) \
        .outerjoin(Scheme, Scheme.id == Member.scheme_id).outerjoin(BenefitCategory, BenefitCategory.id == Member.category_id)
    allowed = fund_access.fund_ids_for(db, user)
    if allowed is not None:
        query = query.where(Member.fund_id.in_(allowed))
    if fund_id:
        query = query.where(Member.fund_id == fund_id)
    if scheme_id:
        query = query.where(Member.scheme_id == scheme_id)
    if status_filter:
        query = query.where(Member.status == status_filter)
    if group_accounts:
        query = query.where(Member.is_group_account.is_(True))
    if q and q.strip():
        term = f"%{q.strip()}%"
        name = func.concat_ws(" ", Member.first_name, Member.other_names, Member.last_name)
        conditions = [name.ilike(term), func.concat_ws(" ", Member.first_name, Member.last_name).ilike(term),
                      Member.account_code.ilike(term), Member.employee_no.ilike(term), Member.old_member_no.ilike(term)]
        key = service.id_key(q)
        if key:
            conditions.append(Member.id_number_key == key)
        query = query.where(or_(*conditions))
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(query.order_by(Member.last_name, Member.first_name, Member.account_code)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    sensitive = service.sees_sensitive(user)
    items = [MemberSummaryOut(
        id=m.id, fund_id=m.fund_id, fund_code=fund_code, account_code=m.account_code, full_name=m.full_name, employee_no=m.employee_no,
        id_number_masked=m.id_number if sensitive else service.mask(m.id_number), date_of_birth=m.date_of_birth,
        employer_code=scheme_code, category_code=category_code, status=m.status, date_joined_fund=m.date_joined_fund,
        pending_approval_id=service.pending_request_id(db, m.id),
    ) for m, fund_code, scheme_code, category_code in rows]
    return MemberPage(items=items, total=total)


@router.post("/funds/{fund_id}/members", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def create_member(fund_id: uuid.UUID, payload: MemberCreateIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Proposes a new member; a member checker approves it."""
    fund = fund_access.require_fund_access(db, user, fund_id)
    return to_out(db, service.propose_new(db, user, fund, payload), user)


@router.get("/members/duplicates", response_model=list[DuplicateOut])
def duplicates(
    id_number: str | None = None, first_name: str | None = None, last_name: str | None = None, date_of_birth: date | None = None,
    exclude: uuid.UUID | None = None, db: Session = Depends(get_db), _: User = Depends(capture_roles),
) -> list[DuplicateOut]:
    """Possible duplicates across all funds (FR-MEM-011) — shown to staff while capturing."""
    return [DuplicateOut(**d) for d in service.find_duplicates(
        db, id_number=id_number, first_name=first_name, last_name=last_name, date_of_birth=date_of_birth, exclude_id=exclude)]


@router.get("/members/kyc-prefill/{party_id}")
def kyc_prefill(party_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(maker)) -> dict:
    """Member fields filled from an approved individual's KYC answers."""
    party = db.get(Party, party_id)
    if party is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "KYC client not found")
    return service.prefill_from_party(db, party)


def _detail(db: Session, user: User, m: Member) -> MemberOut:
    sensitive = service.sees_sensitive(user)
    fields = service.values_of(m)
    fields.update(account_code=m.account_code, account_type_code=m.account_type_code, scheme_id=str(m.scheme_id) if m.scheme_id else None,
                  category_id=str(m.category_id) if m.category_id else None, full_name=m.full_name,
                  status_effective=m.status_effective, exit_date=m.exit_date, date_of_death=m.date_of_death)
    if not sensitive:
        fields["id_number"] = service.mask(m.id_number)
        fields["bank_account_number"] = service.mask(m.bank_account_number)
    fund = db.get(Fund, m.fund_id)
    changes = db.execute(select(MemberStatusChange).where(MemberStatusChange.member_id == m.id)
                         .order_by(MemberStatusChange.effective_date.desc(), MemberStatusChange.created_at.desc())).scalars()
    assignments = db.execute(select(MemberAssignment).where(MemberAssignment.member_id == m.id)
                             .order_by(MemberAssignment.effective_from.desc())).scalars()
    names = lambda a: service.labels(db, {"scheme_id": a.scheme_id, "category_id": a.category_id})  # noqa: E731
    return MemberOut(
        id=m.id, sensitive=sensitive, fields=fields, labels=service.labels(db, fields),
        fund={"id": fund.id, "code": fund.code, "name": fund.name, "fund_type": fund.fund_type.value},
        company=service.company_info(db, m), kyc=KycStatusOut(**service.kyc_status(db, m.party_id)), status=m.status,
        allowed_transitions=sorted(service.TRANSITIONS[m.status], key=lambda s: list(MemberStatus).index(s)),
        status_history=[StatusChangeOut(id=c.id, from_status=c.from_status, to_status=c.to_status, effective_date=c.effective_date,
                                        reason=c.reason, requested_by=_name(db, c.requested_by_user_id),
                                        approved_by=_name(db, c.approved_by_user_id), created_at=c.created_at) for c in changes],
        assignments=[AssignmentOut(id=a.id, employer=names(a)["scheme_id"], category=names(a)["category_id"],
                                   effective_from=a.effective_from, effective_to=a.effective_to, reason=a.reason, note=a.note)
                     for a in assignments],
        pending_approval_id=service.pending_request_id(db, m.id),
        can_edit=user.has_any_role(*service.MAKERS),
    )


@router.get("/members/{member_id}", response_model=MemberOut)
def get_member_detail(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> MemberOut:
    return _detail(db, user, get_member(db, user, member_id))


@router.put("/members/{member_id}", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def update_member(member_id: uuid.UUID, payload: MemberDetailsIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Proposes a data correction; a member checker approves it."""
    return to_out(db, service.propose_update(db, user, get_member(db, user, member_id), payload), user)


@router.post("/members/{member_id}/status", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def change_status(member_id: uuid.UUID, payload: StatusChangeIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Proposes a status change (FR-MEM-005); a member checker approves it."""
    return to_out(db, service.propose_status(db, user, get_member(db, user, member_id), payload), user)


# ---- beneficiaries, salary and service (FR-MEM-008, 009)


def _beneficiary_out(b, names: dict, sensitive: bool) -> BeneficiaryOut:
    return BeneficiaryOut(
        full_name=b.full_name, relationship=b.relationship_code, relationship_label=names.get(b.relationship_code),
        date_of_birth=b.date_of_birth, is_minor=records.is_minor(b.date_of_birth),
        id_number=b.id_number if sensitive else service.mask(b.id_number),
        phone=b.phone if sensitive else None, email=b.email if sensitive else None, address=b.address if sensitive else None,
        share_pct=b.share_pct, guardian_name=b.guardian_name, guardian_relationship=b.guardian_relationship,
        guardian_relationship_label=names.get(b.guardian_relationship) if b.guardian_relationship else None,
        guardian_phone=b.guardian_phone if sensitive else None,
        guardian_id_number=b.guardian_id_number if sensitive else service.mask(b.guardian_id_number),
    )


@router.get("/members/{member_id}/beneficiaries", response_model=NominationsOut)
def beneficiaries(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> NominationsOut:
    """The current nomination and every earlier version. Contact details only for roles that need them."""
    m = get_member(db, user, member_id)
    names, sensitive = records.relationship_names(db), service.sees_sensitive(user)
    rows = db.execute(select(BeneficiaryNomination).where(BeneficiaryNomination.member_id == m.id)
                      .order_by(BeneficiaryNomination.version.desc())).scalars().all()
    out = [NominationOut(id=n.id, version=n.version, signed_date=n.signed_date, is_current=n.is_current, note=n.note,
                         approved_by=_name(db, n.approved_by_user_id), created_at=n.created_at,
                         beneficiaries=[_beneficiary_out(b, names, sensitive) for b in n.beneficiaries]) for n in rows]
    return NominationsOut(current=next((n for n in out if n.is_current), None), history=[n for n in out if not n.is_current],
                          pending_approval_id=records.pending_id(db, records.KIND_NOMINATION, m.id),
                          can_edit=user.has_any_role(*service.MAKERS) and m.status in records.NOMINATING)


@router.post("/members/{member_id}/beneficiaries", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def nominate(member_id: uuid.UUID, payload: NominationIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Proposes a new nomination that replaces the current one; a member checker approves it."""
    return to_out(db, records.propose_nomination(db, user, get_member(db, user, member_id), payload), user)


def _salary_out(db: Session, s) -> SalaryOut:
    return SalaryOut(id=s.id, effective_from=s.effective_from, basic_salary=s.basic_salary, pensionable_salary=s.pensionable_salary,
                     note=s.note, approved_by=_name(db, s.approved_by_user_id), created_at=s.created_at)


@router.get("/members/{member_id}/employment", response_model=EmploymentRecordsOut)
def employment(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> EmploymentRecordsOut:
    """Salary history (latest first) and service periods with pensionable service to today."""
    m = get_member(db, user, member_id)
    salaries = db.execute(select(MemberSalary).where(MemberSalary.member_id == m.id).order_by(MemberSalary.effective_from.desc())).scalars().all()
    current = records.salary_on(db, m.id, records.today())
    periods = records.service_periods(db, m.id)
    as_of = records.today()
    return EmploymentRecordsOut(
        salaries=[_salary_out(db, s) for s in salaries], current_salary=_salary_out(db, current) if current else None,
        service=[ServicePeriodOut(start_date=p.start_date, end_date=p.end_date, part_time_factor=p.part_time_factor, note=p.note,
                                  years=records.service_years([p], as_of)) for p in periods],
        pensionable_service_years=records.service_years(periods, as_of),
        salary_pending_approval_id=records.pending_id(db, records.KIND_SALARY, m.id),
        service_pending_approval_id=records.pending_id(db, records.KIND_SERVICE, m.id),
        can_edit=user.has_any_role(*service.MAKERS),
    )


@router.post("/members/{member_id}/salaries", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def record_salary(member_id: uuid.UUID, payload: SalaryIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Proposes a salary from a date (same date = correction); a member checker approves it."""
    return to_out(db, records.propose_salary(db, user, get_member(db, user, member_id), payload), user)


@router.put("/members/{member_id}/service", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def set_service(member_id: uuid.UUID, payload: ServiceIn, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Proposes the whole service history as it should be; a member checker approves it."""
    return to_out(db, records.propose_service(db, user, get_member(db, user, member_id), payload), user)
