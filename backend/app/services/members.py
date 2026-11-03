"""Members (FR-MEM-001…005, 011; FR-ONB-105) through maker-checker.

A member administrator proposes; a member checker (who administers the fund)
approves. Three approval kinds:

- `member_new` — a new member (the record, first employer/category row, status active);
- `member_update` — a data correction to the person's details;
- `member_status` — a status transition (see TRANSITIONS), with its effective date and reason.

The payload the checker sees has readable values ("CTE01 — Chitete Estates",
district names…) with the raw values under `_values`, and any possible
duplicates found across all funds (FR-MEM-011)."""
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.category import BenefitCategory, CategoryStatus
from app.models.fund import Fund, FundStatus, FundType
from app.models.identity import User, UserRole
from app.models.kyc import ClientType, DocumentReview, KycApplication, KycDocument, Party
from app.models.member import AssignmentReason, Member, MemberAssignment, MemberSalary, MemberStatus, MemberStatusChange
from app.models.reference import Bank, BankBranch, Country, District, ReferenceItem, ReferenceList, TraditionalAuthority, Village
from app.models.scheme import Scheme, SchemeStatus
from app.schemas.member import MemberCreateIn, MemberDetailsIn, MoveIn, StatusChangeIn
from app.services import approvals, audit, config_resolver, kyc_forms
from app.services.kyc import today

KIND_NEW = "member_new"
KIND_UPDATE = "member_update"
KIND_STATUS = "member_status"
KIND_MOVE = "member_move"
MEMBER_KINDS = (KIND_NEW, KIND_UPDATE, KIND_STATUS, KIND_MOVE)
CHECKERS = frozenset({UserRole.member_checker})
MAKERS = (UserRole.member_admin,)

DETAIL_FIELDS = tuple(MemberDetailsIn.model_fields)
DATE_FIELDS = {"date_of_birth", "date_joined_fund", "date_joined_employer"}
UUID_FIELDS = {f for f in DETAIL_FIELDS if f.endswith("_id")}

# Funds whose members have no participating employer or benefit category.
NO_EMPLOYER_FUNDS = frozenset({FundType.personal_pension, FundType.minors_trust})

# Who sees full ID numbers and bank account numbers; everyone else gets them masked.
SENSITIVE_ROLES = frozenset({
    UserRole.admin, UserRole.member_admin, UserRole.member_checker, UserRole.compliance,
    UserRole.benefits_officer, UserRole.benefits_checker, UserRole.benefits_approver_l2, UserRole.payroll_officer,
})

S = MemberStatus
# Allowed status changes (FR-MEM-005). Exited and deceased are final: a returning
# member is a new membership.
TRANSITIONS: dict[MemberStatus, frozenset[MemberStatus]] = {
    S.active: frozenset({S.inactive, S.deferred, S.pensioner, S.exited, S.deceased}),
    S.inactive: frozenset({S.active, S.deferred, S.pensioner, S.exited, S.deceased}),
    S.deferred: frozenset({S.active, S.pensioner, S.exited, S.deceased}),
    S.pensioner: frozenset({S.exited, S.deceased}),
    S.exited: frozenset(),
    S.deceased: frozenset(),
}
# What each status allows; later phases ask `allows(member.status, "contributions")`.
ACTIVITIES: dict[str, frozenset[MemberStatus]] = {
    "contributions": frozenset({S.active}),
    "benefit_claims": frozenset({S.active, S.inactive, S.deferred, S.deceased}),
    "pension_payroll": frozenset({S.pensioner}),
}
# Statuses that end employment: the exit date is set from the effective date.
LEAVING = frozenset({S.deferred, S.pensioner, S.exited})

STATUS_LABELS = {S.active: "Active", S.inactive: "Inactive", S.deferred: "Deferred (paid-up)", S.pensioner: "Pensioner",
                 S.exited: "Exited", S.deceased: "Deceased"}


def allows(member_status: MemberStatus, activity: str) -> bool:
    return member_status in ACTIVITIES[activity]


def sees_sensitive(user: User) -> bool:
    return user.has_any_role(*SENSITIVE_ROLES)


def mask(value: str | None) -> str | None:
    if not value:
        return value
    return "•••• " + value[-4:] if len(value) > 4 else "••••"


def id_key(value: str | None) -> str | None:
    key = re.sub(r"[\s\-/.]", "", value or "").upper()
    return key or None


def age_on(born: date, on: date) -> int:
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def pending_request_id(db: Session, member_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(ApprovalRequest.id).where(
            ApprovalRequest.kind.in_(MEMBER_KINDS), ApprovalRequest.entity_id == str(member_id),
            ApprovalRequest.status == ApprovalStatus.pending,
        ).limit(1)
    ).scalar_one_or_none()


def has_members(db: Session, fund_id: uuid.UUID) -> bool:
    return db.execute(select(Member.id).where(Member.fund_id == fund_id).limit(1)).first() is not None


# ---- duplicates (FR-MEM-011)


def find_duplicates(db: Session, *, id_number: str | None, first_name: str | None, last_name: str | None,
                    date_of_birth: date | None, exclude_id: uuid.UUID | None = None) -> list[dict]:
    """Members in any fund with the same ID number, or the same name and date of birth."""
    conditions, key = [], id_key(id_number)
    if key:
        conditions.append(Member.id_number_key == key)
    if first_name and last_name and date_of_birth:
        conditions.append((func.lower(Member.first_name) == first_name.strip().lower())
                          & (func.lower(Member.last_name) == last_name.strip().lower())
                          & (Member.date_of_birth == date_of_birth))
    if not conditions:
        return []
    query = select(Member, Fund.code, Scheme.code).join(Fund, Fund.id == Member.fund_id).outerjoin(Scheme, Scheme.id == Member.scheme_id) \
        .where(or_(*conditions)).order_by(Member.account_code).limit(20)
    if exclude_id is not None:
        query = query.where(Member.id != exclude_id)
    out = []
    for m, fund_code, scheme_code in db.execute(query):
        same_id = bool(key) and m.id_number_key == key
        out.append({
            "member_id": m.id, "account_code": m.account_code, "full_name": m.full_name, "date_of_birth": m.date_of_birth,
            "fund_code": fund_code, "employer": scheme_code, "status": m.status,
            "match": "Same ID number" if same_id else "Same name and date of birth",
        })
    return out


def _duplicate_lines(dups: list[dict]) -> list[str]:
    return [f"{d['match']}: {d['account_code']} {d['full_name']} ({d['fund_code']}, {STATUS_LABELS[MemberStatus(d['status'])]})" for d in dups]


# ---- readable values for the checker and the record page


def _name_of(db: Session, model, value) -> str | None:
    if not value:
        return None
    row = db.get(model, uuid.UUID(str(value)))
    return row.name if row else None


def _ref(db: Session, list_key: ReferenceList, code: str | None) -> str | None:
    if not code:
        return None
    name = db.execute(select(ReferenceItem.name).where(ReferenceItem.list_key == list_key, ReferenceItem.code == code)).scalar_one_or_none()
    return name or code


def labels(db: Session, values: dict) -> dict:
    """Display names for every reference in a member's values."""
    def scheme(v):
        s = db.get(Scheme, uuid.UUID(str(v))) if v else None
        return f"{s.code} — {s.name}" if s else None

    def category(v):
        c = db.get(BenefitCategory, uuid.UUID(str(v))) if v else None
        return f"{c.code} — {c.name}" if c else None

    def party(v):
        p = db.get(Party, uuid.UUID(str(v))) if v else None
        return p.name if p else None

    def group(v):
        g = db.get(Member, uuid.UUID(str(v))) if v else None
        return f"{g.account_code} — {g.full_name}" if g else None

    nationality = values.get("nationality")
    country = db.execute(select(Country.name).where(Country.code == nationality)).scalar_one_or_none() if nationality else None
    return {
        "scheme_id": scheme(values.get("scheme_id")),
        "category_id": category(values.get("category_id")),
        "party_id": party(values.get("party_id")),
        "group_account_id": group(values.get("group_account_id")),
        "salutation": _ref(db, ReferenceList.salutation, values.get("salutation")),
        "id_type": _ref(db, ReferenceList.id_type, values.get("id_type")),
        "next_of_kin_relationship": _ref(db, ReferenceList.relationship, values.get("next_of_kin_relationship")),
        "nationality": country or nationality,
        "birth_district_id": _name_of(db, District, values.get("birth_district_id")),
        "postal_district_id": _name_of(db, District, values.get("postal_district_id")),
        "home_district_id": _name_of(db, District, values.get("home_district_id")),
        "home_ta_id": _name_of(db, TraditionalAuthority, values.get("home_ta_id")),
        "home_village_id": _name_of(db, Village, values.get("home_village_id")),
        "bank_id": _name_of(db, Bank, values.get("bank_id")),
        "bank_branch_id": _name_of(db, BankBranch, values.get("bank_branch_id")),
    }


CHOICE_LABELS = {
    "gender": {"female": "Female", "male": "Male"},
    "civil_status_on_entry": {"single": "Single", "married": "Married", "divorced": "Divorced", "widowed": "Widow / widower"},
    "preferred_contact": {"phone": "Phone call", "sms": "SMS", "email": "Email", "post": "Post"},
}
CHOICE_LABELS["civil_status_current"] = CHOICE_LABELS["civil_status_on_entry"]
# The order the checker reads a member in.
READ_ORDER = ("scheme_id", "category_id", "first_name", "other_names", "last_name", "maiden_name", "salutation", "gender",
              "date_of_birth", "id_type", "id_number", "nationality", "date_joined_fund", "date_joined_employer", "employee_no")


def readable(db: Session, values: dict, *, drop_empty: bool) -> dict:
    """The values as the checker should read them: references by name, `_id` dropped from keys."""
    names = labels(db, values)
    out = {}
    ordered = [k for k in READ_ORDER if k in values] + [k for k in values if k not in READ_ORDER]
    for key in ordered:
        value = values[key]
        shown = names.get(key) if key in names and value else value
        if key in CHOICE_LABELS and value:
            shown = CHOICE_LABELS[key].get(value, value)
        elif key in DATE_FIELDS and value:
            shown = date.fromisoformat(str(value)).strftime("%d %b %Y").lstrip("0")
        if key == "regulatory_data":
            shown = "; ".join(f"{k}: {v}" for k, v in (value or {}).items()) or None
        elif isinstance(value, bool):
            shown = "Yes" if value else "No"
        if drop_empty and shown in (None, "", "No"):
            continue
        out[key[:-3] if key.endswith("_id") else key] = shown
    if "scheme" in out:
        out["employer"] = out.pop("scheme")
    if "party" in out:
        out["kyc_client"] = out.pop("party")
    return out


# ---- snapshot / values


def values_of(member: Member) -> dict:
    return audit._jsonable({f: getattr(member, f) for f in DETAIL_FIELDS})


def _from_payload(values: dict) -> dict:
    out = {}
    for f in DETAIL_FIELDS:
        v = values.get(f)
        if f in DATE_FIELDS and v:
            v = date.fromisoformat(v)
        elif f in UUID_FIELDS and v:
            v = uuid.UUID(v)
        elif f == "regulatory_data":
            v = v or {}
        elif f == "is_group_account":
            v = bool(v)
        out[f] = v
    return out


# ---- validation


def _bad(message: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, message)


def _check_employment(db: Session, fund: Fund, scheme_id, category_id, joined: date, born: date, *, new: bool) -> None:
    if fund.fund_type in NO_EMPLOYER_FUNDS:
        if scheme_id or category_id:
            raise _bad("Members of this fund have no employer or benefit category")
        return
    if not scheme_id or not category_id:
        raise _bad("Choose the member's employer and benefit category")
    scheme = db.get(Scheme, scheme_id)
    if scheme is None or scheme.fund_id != fund.id:
        raise _bad("That employer isn't part of this fund")
    if new and scheme.status != SchemeStatus.active:
        raise _bad(f"Employer {scheme.code} isn't active, so it can't take new members")
    category = db.get(BenefitCategory, category_id)
    if category is None or category.scheme_id != scheme.id:
        raise _bad("That benefit category doesn't belong to the employer")
    if new and category.status != CategoryStatus.active:
        raise _bad(f"Category {category.code} is closed to new members")
    terms = config_resolver.category_terms(db, category.id, joined)
    if terms is None:
        raise _bad(f"Category {category.code} has no terms in force on the join date")
    age = age_on(born, joined)
    if new and terms.min_entry_age is not None and age < terms.min_entry_age:
        raise _bad(f"The member is {age} on the join date; category {category.code} accepts members from age {terms.min_entry_age}")
    if new and terms.max_entry_age is not None and age > terms.max_entry_age:
        raise _bad(f"The member is {age} on the join date; category {category.code} accepts members up to age {terms.max_entry_age}")


def _check_details(db: Session, fund: Fund, d: dict, member: Member | None) -> None:
    born, joined = d["date_of_birth"], d["date_joined_fund"]
    if born >= today():
        raise _bad("The date of birth must be in the past")
    if joined < born:
        raise _bad("The member can't join before they were born")
    if joined > today():
        raise _bad("The join date can't be in the future")
    if d.get("date_joined_employer") and d["date_joined_employer"] < born:
        raise _bad("The date joined the employer can't be before the date of birth")
    if fund.fund_type == FundType.minors_trust and age_on(born, joined) >= 18:
        raise _bad("Minors' trust accounts are for beneficiaries under 18")
    if d.get("id_number") and not d.get("id_type"):
        raise _bad("Choose the ID type for the ID number")
    if d.get("bank_account_number") and not d.get("bank_id"):
        raise _bad("Choose the bank for the account number")
    if d.get("bank_branch_id"):
        branch = db.get(BankBranch, d["bank_branch_id"])
        if branch is None or branch.bank_id != d.get("bank_id"):
            raise _bad("The branch doesn't belong to that bank")
    if d.get("home_ta_id"):
        ta = db.get(TraditionalAuthority, d["home_ta_id"])
        if ta is None or ta.district_id != d.get("home_district_id"):
            raise _bad("The traditional authority isn't in the home district")
    if d.get("home_village_id"):
        village = db.get(Village, d["home_village_id"])
        if village is None or village.traditional_authority_id != d.get("home_ta_id"):
            raise _bad("The village isn't under that traditional authority")
    if d.get("group_account_id"):
        if d.get("is_group_account"):
            raise _bad("A group account can't itself belong to another group account")
        group = db.get(Member, d["group_account_id"])
        if group is None or group.fund_id != fund.id or not group.is_group_account or (member and group.id == member.id):
            raise _bad("The linked group account must be a group account in the same fund")

    party_id = d.get("party_id")
    if fund.fund_type == FundType.personal_pension and not party_id:
        raise _bad("Personal pension holders need an approved KYC client — link one first")
    if party_id:
        party = db.get(Party, party_id)
        if party is None or party.client_type != ClientType.individual:
            raise _bad("Link an approved individual KYC client")
        clash = db.execute(select(Member.account_code).where(
            Member.fund_id == fund.id, Member.party_id == party_id, Member.id != (member.id if member else uuid.uuid4()))).first()
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, f"That KYC client is already member {clash[0]} in this fund")

    key = id_key(d.get("id_number"))
    if key:
        clash = db.execute(select(Member.account_code).where(
            Member.fund_id == fund.id, Member.id_number_key == key, Member.id != (member.id if member else uuid.uuid4()))).first()
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Member {clash[0]} in this fund already has that ID number")


def _pending_new(db: Session, fund_id: uuid.UUID, ignore: uuid.UUID | None = None) -> list[ApprovalRequest]:
    rows = db.execute(select(ApprovalRequest).where(
        ApprovalRequest.kind == KIND_NEW, ApprovalRequest.status == ApprovalStatus.pending, ApprovalRequest.fund_id == fund_id,
    )).scalars().all()
    return [r for r in rows if r.id != ignore]


def _check_against_pending(db: Session, fund: Fund, d: dict, account_code: str | None, ignore: uuid.UUID | None = None) -> None:
    key = id_key(d.get("id_number"))
    for request in _pending_new(db, fund.id, ignore):
        raw = request.payload.get("_values", {})
        if key and id_key(raw.get("id_number")) == key:
            raise HTTPException(status.HTTP_409_CONFLICT, "A new member with that ID number is already waiting for approval in this fund")
        if account_code and (request.payload.get("_account_code") or "").upper() == account_code:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Account code {account_code} is already used by a member waiting for approval")


def _check_account_code(db: Session, fund: Fund, code: str) -> None:
    if db.execute(select(Member.id).where(Member.fund_id == fund.id, func.upper(Member.account_code) == code)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Account code {code} is already used in this fund")


# ---- proposals


def propose_new(db: Session, maker: User, fund: Fund, data: MemberCreateIn, *, first_salary: Decimal | None = None) -> ApprovalRequest:
    """`first_salary` (basic = pensionable, from the employer join date) is recorded with the member on approval."""
    if fund.status != FundStatus.active:
        raise _bad("This fund isn't taking new members (it is closed to new members or wound up)")
    d = {k: v for k, v in data.model_dump().items() if k in DETAIL_FIELDS}
    _check_details(db, fund, d, None)
    _check_employment(db, fund, data.scheme_id, data.category_id, data.date_joined_fund, data.date_of_birth, new=True)
    if data.account_code:
        _check_account_code(db, fund, data.account_code)
    _check_against_pending(db, fund, d, data.account_code)
    dups = find_duplicates(db, id_number=data.id_number, first_name=data.first_name, last_name=data.last_name, date_of_birth=data.date_of_birth)
    values = audit._jsonable({**d, "scheme_id": data.scheme_id, "category_id": data.category_id})
    payload = {
        "action": "create", "fund_id": str(fund.id), "fund": fund.code,
        **readable(db, values, drop_empty=True),
        "account_code": data.account_code or "Generated on approval",
        "possible_duplicates": _duplicate_lines(dups) or None,
        "_values": values, "_account_code": data.account_code,
    }
    if first_salary is not None:
        if first_salary <= 0:
            raise _bad("The salary must be more than zero")
        payload["first_salary"] = f"MWK {first_salary:,.2f}"
        payload["_first_salary"] = str(first_salary)
    request = approvals.submit(
        db, maker, KIND_NEW, entity_type="member", entity_id=None,
        summary=f"New member {data.first_name} {data.last_name} in fund {fund.code}" + (" — possible duplicate" if dups else ""),
        payload=payload, fund_id=fund.id,
    )
    db.commit()
    db.refresh(request)
    return request


def propose_update(db: Session, maker: User, member: Member, data: MemberDetailsIn) -> ApprovalRequest:
    fund = db.get(Fund, member.fund_id)
    current = values_of(member)
    proposed = audit._jsonable(data.model_dump())
    changed = [k for k in DETAIL_FIELDS if proposed.get(k) != current.get(k)]
    if not changed:
        raise _bad("Nothing has changed")
    _check_details(db, fund, data.model_dump(), member)
    dups = []
    if {"id_number", "first_name", "last_name", "date_of_birth"} & set(changed):
        dups = find_duplicates(db, id_number=data.id_number, first_name=data.first_name, last_name=data.last_name,
                               date_of_birth=data.date_of_birth, exclude_id=member.id)
    request = approvals.submit(
        db, maker, KIND_UPDATE, entity_type="member", entity_id=member.id,
        summary=f"Correct member {member.account_code}: {', '.join(k.replace('_id', '').replace('_', ' ') for k in changed)}"[:300],
        payload={"action": "update", **readable(db, proposed, drop_empty=False),
                 "possible_duplicates": _duplicate_lines(dups) or None, "_values": proposed},
        previous={**readable(db, current, drop_empty=False), "possible_duplicates": None},
        fund_id=member.fund_id,
    )
    db.commit()
    db.refresh(request)
    return request


def _check_transition(member: Member, data: StatusChangeIn) -> None:
    if data.to_status == member.status:
        raise _bad(f"The member is already {STATUS_LABELS[member.status].lower()}")
    if data.to_status not in TRANSITIONS[member.status]:
        raise _bad(f"A member who is {STATUS_LABELS[member.status].lower()} can't become {STATUS_LABELS[data.to_status].lower()}")
    if data.effective_date > today():
        raise _bad("The effective date can't be in the future")
    if data.effective_date < member.date_joined_fund:
        raise _bad("The effective date can't be before the member joined the fund")
    if member.status_effective and data.effective_date < member.status_effective:
        raise _bad("The effective date can't be before the current status took effect")


def propose_status(db: Session, maker: User, member: Member, data: StatusChangeIn) -> ApprovalRequest:
    _check_transition(member, data)
    request = approvals.submit(
        db, maker, KIND_STATUS, entity_type="member", entity_id=member.id,
        summary=f"Member {member.account_code} {member.full_name}: {STATUS_LABELS[member.status]} → {STATUS_LABELS[data.to_status]}",
        payload={"action": "status", "status": STATUS_LABELS[data.to_status], "effective_date": data.effective_date,
                 "reason": data.reason, "_to_status": data.to_status.value, "_from_status": member.status.value},
        previous={"status": STATUS_LABELS[member.status], "effective_date": member.status_effective, "reason": None},
        fund_id=member.fund_id,
    )
    db.commit()
    db.refresh(request)
    return request


def current_assignment(db: Session, member_id: uuid.UUID) -> MemberAssignment | None:
    return db.execute(select(MemberAssignment).where(MemberAssignment.member_id == member_id, MemberAssignment.effective_to.is_(None))
                      .order_by(MemberAssignment.effective_from.desc()).limit(1)).scalar_one_or_none()


MOVABLE = frozenset({MemberStatus.active, MemberStatus.inactive})


def _check_move(db: Session, member: Member, data: MoveIn) -> AssignmentReason:
    fund = db.get(Fund, member.fund_id)
    if fund.fund_type in NO_EMPLOYER_FUNDS:
        raise _bad("Members of this fund have no employer or category to move between")
    if member.status not in MOVABLE:
        raise _bad(f"Only active or inactive members can move (this member is {STATUS_LABELS[member.status].lower()})")
    if data.scheme_id == member.scheme_id and data.category_id == member.category_id:
        raise _bad("The member is already in that employer and category")
    transfer = data.scheme_id != member.scheme_id
    if transfer and fund.fund_type != FundType.umbrella_dc:
        raise _bad("Members move between employers only within an umbrella fund")
    if data.effective_date > today():
        raise _bad("The move can't take effect in the future")
    current = current_assignment(db, member.id)
    start = current.effective_from if current else member.date_joined_fund
    if data.effective_date <= start:
        raise _bad(f"The move must take effect after {start:%d %b %Y}, when the current employer and category started")
    _check_employment(db, fund, data.scheme_id, data.category_id, data.effective_date, member.date_of_birth, new=False)
    scheme, category = db.get(Scheme, data.scheme_id), db.get(BenefitCategory, data.category_id)
    if scheme.status != SchemeStatus.active:
        raise _bad(f"Employer {scheme.code} isn't active")
    if category.status != CategoryStatus.active:
        raise _bad(f"Category {category.code} is closed")
    return AssignmentReason.employer_transfer if transfer else AssignmentReason.category_move


def propose_move(db: Session, maker: User, member: Member, data: MoveIn) -> ApprovalRequest:
    reason = _check_move(db, member, data)
    names = labels(db, {"scheme_id": data.scheme_id, "category_id": data.category_id})
    now = labels(db, {"scheme_id": member.scheme_id, "category_id": member.category_id})
    word = "Transfer" if reason == AssignmentReason.employer_transfer else "Category move"
    request = approvals.submit(
        db, maker, KIND_MOVE, entity_type="member", entity_id=member.id,
        summary=f"{word} for {member.account_code} {member.full_name} to {names['scheme_id'].split(' — ')[0]} / {names['category_id'].split(' — ')[0]}",
        payload={"action": reason.value, "employer": names["scheme_id"], "category": names["category_id"],
                 "effective_date": data.effective_date.strftime("%d %b %Y").lstrip("0"),
                 "employee_no": data.employee_no or member.employee_no, "reason": data.reason,
                 "_values": audit._jsonable(data.model_dump())},
        previous={"employer": now["scheme_id"], "category": now["category_id"], "effective_date": None,
                  "employee_no": member.employee_no, "reason": None},
        fund_id=member.fund_id,
    )
    db.commit()
    db.refresh(request)
    return request


# ---- apply on approval


def _next_account_code(db: Session, fund: Fund) -> str:
    while True:
        n = db.execute(select(func.nextval("member_number_seq"))).scalar_one()
        code = f"{fund.code}{n:06d}"
        if not db.execute(select(Member.id).where(Member.fund_id == fund.id, Member.account_code == code)).first():
            return code


def _apply_new(db: Session, request: ApprovalRequest, checker: User) -> None:
    fund = db.get(Fund, uuid.UUID(request.payload["fund_id"]))
    if fund is None or fund.status != FundStatus.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "The fund is no longer taking new members")
    raw = request.payload["_values"]
    d = _from_payload(raw)
    scheme_id = uuid.UUID(raw["scheme_id"]) if raw.get("scheme_id") else None
    category_id = uuid.UUID(raw["category_id"]) if raw.get("category_id") else None
    _check_details(db, fund, d, None)
    _check_employment(db, fund, scheme_id, category_id, d["date_joined_fund"], d["date_of_birth"], new=True)
    member = create_member(db, fund, d, scheme_id, category_id, request.payload.get("_account_code"), checker, request)
    request.entity_id = str(member.id)
    if request.payload.get("_first_salary"):
        amount = Decimal(request.payload["_first_salary"])
        db.add(MemberSalary(member_id=member.id, effective_from=d.get("date_joined_employer") or d["date_joined_fund"], basic_salary=amount,
                            pensionable_salary=amount, note="Given with the application", approved_by_user_id=checker.id,
                            approval_request_id=request.id))


def create_member(db: Session, fund: Fund, d: dict, scheme_id, category_id, code: str | None, checker: User,
                  request: ApprovalRequest, *, joined_reason: str = "Joined the fund") -> Member:
    """Creates an approved member with its first employer/category row and status. Checks must already have passed."""
    if code:
        _check_account_code(db, fund, code)
    else:
        code = _next_account_code(db, fund)
    member = Member(fund_id=fund.id, scheme_id=scheme_id, category_id=category_id, account_code=code, status=MemberStatus.active,
                    status_effective=d["date_joined_fund"], id_number_key=id_key(d.get("id_number")), **d)
    db.add(member)
    db.flush()
    db.add(MemberAssignment(member_id=member.id, scheme_id=scheme_id, category_id=category_id, effective_from=d["date_joined_fund"],
                            reason=AssignmentReason.joined, approved_by_user_id=checker.id))
    db.add(MemberStatusChange(member_id=member.id, from_status=None, to_status=MemberStatus.active, effective_date=d["date_joined_fund"],
                              reason=joined_reason, requested_by_user_id=request.initiated_by_user_id, approved_by_user_id=checker.id,
                              approval_request_id=request.id))
    audit.record(db, checker.id, "member", member.id, "created", after={**values_of(member), "account_code": code}, fund_id=fund.id)
    return member


def _lock(db: Session, request: ApprovalRequest) -> Member:
    member = db.execute(select(Member).where(Member.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That member no longer exists")
    return member


def _apply_update(db: Session, request: ApprovalRequest, checker: User) -> None:
    member = _lock(db, request)
    fund = db.get(Fund, member.fund_id)
    before = values_of(member)
    d = _from_payload(request.payload["_values"])
    _check_details(db, fund, d, member)
    for field, value in d.items():
        setattr(member, field, value)
    member.id_number_key = id_key(member.id_number)
    db.flush()
    audit.record(db, checker.id, "member", member.id, "updated", before=before, after=values_of(member), fund_id=member.fund_id)


def _apply_status(db: Session, request: ApprovalRequest, checker: User) -> None:
    member = _lock(db, request)
    data = request.payload
    if member.status.value != data["_from_status"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "The member's status has changed since this was requested")
    change = StatusChangeIn(to_status=data["_to_status"], effective_date=data["effective_date"], reason=data["reason"])
    _check_transition(member, change)
    before = {"status": member.status.value, "exit_date": member.exit_date, "date_of_death": member.date_of_death}
    db.add(MemberStatusChange(member_id=member.id, from_status=member.status, to_status=change.to_status,
                              effective_date=change.effective_date, reason=change.reason,
                              requested_by_user_id=request.initiated_by_user_id, approved_by_user_id=checker.id,
                              approval_request_id=request.id))
    member.status, member.status_effective = change.to_status, change.effective_date
    if change.to_status in LEAVING and member.exit_date is None:
        member.exit_date = change.effective_date
    if change.to_status == MemberStatus.deceased:
        member.date_of_death = change.effective_date
    if change.to_status in (MemberStatus.active, MemberStatus.inactive):
        member.exit_date = None
    db.flush()
    audit.record(db, checker.id, "member", member.id, "status_changed", before=audit._jsonable(before),
                 after=audit._jsonable({"status": member.status.value, "exit_date": member.exit_date, "date_of_death": member.date_of_death,
                                        "reason": change.reason}), fund_id=member.fund_id)


def _apply_move(db: Session, request: ApprovalRequest, checker: User) -> None:
    member = _lock(db, request)
    data = MoveIn(**request.payload["_values"])
    reason = _check_move(db, member, data)
    before = {"scheme_id": member.scheme_id, "category_id": member.category_id, "employee_no": member.employee_no}
    current = current_assignment(db, member.id)
    if current is not None:
        current.effective_to = data.effective_date - timedelta(days=1)
    db.add(MemberAssignment(member_id=member.id, scheme_id=data.scheme_id, category_id=data.category_id, effective_from=data.effective_date,
                            reason=reason, note=data.reason, approved_by_user_id=checker.id))
    member.scheme_id, member.category_id = data.scheme_id, data.category_id
    if reason == AssignmentReason.employer_transfer:
        member.date_joined_employer = data.effective_date
    if data.employee_no:
        member.employee_no = data.employee_no
    db.flush()
    audit.record(db, checker.id, "member", member.id, reason.value, before=audit._jsonable(before),
                 after=audit._jsonable({**data.model_dump()}), fund_id=member.fund_id)


for _kind, _label, _apply in ((KIND_NEW, "New member", _apply_new), (KIND_UPDATE, "Member data correction", _apply_update),
                              (KIND_STATUS, "Member status change", _apply_status), (KIND_MOVE, "Member move / transfer", _apply_move)):
    approvals.register(approvals.ApprovalKind(name=_kind, label=_label, checker_roles=CHECKERS, apply=_apply))


# ---- KYC link (FR-ONB-105)


def _latest_application(db: Session, party: Party) -> KycApplication | None:
    return db.get(KycApplication, party.latest_application_id) if party.latest_application_id else None


def kyc_status(db: Session, party_id: uuid.UUID | None, *, as_of: date | None = None) -> dict:
    """KYC standing of a member or employer, and whether it blocks benefit payments."""
    as_of = as_of or today()
    party = db.get(Party, party_id) if party_id else None
    if party is None:
        return {"state": "none", "label": "No KYC on file", "payment_block": "There is no approved KYC on file — complete KYC before paying a benefit"}
    app = _latest_application(db, party)
    base = {"party_id": party.id, "party_name": party.name, "risk_rating": party.risk_rating.value, "review_due": party.kyc_review_due,
            "application_id": app.id if app else None, "application_reference": app.reference if app else None}
    if party.kyc_review_due < as_of:
        return {**base, "state": "review_overdue", "label": "KYC review overdue",
                "payment_block": f"The KYC review was due on {party.kyc_review_due:%d %b %Y} — refresh KYC before paying a benefit"}
    if app is not None:
        expired = db.execute(select(KycDocument).where(
            KycDocument.application_id == app.id, KycDocument.superseded.is_(False),
            KycDocument.review_status == DocumentReview.accepted, KycDocument.expiry_date < as_of,
        ).limit(1)).scalar_one_or_none()
        if expired is not None:
            return {**base, "state": "document_expired", "label": "KYC document expired",
                    "payment_block": f"A KYC document expired on {expired.expiry_date:%d %b %Y} — collect a current one before paying a benefit"}
    return {**base, "state": "current", "label": "KYC current", "payment_block": None}


def payment_block(db: Session, member: Member, as_of: date | None = None) -> str | None:
    """Why a benefit can't be paid to this member yet (None = KYC allows it). Phases 8/9 call this."""
    return kyc_status(db, member.party_id, as_of=as_of)["payment_block"]


def prefill_from_party(db: Session, party: Party) -> dict:
    """Member fields from an approved individual's KYC answers."""
    if party.client_type != ClientType.individual:
        raise _bad("Only an individual KYC client can become a member")
    app = _latest_application(db, party)
    k = app.data if app else {}
    kin = k.get("next_of_kin") or {}
    other = " ".join(p for p in (k.get("middle_name"), k.get("other_names")) if p) or None
    return {
        "party_id": str(party.id), "salutation": k.get("salutation"), "first_name": k.get("first_name"), "other_names": other,
        "maiden_name": k.get("maiden_name"), "last_name": k.get("last_name"), "gender": k.get("gender"),
        "date_of_birth": k.get("date_of_birth"), "nationality": k.get("nationality"), "id_type": k.get("id_type"),
        "id_number": k.get("id_number"), "civil_status_current": k.get("marital_status"),
        "civil_status_on_entry": k.get("marital_status_on_entry") or k.get("marital_status"),
        "physical_address": k.get("physical_address"), "postal_address": k.get("postal_address"),
        "home_district_id": k.get("home_district_id"), "home_ta_id": k.get("home_ta_id"), "home_village_id": k.get("home_village_id"),
        "birth_district_id": k.get("birth_district_id"), "birth_village": k.get("birth_village"),
        "telephone": k.get("telephone"), "mobile": k.get("mobile"), "email": k.get("email"),
        "preferred_contact": k.get("preferred_contact"),
        "next_of_kin_name": kin.get("name"), "next_of_kin_relationship": kin.get("relationship"),
        "next_of_kin_phone": kin.get("cell"), "next_of_kin_email": kin.get("email"),
    }


def company_info(db: Session, member: Member) -> dict:
    """FR-MEM-003: the employer the member belongs to (owner name, corporate form, TPIN) and the fund."""
    fund = db.get(Fund, member.fund_id)
    scheme = db.get(Scheme, member.scheme_id) if member.scheme_id else None
    info = {"fund_name": fund.name, "fund_code": fund.code, "owner_name": None, "employer_code": None, "corporate_form": None,
            "tpin": None, "registration_number": None, "employer_kyc": None}
    if scheme is None:
        return info
    info.update(owner_name=scheme.name, employer_code=scheme.code, tpin=scheme.tpin, registration_number=scheme.registration_number,
                employer_kyc=kyc_status(db, scheme.party_id)["label"])
    party = db.get(Party, scheme.party_id) if scheme.party_id else None
    app = _latest_application(db, party) if party else None
    if app is not None:
        form = app.data.get("entity_form")
        names = dict(kyc_forms.ENTITY_FORMS)
        info["corporate_form"] = app.data.get("entity_form_other") if form == "other" else names.get(form, form)
    return info
