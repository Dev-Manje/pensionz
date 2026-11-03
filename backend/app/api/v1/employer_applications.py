"""Employer onboarding by the principal officer — see services/employer_applications.py.

Portal: /po/employer-applications (principal officer, own applications only).
Staff: /employer-applications (scheme setup, fund-scoped)."""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1 import kyc as kyc_api
from app.api.v1.approvals import to_out
from app.core.database import get_db
from app.models.fund import Fund
from app.models.identity import User, UserRole
from app.models.scheme import EmployerApplication, EmployerApplicationStatus
from app.schemas.approval import ApprovalOut
from app.schemas.employer_application import (
    ApplicationFundOut, EmployerApplicationIn, EmployerApplicationOut, FinalTermsIn, NoteIn,
)
from app.schemas.kyc import ApplicationOut
from app.services import employer_applications as svc

router = APIRouter(tags=["employer onboarding"])

officer_only = require_roles(UserRole.principal_officer)
reviewer = require_roles(*svc.REVIEWERS)
staff_viewers = require_roles(UserRole.scheme_config_maker, UserRole.scheme_config_checker, UserRole.admin, UserRole.auditor,
                              UserRole.compliance, UserRole.relationship_manager)


def _out(db: Session, app: EmployerApplication, *, staff: bool) -> EmployerApplicationOut:
    fund = db.get(Fund, app.fund_id)
    officer = db.get(User, app.officer_user_id)
    k = svc.kyc_application(db, app)
    if staff:
        problems = svc.staff_problems(db, app) if app.status == EmployerApplicationStatus.submitted else []
    else:
        problems = svc.officer_problems(db, app) if app.status in svc.OFFICER_EDITABLE else []
    return EmployerApplicationOut(
        id=app.id, reference=app.reference, status=app.status, fund_id=fund.id, fund_code=fund.code, fund_name=fund.name,
        officer_name=officer.full_name or officer.email, officer_email=officer.email,
        details=app.details, categories=app.categories,
        # The officer sees the final terms once approved.
        final_terms=app.final_terms if staff or app.status == EmployerApplicationStatus.approved else None,
        kyc_application_id=app.kyc_application_id, kyc_reference=k.reference if k else None, kyc_status=k.status.value if k else None,
        scheme_id=app.scheme_id, review_note=app.review_note, submitted_at=app.submitted_at, decided_at=app.decided_at,
        created_at=app.created_at, problems=problems,
        pending_approval_id=svc.pending_request_id(db, app) if staff else None,
        can_edit=not staff and app.status in svc.OFFICER_EDITABLE,
    )


# ---- portal


@router.get("/po/application-funds", response_model=list[ApplicationFundOut])
def application_funds(db: Session = Depends(get_db), user: User = Depends(officer_only)) -> list[ApplicationFundOut]:
    """Funds the officer may apply into with a new employer."""
    return [ApplicationFundOut(id=f.id, code=f.code, name=f.name, fund_type=f.fund_type.value) for f in svc.application_funds(db, user)]


@router.get("/po/employer-applications", response_model=list[EmployerApplicationOut])
def my_applications(db: Session = Depends(get_db), user: User = Depends(officer_only)) -> list[EmployerApplicationOut]:
    return [_out(db, a, staff=False) for a in svc.for_officer(db, user)]


@router.post("/po/employer-applications", response_model=EmployerApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(payload: EmployerApplicationIn, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> EmployerApplicationOut:
    return _out(db, svc.create(db, user, payload), staff=False)


@router.get("/po/employer-applications/{application_id}", response_model=EmployerApplicationOut)
def my_application(application_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> EmployerApplicationOut:
    return _out(db, svc.require_officer_application(db, user, application_id), staff=False)


@router.put("/po/employer-applications/{application_id}", response_model=EmployerApplicationOut)
def save_application(application_id: uuid.UUID, payload: EmployerApplicationIn, db: Session = Depends(get_db),
                     user: User = Depends(officer_only)) -> EmployerApplicationOut:
    return _out(db, svc.save(db, user, svc.require_officer_application(db, user, application_id), payload), staff=False)


@router.post("/po/employer-applications/{application_id}/kyc", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def start_kyc(application_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ApplicationOut:
    """Starts the organisation KYC (corporate) for the application."""
    return kyc_api._out(db, svc.start_kyc(db, user, svc.require_officer_application(db, user, application_id)), user)


@router.post("/po/employer-applications/{application_id}/submit", response_model=EmployerApplicationOut)
def submit_application(application_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> EmployerApplicationOut:
    return _out(db, svc.submit(db, user, svc.require_officer_application(db, user, application_id)), staff=False)


@router.post("/po/employer-applications/{application_id}/withdraw", response_model=EmployerApplicationOut)
def withdraw_application(application_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> EmployerApplicationOut:
    return _out(db, svc.withdraw(db, user, svc.require_officer_application(db, user, application_id)), staff=False)


# ---- staff


@router.get("/employer-applications", response_model=list[EmployerApplicationOut])
def list_applications(status_filter: EmployerApplicationStatus | None = None, db: Session = Depends(get_db),
                      user: User = Depends(staff_viewers)) -> list[EmployerApplicationOut]:
    return [_out(db, a, staff=True) for a in db.execute(svc.staff_query(db, user, status_filter)).scalars()]


@router.get("/employer-applications/{application_id}", response_model=EmployerApplicationOut)
def get_application(application_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(staff_viewers)) -> EmployerApplicationOut:
    return _out(db, svc.require_staff_application(db, user, application_id), staff=True)


@router.get("/employer-applications/{application_id}/suggested-terms")
def suggested_terms(application_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(reviewer)) -> dict:
    """The officer's proposal as a starting point for the final terms."""
    return svc.suggested_terms(db, svc.require_staff_application(db, user, application_id))


@router.post("/employer-applications/{application_id}/return", response_model=EmployerApplicationOut)
def return_application(application_id: uuid.UUID, payload: NoteIn, db: Session = Depends(get_db),
                       user: User = Depends(reviewer)) -> EmployerApplicationOut:
    return _out(db, svc.return_to_officer(db, user, svc.require_staff_application(db, user, application_id), payload.note), staff=True)


@router.post("/employer-applications/{application_id}/reject", response_model=EmployerApplicationOut)
def reject_application(application_id: uuid.UUID, payload: NoteIn, db: Session = Depends(get_db),
                       user: User = Depends(reviewer)) -> EmployerApplicationOut:
    return _out(db, svc.reject(db, user, svc.require_staff_application(db, user, application_id), payload.note), staff=True)


@router.post("/employer-applications/{application_id}/propose", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def propose_terms(application_id: uuid.UUID, payload: FinalTermsIn, db: Session = Depends(get_db),
                  user: User = Depends(reviewer)) -> ApprovalOut:
    """Sends the final terms to a scheme-setup checker; approval creates the employer."""
    return to_out(db, svc.propose(db, user, svc.require_staff_application(db, user, application_id), payload), user)
