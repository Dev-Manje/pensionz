"""Employer (scheme) onboarding by the principal officer (FR-PRT-001, FR-PRT-005,
FR-ONB-101; decided 2026-11-03).

1. The officer applies in the portal into a fund staff gave them
   (`officers.officer_fund_ids`): organisation details, contribution day, the
   members' categories and rates as proposed, and the organisation KYC (the
   ordinary corporate KYC stepper, applicant = the officer).
2. Compliance reviews the KYC as usual (return / re-submit / approve).
3. Scheme setup reviews the application: returns it to the officer with a
   note, rejects it, or sets the final terms — employer code, join date, each
   category's code and full terms (default investment option, vesting …; staff
   may change the proposed rates) — and sends them to a checker
   (approval kind "employer_onboarding"). Only possible once the KYC is approved.
4. A scheme-setup checker approves: the employer is created with the officer
   linked and the KYC client linked, plus its categories. Fees stay staff-set.
"""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.category import BenefitCategory
from app.models.fund import Fund, FundStatus, FundType
from app.models.identity import User, UserRole
from app.models.kyc import ApplicationStatus, ClientType, KycApplication
from app.models.mixins import utcnow
from app.models.scheme import BillingFrequency, EmployerApplication, EmployerApplicationStatus as S, Scheme, SchemeOfficer
from app.schemas.category import TermsIn
from app.schemas.employer_application import EmployerApplicationIn, FinalTermsIn
from app.services import approvals, audit, categories, config_resolver, fund_access, kyc, notifications, officers, schemes

KIND = "employer_onboarding"
REVIEWERS = (UserRole.scheme_config_maker,)
OPEN_FUND_TYPES = (FundType.standalone_dc, FundType.umbrella_dc)
OFFICER_EDITABLE = (S.draft, S.returned)
# Details that become the employer's record (the rest of SchemeIn is set by staff).
DETAIL_FIELDS = (
    "name", "registration_number", "tpin", "address_line1", "address_line2", "address_line3", "phone", "email",
    "contact_name", "contact_email", "contact_phone", "contribution_day", "billing_frequency",
)


def _today() -> date:
    return kyc.today()


def _reference(db: Session) -> str:
    number = db.execute(text("SELECT nextval('employer_application_seq')")).scalar_one()
    return f"EMP-{_today().year}-{number:06d}"


# ---- what the officer may do


def application_funds(db: Session, officer: User) -> list[Fund]:
    ids = officers.officer_fund_ids(db, officer)
    if not ids:
        return []
    return list(db.execute(
        select(Fund).where(Fund.id.in_(ids), Fund.status == FundStatus.active, Fund.fund_type.in_(OPEN_FUND_TYPES)).order_by(Fund.code)
    ).scalars())


def for_officer(db: Session, officer: User) -> list[EmployerApplication]:
    return list(db.execute(
        select(EmployerApplication).where(EmployerApplication.officer_user_id == officer.id)
        .order_by(EmployerApplication.created_at.desc())
    ).scalars())


def require_officer_application(db: Session, officer: User, application_id: uuid.UUID) -> EmployerApplication:
    app = db.get(EmployerApplication, application_id)
    if app is None or app.officer_user_id != officer.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return app


def _require_fund(db: Session, officer: User, fund_id: uuid.UUID) -> Fund:
    fund = next((f for f in application_funds(db, officer) if f.id == fund_id), None)
    if fund is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You can't apply into that fund — ask the administrator to add it for you")
    return fund


def _store(app: EmployerApplication, data: EmployerApplicationIn) -> None:
    app.details = data.details.model_dump(mode="json")
    app.categories = [c.model_dump(mode="json") for c in data.categories]


def create(db: Session, officer: User, data: EmployerApplicationIn) -> EmployerApplication:
    fund = _require_fund(db, officer, data.fund_id)
    app = EmployerApplication(reference=_reference(db), fund_id=fund.id, officer_user_id=officer.id, status=S.draft)
    _store(app, data)
    db.add(app)
    db.flush()
    audit.record(db, officer.id, "employer_application", app.id, "created",
                 after={"reference": app.reference, "fund": fund.code, "name": data.details.name}, fund_id=fund.id)
    db.commit()
    db.refresh(app)
    return app


def save(db: Session, officer: User, app: EmployerApplication, data: EmployerApplicationIn) -> EmployerApplication:
    if app.status not in OFFICER_EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "This application is with the administrator and can't be changed now")
    if data.fund_id != app.fund_id:
        app.fund_id = _require_fund(db, officer, data.fund_id).id
    _store(app, data)
    audit.record(db, officer.id, "employer_application", app.id, "saved", fund_id=app.fund_id)
    db.commit()
    db.refresh(app)
    return app


def kyc_application(db: Session, app: EmployerApplication) -> KycApplication | None:
    return db.get(KycApplication, app.kyc_application_id) if app.kyc_application_id else None


def start_kyc(db: Session, officer: User, app: EmployerApplication) -> KycApplication:
    """The organisation KYC for the application, prefilled from its details."""
    if app.status not in OFFICER_EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "This application is with the administrator and can't be changed now")
    current = kyc_application(db, app)
    if current is not None and current.status != ApplicationStatus.rejected:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{current.reference} is already started — continue that one")
    prefill = {k: v for k, v in {"entity_name": app.details.get("name"), "registration_number": app.details.get("registration_number"),
                                 "tpin": app.details.get("tpin")}.items() if v}
    kyc_app = kyc.create(db, officer, ClientType.corporate, prefill)  # commits
    app.kyc_application_id = kyc_app.id
    audit.record(db, officer.id, "employer_application", app.id, "kyc_started", after={"kyc": kyc_app.reference}, fund_id=app.fund_id)
    db.commit()
    db.refresh(app)
    return kyc_app


def _rate_problems(db: Session, cats: list[dict], on: date) -> list[str]:
    out = []
    ee_min = config_resolver.regulatory(db, "min_employee_contribution_pct", on)
    er_min = config_resolver.regulatory(db, "min_employer_contribution_pct", on)
    low = config_resolver.regulatory(db, "min_retirement_age", on)
    high = config_resolver.regulatory(db, "max_retirement_age", on)
    for c in cats:
        name = c.get("name") or "A category"
        if ee_min is not None and Decimal(str(c["employee_rate"])) < ee_min:
            out.append(f"{name}: the employee rate is below the statutory minimum of {categories._num(ee_min)}%")
        if er_min is not None and Decimal(str(c["employer_rate"])) < er_min:
            out.append(f"{name}: the employer rate is below the statutory minimum of {categories._num(er_min)}%")
        nra = c["normal_retirement_age"]
        if (low is not None and nra < low) or (high is not None and nra > high):
            out.append(f"{name}: normal retirement age must be between {int(low or 0)} and {int(high or 99)}")
    return out


def officer_problems(db: Session, app: EmployerApplication) -> list[str]:
    """What stops the officer sending the application."""
    d = app.details
    out = []
    for key, label in (("contribution_day", "the contribution due day"), ("contact_name", "a contact person"),
                       ("contact_email", "the contact's email"), ("address_line1", "the address"),
                       ("join_date", "the first contribution month")):
        if not d.get(key):
            out.append(f"Give {label}")
    if not app.categories:
        out.append("Add at least one category of members with its contribution rates")
    on = date.fromisoformat(d["join_date"]) if d.get("join_date") else _today()
    out += _rate_problems(db, app.categories, on)
    names = [c["name"].strip().lower() for c in app.categories]
    if len(names) != len(set(names)):
        out.append("Give each category a different name")
    k = kyc_application(db, app)
    if k is None or k.status == ApplicationStatus.rejected:
        out.append("Complete the organisation KYC")
    elif k.status in kyc.EDITABLE:
        out.append(f"Send the organisation KYC ({k.reference}) to compliance")
    return out


def _makers_for(db: Session, fund_id: uuid.UUID) -> list[User]:
    return [u for u in notifications.users_with_roles(db, set(REVIEWERS)) if fund_access.can_access(db, u, fund_id)]


def submit(db: Session, officer: User, app: EmployerApplication) -> EmployerApplication:
    if app.status not in OFFICER_EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This application was already {app.status.value.replace('_', ' ')}")
    problems = officer_problems(db, app)
    if problems:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "; ".join(problems))
    _require_fund(db, officer, app.fund_id)
    app.status, app.submitted_at = S.submitted, utcnow()
    audit.record(db, officer.id, "employer_application", app.id, "submitted", fund_id=app.fund_id)
    fund = db.get(Fund, app.fund_id)
    notifications.notify_officers(
        db, _makers_for(db, app.fund_id), "employer_application.submitted", "New employer application",
        f"{app.reference} — {app.details['name']} applied to join {fund.name} (from {officer.full_name or officer.email}).",
        link=f"/onboarding/applications/{app.id}", entity_type="employer_application", entity_id=app.id)
    db.commit()
    db.refresh(app)
    return app


def withdraw(db: Session, officer: User, app: EmployerApplication) -> EmployerApplication:
    if app.status not in (S.draft, S.returned, S.submitted):
        raise HTTPException(status.HTTP_409_CONFLICT, "This application can't be withdrawn now")
    app.status, app.decided_at = S.withdrawn, utcnow()
    audit.record(db, officer.id, "employer_application", app.id, "withdrawn", fund_id=app.fund_id)
    db.commit()
    db.refresh(app)
    return app


# ---- staff review


def staff_query(db: Session, user: User, status_filter: S | None):
    query = select(EmployerApplication).where(EmployerApplication.status != S.draft)
    funds = fund_access.fund_ids_for(db, user)
    if funds is not None:
        query = query.where(EmployerApplication.fund_id.in_(funds))
    if status_filter is not None:
        query = query.where(EmployerApplication.status == status_filter)
    return query.order_by(EmployerApplication.submitted_at.desc().nulls_last())


def require_staff_application(db: Session, user: User, application_id: uuid.UUID) -> EmployerApplication:
    app = db.get(EmployerApplication, application_id)
    if app is None or app.status == S.draft or not fund_access.can_access(db, user, app.fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return app


def pending_request_id(db: Session, app: EmployerApplication) -> uuid.UUID | None:
    return db.execute(
        select(ApprovalRequest.id).where(ApprovalRequest.kind == KIND, ApprovalRequest.entity_id == str(app.id),
                                         ApprovalRequest.status == ApprovalStatus.pending)
    ).scalar_one_or_none()


def staff_problems(db: Session, app: EmployerApplication) -> list[str]:
    """What stops scheme setup sending the final terms for approval."""
    out = []
    k = kyc_application(db, app)
    if k is None or k.status != ApplicationStatus.approved:
        out.append(f"Compliance hasn't approved the KYC yet ({k.reference if k else 'not started'})")
    fund = db.get(Fund, app.fund_id)
    if fund.status != FundStatus.active:
        out.append("The fund isn't taking new employers")
    return out


def _officer_link(app: EmployerApplication) -> str:
    return f"/po/applications/{app.id}"


def _tell_officer(db: Session, app: EmployerApplication, event: str, title: str, body: str, link: str | None = None) -> None:
    officer = db.get(User, app.officer_user_id)
    notifications.notify_officers(db, [officer], event, title, body, link=link or _officer_link(app),
                                  entity_type="employer_application", entity_id=app.id)


def _require_reviewable(app: EmployerApplication) -> None:
    if app.status != S.submitted:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This application is {app.status.value.replace('_', ' ')}, not waiting for review")


def return_to_officer(db: Session, user: User, app: EmployerApplication, note: str) -> EmployerApplication:
    _require_reviewable(app)
    app.status, app.review_note, app.reviewed_by_user_id = S.returned, note.strip(), user.id
    audit.record(db, user.id, "employer_application", app.id, "returned", after={"note": app.review_note}, fund_id=app.fund_id)
    _tell_officer(db, app, "employer_application.returned", "Your employer application needs changes",
                  f"{app.reference} — {app.details['name']} was sent back: {app.review_note} Please update it and send it again.")
    db.commit()
    db.refresh(app)
    return app


def reject(db: Session, user: User, app: EmployerApplication, note: str) -> EmployerApplication:
    _require_reviewable(app)
    app.status, app.review_note, app.reviewed_by_user_id, app.decided_at = S.rejected, note.strip(), user.id, utcnow()
    audit.record(db, user.id, "employer_application", app.id, "rejected", after={"note": app.review_note}, fund_id=app.fund_id)
    _tell_officer(db, app, "employer_application.rejected", "Your employer application was not accepted",
                  f"{app.reference} — {app.details['name']}: {app.review_note}")
    db.commit()
    db.refresh(app)
    return app


def _final(db: Session, fund: Fund, data: FinalTermsIn) -> list[dict]:
    codes = [c.code for c in data.categories]
    if len(codes) != len(set(codes)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give each category a different code")
    out = []
    for c in data.categories:
        if c.terms.effective_from > data.join_date:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{c.name}: the terms must be in force by the join date")
        out.append({"code": c.code, "name": c.name, "terms": categories.validate_terms(db, fund, c.terms)})
    return out


def propose(db: Session, maker: User, app: EmployerApplication, data: FinalTermsIn) -> ApprovalRequest:
    _require_reviewable(app)
    problems = staff_problems(db, app)
    if problems:
        raise HTTPException(status.HTTP_409_CONFLICT, "; ".join(problems))
    fund = db.get(Fund, app.fund_id)
    schemes._check_code_free(db, fund.id, data.code, None)
    final_categories = _final(db, fund, data)
    app.final_terms = {"code": data.code, "join_date": data.join_date.isoformat(), "categories": final_categories, "note": data.note}
    app.status, app.reviewed_by_user_id = S.in_approval, maker.id
    officer = db.get(User, app.officer_user_id)
    readable_categories = {c["code"]: f"{c['name']} — " + "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in categories.readable(db, c["terms"]).items() if v)
                           for c in final_categories}
    request = approvals.submit(
        db, maker, KIND, entity_type="employer_application", entity_id=app.id,
        summary=f"New employer {data.code} — {app.details['name']} in fund {fund.code} (applied by {officer.full_name or officer.email})",
        payload={"action": "create", "fund_id": str(fund.id), "code": data.code, **{k: app.details.get(k) for k in DETAIL_FIELDS},
                 "join_date": data.join_date.isoformat(), "principal_officer": officer.email,
                 "kyc_application": kyc_application(db, app).reference, "categories": readable_categories,
                 "note_to_officer": data.note},
        fund_id=fund.id,
    )
    audit.record(db, maker.id, "employer_application", app.id, "sent_for_approval", after=app.final_terms, fund_id=fund.id)
    db.commit()
    db.refresh(request)
    return request


def _apply(db: Session, request: ApprovalRequest, checker: User) -> None:
    app = db.execute(select(EmployerApplication).where(EmployerApplication.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one()
    if app.status != S.in_approval or not app.final_terms:
        raise HTTPException(status.HTTP_409_CONFLICT, "This application is no longer waiting for approval")
    fund = db.get(Fund, app.fund_id)
    if fund.status != FundStatus.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "The fund is no longer taking new employers")
    k = kyc_application(db, app)
    if k is None or k.status != ApplicationStatus.approved or k.party_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The organisation KYC isn't approved")
    terms = app.final_terms
    schemes._check_code_free(db, fund.id, terms["code"], None, ignore_request=request.id)
    d = app.details
    scheme = Scheme(
        fund_id=fund.id, code=terms["code"], join_date=date.fromisoformat(terms["join_date"]), party_id=k.party_id,
        **{f: d.get(f) for f in DETAIL_FIELDS if f not in ("billing_frequency",)},
        billing_frequency=BillingFrequency(d.get("billing_frequency") or "monthly"),
    )
    db.add(scheme)
    db.flush()
    scheme.officers.append(SchemeOfficer(user_id=app.officer_user_id))
    k.scheme_id = scheme.id  # the KYC now belongs to the employer: its other officers can see it
    for c in terms["categories"]:
        category = BenefitCategory(scheme_id=scheme.id, fund_id=fund.id, code=c["code"], name=c["name"])
        db.add(category)
        db.flush()
        categories._add_terms(db, category, fund, c["terms"])
        audit.record(db, checker.id, "benefit_category", category.id, "created",
                     after={"code": c["code"], "name": c["name"], "terms": c["terms"], "employer_application": app.reference}, fund_id=fund.id)
    app.status, app.scheme_id, app.decided_at = S.approved, scheme.id, utcnow()
    app.review_note = terms.get("note")
    db.flush()
    db.refresh(scheme)
    audit.record(db, checker.id, "scheme", scheme.id, "created", after={**schemes.snapshot(scheme), "employer_application": app.reference},
                 fund_id=fund.id)
    _tell_officer(db, app, "employer_application.approved", f"{scheme.name} is set up in {fund.name}",
                  f"{app.reference} was approved: {scheme.name} is now employer {scheme.code} in {fund.name}. "
                  "You can add its members and send contribution schedules."
                  + (f" Note from the administrator: {terms['note']}" if terms.get("note") else ""),
                  link=f"/po/schemes/{scheme.id}")


def _on_reject(db: Session, request: ApprovalRequest, checker: User) -> None:
    """The checker sent it back (or the maker withdrew it): scheme setup can change the terms and send again."""
    app = db.get(EmployerApplication, uuid.UUID(request.entity_id))
    if app is not None and app.status == S.in_approval:
        app.status = S.submitted


approvals.register(approvals.ApprovalKind(
    name=KIND, label="Employer onboarding", checker_roles=frozenset({UserRole.scheme_config_checker}), apply=_apply,
    on_reject=_on_reject,
))


def kyc_approved(db: Session, kyc_app: KycApplication) -> None:
    """Called when compliance approves a KYC: tell scheme setup an application is ready for its terms."""
    app = db.execute(select(EmployerApplication).where(EmployerApplication.kyc_application_id == kyc_app.id)).scalar_one_or_none()
    if app is None or app.status != S.submitted:
        return
    notifications.notify_officers(
        db, _makers_for(db, app.fund_id), "employer_application.kyc_approved", "Employer application ready for its terms",
        f"Compliance approved the KYC for {app.reference} — {app.details['name']}. Set the final terms and send them for approval.",
        link=f"/onboarding/applications/{app.id}", entity_type="employer_application", entity_id=app.id)


def suggested_terms(db: Session, app: EmployerApplication) -> dict:
    """A starting point for scheme setup: the officer's proposal with the fund's default option."""
    from app.models.investment import InvestmentOption, InvestmentOptionStatus

    option = db.execute(
        select(InvestmentOption.id).where(InvestmentOption.fund_id == app.fund_id, InvestmentOption.status == InvestmentOptionStatus.active)
        .order_by(InvestmentOption.code).limit(1)
    ).scalar_one_or_none()
    join = app.details.get("join_date") or _today().replace(day=1).isoformat()
    cats = []
    for i, c in enumerate(app.categories, start=1):
        code = "".join(ch for ch in c["name"].upper() if ch.isalnum())[:6] or f"CAT{i}"
        cats.append({"code": code, "name": c["name"], "terms": TermsIn(
            effective_from=date.fromisoformat(join), employee_rate=Decimal(str(c["employee_rate"])),
            employer_rate=Decimal(str(c["employer_rate"])), salary_basis=c.get("salary_basis") or "basic",
            normal_retirement_age=c["normal_retirement_age"], default_investment_option_id=option,
        ).model_dump(mode="json")})
    base = "".join(ch for ch in app.details["name"].upper() if ch.isalnum())[:5] or "EMP"
    return {"code": f"{base}01", "join_date": join, "categories": cats}
