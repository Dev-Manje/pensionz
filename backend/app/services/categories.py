"""Benefit categories (FR-CFG-004) through maker-checker (kind "benefit_category").

A proposal is either a new category with its first terms, or a change to an
existing one: rename / close, and/or new terms from a later date. Terms are
checked against the regulatory parameters in force on their effective date
(minimum contribution rates, retirement age band) and against the fund:
DC categories need a default investment option of the fund; DB categories
need an accrual rate and final-salary averaging instead.

The payload carries readable values for the checker and the raw terms under
"_terms" (keys starting with "_" are hidden from the approval diff)."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.category import BenefitCategory, BenefitCategoryTerms, BenefitDesign, CategoryStatus, RateType, SalaryBasis
from app.models.fund import Fund, FundType
from app.models.identity import User, UserRole
from app.models.investment import InvestmentOption, InvestmentOptionStatus
from app.models.scheme import Scheme, SchemeStatus
from app.schemas.category import TermsIn
from app.services import approvals, audit, config_resolver

KIND = "benefit_category"

SALARY_BASIS_LABELS = {
    SalaryBasis.basic: "Basic salary",
    SalaryBasis.basic_plus_allowances: "Basic salary plus fixed allowances",
    SalaryBasis.total_emoluments: "Total emoluments",
}
TERM_FIELDS = (
    "employee_rate_type", "employee_rate", "employer_rate_type", "employer_rate", "salary_basis",
    "normal_retirement_age", "min_entry_age", "max_entry_age", "waiting_period_months", "vesting_scale",
    "default_investment_option_id", "member_choice_allowed", "avc_allowed", "group_life_multiple",
    "accrual_denominator", "final_salary_months",
)


def design_for(fund: Fund) -> BenefitDesign:
    return BenefitDesign.db if fund.fund_type == FundType.defined_benefit else BenefitDesign.dc


def pending_request_id(db: Session, category_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(ApprovalRequest.id).where(
            ApprovalRequest.kind == KIND, ApprovalRequest.entity_id == str(category_id), ApprovalRequest.status == ApprovalStatus.pending,
        )
    ).scalar_one_or_none()


def option_label(db: Session, option_id) -> str | None:
    option = db.get(InvestmentOption, uuid.UUID(str(option_id))) if option_id else None
    return f"{option.code} — {option.name}" if option else None


# ---- readable values for the checker


def _num(value) -> str:
    return f"{Decimal(str(value)).normalize():f}"


def _rate(rate_type, rate) -> str:
    if rate is None:
        return "Balance of cost (set by the actuary)"
    return f"{_num(rate)}% of pensionable salary" if RateType(rate_type) == RateType.percent else f"MWK {Decimal(str(rate)):,.2f} a month"


def readable(db: Session, t: dict) -> dict:
    """Terms (raw, JSON form) → the lines a checker reads."""
    out = {
        "effective_from": t["effective_from"],
        "employee_contribution": _rate(t["employee_rate_type"], t["employee_rate"]),
        "employer_contribution": _rate(t["employer_rate_type"], t.get("employer_rate")),
        "salary_basis": SALARY_BASIS_LABELS[SalaryBasis(t["salary_basis"])],
        "normal_retirement_age": f"{t['normal_retirement_age']} years",
        "entry_ages": f"{t.get('min_entry_age') or 'any'} to {t.get('max_entry_age') or 'any'}",
        "waiting_period": f"{t.get('waiting_period_months') or 0} months",
        "vesting_scale": [f"{s['years']} years' service: {_num(s['vested_pct'])}% vested" for s in t.get("vesting_scale") or []] or None,
        "group_life_cover": f"{_num(t['group_life_multiple'])} × annual salary" if t.get("group_life_multiple") else None,
    }
    if t.get("accrual_denominator"):
        out["db_accrual"] = f"1/{t['accrual_denominator']} of final salary per year of service"
        out["final_salary"] = f"Average of the last {t['final_salary_months']} months"
    else:
        out["default_investment_option"] = option_label(db, t.get("default_investment_option_id"))
        out["member_choice_allowed"] = "Yes" if t.get("member_choice_allowed") else "No"
        out["avc_allowed"] = "Yes" if t.get("avc_allowed") else "No"
    return out


def terms_dict(terms: BenefitCategoryTerms) -> dict:
    return audit._jsonable({"effective_from": terms.effective_from, **{f: getattr(terms, f) for f in TERM_FIELDS}})


# ---- validation


def validate_terms(db: Session, fund: Fund, t: TermsIn) -> dict:
    """Checks the terms for this fund on their effective date; returns them in JSON form."""
    design = design_for(fund)
    on = t.effective_from
    if design == BenefitDesign.dc:
        if t.employer_rate is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Set the employer contribution rate")
        if t.accrual_denominator or t.final_salary_months:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Accrual rate and final salary only apply to defined benefit funds")
        if t.default_investment_option_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose the default investment option for new members")
        option = db.get(InvestmentOption, t.default_investment_option_id)
        if option is None or option.fund_id != fund.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The default investment option must be one of this fund's options")
        if option.status != InvestmentOptionStatus.active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{option.name} is closed to new money — choose an active option")
        for label, key, rate_type, rate in (
            ("employee", "min_employee_contribution_pct", t.employee_rate_type, t.employee_rate),
            ("employer", "min_employer_contribution_pct", t.employer_rate_type, t.employer_rate),
        ):
            minimum = config_resolver.regulatory(db, key, on)
            if minimum is not None and rate_type == RateType.percent and rate < minimum:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    f"The {label} rate can't be below the statutory minimum of {_num(minimum)}% in force on {on.day} {on:%b %Y}")
    else:
        if not t.accrual_denominator or not t.final_salary_months:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A defined benefit category needs its accrual rate and final-salary averaging period")
        if t.default_investment_option_id or t.member_choice_allowed:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Defined benefit members don't choose investment options")
    low, high = (config_resolver.regulatory(db, "min_retirement_age", on), config_resolver.regulatory(db, "max_retirement_age", on))
    if (low is not None and t.normal_retirement_age < low) or (high is not None and t.normal_retirement_age > high):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Normal retirement age must be between {int(low or 0)} and {int(high or 99)} on {on.day} {on:%b %Y}")
    data = t.model_dump(mode="json")
    if design == BenefitDesign.db:
        data["employer_rate_type"] = RateType.percent.value
    return data


def categories_below(db: Session, key: str, value: Decimal, as_of: date) -> list[str]:
    """Categories whose percent rate would fall below a proposed new minimum
    (terms in force on `as_of`, or starting later) — shown to the checker."""
    field = {"min_employee_contribution_pct": ("employee_rate_type", "employee_rate"),
             "min_employer_contribution_pct": ("employer_rate_type", "employer_rate")}.get(key)
    if field is None:
        return []
    found = []
    for category in db.execute(select(BenefitCategory).where(BenefitCategory.status == CategoryStatus.active)).scalars():
        relevant = [t for t in category.terms if t.effective_from >= as_of]
        in_force = next((t for t in category.terms if t.effective_from <= as_of), None)
        for t in [*relevant, *([in_force] if in_force else [])]:
            rate_type, rate = getattr(t, field[0]), getattr(t, field[1])
            if t.design == BenefitDesign.dc and rate_type == RateType.percent and rate is not None and rate < value:
                scheme = db.get(Scheme, category.scheme_id)
                found.append(f"{scheme.code}/{category.code} ({_num(rate)}% from {t.effective_from.day} {t.effective_from:%b %Y})")
                break
    return found


# ---- proposals


def _check_code_free(db: Session, scheme: Scheme, code: str) -> None:
    taken = db.execute(
        select(BenefitCategory.id).where(BenefitCategory.scheme_id == scheme.id, func.upper(BenefitCategory.code) == code.upper())
    ).first()
    waiting = db.execute(
        select(ApprovalRequest.id).where(
            ApprovalRequest.kind == KIND, ApprovalRequest.status == ApprovalStatus.pending,
            ApprovalRequest.payload["_scheme_id"].astext == str(scheme.id), func.upper(ApprovalRequest.payload["code"].astext) == code.upper(),
        )
    ).first()
    if taken is not None or waiting is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Category code {code} is already used for this employer")


def propose_new(db: Session, maker: User, scheme: Scheme, code: str, name: str, t: TermsIn) -> ApprovalRequest:
    fund = db.get(Fund, scheme.fund_id)
    if scheme.status != SchemeStatus.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Categories can only be added to an active employer")
    _check_code_free(db, scheme, code)
    terms = validate_terms(db, fund, t)
    request = approvals.submit(
        db, maker, KIND, entity_type="benefit_category", entity_id=None,
        summary=f"New category {scheme.code}/{code} — {name}, from {t.effective_from.day} {t.effective_from:%b %Y}",
        payload={"action": "create", "code": code, "name": name, **readable(db, terms),
                 "_scheme_id": str(scheme.id), "_terms": terms},
        fund_id=fund.id,
    )
    db.commit()
    db.refresh(request)
    return request


def propose_change(db: Session, maker: User, category: BenefitCategory, name: str, new_status: CategoryStatus, t: TermsIn | None) -> ApprovalRequest:
    fund = db.get(Fund, category.fund_id)
    scheme = db.get(Scheme, category.scheme_id)
    latest = category.terms[0] if category.terms else None
    payload: dict = {"action": "update", "name": name, "status": new_status.value}
    previous: dict = {"name": category.name, "status": category.status.value}
    changed = [k for k in ("name", "status") if payload[k] != previous[k]]
    if t is not None:
        if latest is not None and t.effective_from <= latest.effective_from:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"New terms must start after the latest ones ({latest.effective_from.day} {latest.effective_from:%b %Y})")
        terms = validate_terms(db, fund, t)
        in_force = config_resolver.category_terms(db, category.id, t.effective_from)
        payload.update(readable(db, terms))
        payload["_terms"] = terms
        if in_force is not None:
            previous.update(readable(db, terms_dict(in_force)))
        changed.append("terms")
    if not changed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing has changed")
    when = f" from {t.effective_from.day} {t.effective_from:%b %Y}" if t else ""
    request = approvals.submit(
        db, maker, KIND, entity_type="benefit_category", entity_id=category.id,
        summary=f"Change category {scheme.code}/{category.code}: {', '.join(changed)}{when}",
        payload=payload, previous=previous, fund_id=fund.id,
    )
    db.commit()
    db.refresh(request)
    return request


def _add_terms(db: Session, category: BenefitCategory, fund: Fund, terms: dict) -> BenefitCategoryTerms:
    t = TermsIn.model_validate(terms)
    validate_terms(db, fund, t)  # the regulatory picture may have changed since the request
    row = BenefitCategoryTerms(category_id=category.id, design=design_for(fund), **t.model_dump(exclude={"vesting_scale"}),
                               vesting_scale=[s.model_dump(mode="json") for s in t.vesting_scale])
    db.add(row)
    return row


def _apply(db: Session, request: ApprovalRequest, checker: User) -> None:
    data = request.payload
    fund = db.get(Fund, request.fund_id)
    if data["action"] == "create":
        scheme = db.get(Scheme, uuid.UUID(data["_scheme_id"]))
        if db.execute(select(BenefitCategory.id).where(BenefitCategory.scheme_id == scheme.id,
                                                       func.upper(BenefitCategory.code) == data["code"].upper())).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "That category code was used in the meantime")
        category = BenefitCategory(scheme_id=scheme.id, fund_id=fund.id, code=data["code"], name=data["name"])
        db.add(category)
        db.flush()
        _add_terms(db, category, fund, data["_terms"])
        request.entity_id = str(category.id)
        db.flush()
        audit.record(db, checker.id, "benefit_category", category.id, "created", after={"code": category.code, "name": category.name, "terms": data["_terms"]}, fund_id=fund.id)
        return
    category = db.execute(select(BenefitCategory).where(BenefitCategory.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one_or_none()
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That category no longer exists")
    before = {"name": category.name, "status": category.status.value}
    category.name, category.status = data["name"], CategoryStatus(data["status"])
    if data.get("_terms"):
        latest = max((t.effective_from for t in category.terms), default=None)
        if latest is not None and date.fromisoformat(data["_terms"]["effective_from"]) <= latest:
            raise HTTPException(status.HTTP_409_CONFLICT, "Later terms were added in the meantime — ask again")
        _add_terms(db, category, fund, data["_terms"])
    db.flush()
    audit.record(db, checker.id, "benefit_category", category.id, "updated", before=before,
                 after={"name": category.name, "status": category.status.value, "terms": data.get("_terms")}, fund_id=fund.id)


approvals.register(approvals.ApprovalKind(
    name=KIND, label="Benefit category", checker_roles=frozenset({UserRole.scheme_config_checker}), apply=_apply,
))
