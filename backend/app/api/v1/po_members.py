"""Principal officer portal — members: the employer's member list (HR-level facts only),
new-member applications and the bulk upload, salary changes and exit notices; each is a
request a member checker approves, listed back under Requests (FR-PRT-001, FR-PRT-005)."""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.member_imports import ImportOut, _out as import_out
from app.core.database import get_db
from app.models.fund import Fund
from app.models.identity import User, UserRole
from app.schemas.member import SalaryIn
from app.schemas.portal import (
    ExitNoticeIn, NewMemberIn, PortalCategoryOut, PortalMemberDetailOut, PortalMemberOut, PortalRequestOut,
)
from app.services import portal, portal_members, receipts
from app.services.io import member_forms, member_import

router = APIRouter(prefix="/po", tags=["principal officer portal"])

officer_only = require_roles(UserRole.principal_officer)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/schemes/{scheme_id}/members", response_model=list[PortalMemberOut])
def members(scheme_id: uuid.UUID, q: str | None = None, current_only: bool = True, db: Session = Depends(get_db),
            user: User = Depends(officer_only)) -> list[dict]:
    """The employer's members (current ones unless `current_only=false`) — no balances, ID or bank numbers."""
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    return portal_members.member_list(db, scheme, receipts.today(), q, current_only)


@router.get("/schemes/{scheme_id}/categories", response_model=list[PortalCategoryOut])
def categories(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> list[dict]:
    return portal_members.categories(db, portal.require_officer_scheme(db, user, scheme_id))


@router.get("/members/{member_id}", response_model=PortalMemberDetailOut)
def member(member_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    return portal_members.member_detail(db, portal_members.require_member(db, user, member_id), receipts.today())


@router.post("/schemes/{scheme_id}/members", response_model=PortalRequestOut, status_code=status.HTTP_202_ACCEPTED)
def new_member(scheme_id: uuid.UUID, payload: NewMemberIn, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    """A new-member application; the member is created when a member checker approves it."""
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    data = payload.model_dump(exclude={"basic_salary"})
    request = portal_members.new_member(db, user, scheme, data, payload.basic_salary)
    return portal_members.request_row(db, request)


@router.post("/members/{member_id}/salary", response_model=PortalRequestOut, status_code=status.HTTP_202_ACCEPTED)
def salary(member_id: uuid.UUID, payload: SalaryIn, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    member = portal_members.require_member(db, user, member_id)
    return portal_members.request_row(db, portal_members.salary_change(db, user, member, payload))


@router.post("/members/{member_id}/exit", response_model=PortalRequestOut, status_code=status.HTTP_202_ACCEPTED)
def exit_notice(member_id: uuid.UUID, payload: ExitNoticeIn, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    """The member has left the employer (or died): stops contributions once approved; the claim follows."""
    member = portal_members.require_member(db, user, member_id)
    request = portal_members.exit_notice(db, user, member, last_day=payload.last_day, reason=payload.reason, note=payload.note)
    return portal_members.request_row(db, request)


@router.get("/schemes/{scheme_id}/requests", response_model=list[PortalRequestOut])
def requests(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> list[dict]:
    """Requests made from the portal for this employer in the last year, with their outcome."""
    return portal_members.scheme_requests(db, portal.require_officer_scheme(db, user, scheme_id))


@router.get("/requests/{request_id}", response_model=PortalRequestOut)
def one_request(request_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    return portal_members.request_row(db, portal_members.require_request(db, user, request_id))


# ---- forms and the bulk upload


@router.get("/schemes/{scheme_id}/members/import-template")
def import_template(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> Response:
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    content = member_import.template(db, db.get(Fund, scheme.fund_id), scheme)
    return Response(content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="members-{scheme.code}.xlsx"'})


@router.get("/schemes/{scheme_id}/members/application-form")
def application_form(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> Response:
    """The printable new-member application form for this employer (for the employee to sign)."""
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    return Response(member_forms.application_form(db, scheme), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="member-application-{scheme.code}.pdf"'})


@router.post("/schemes/{scheme_id}/members/imports", response_model=ImportOut, status_code=status.HTTP_201_CREATED)
async def upload(scheme_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ImportOut:
    """Checks a filled template row by row; nothing is created until the valid rows are sent and approved."""
    scheme = portal.require_officer_scheme(db, user, scheme_id)
    batch = member_import.upload(db, user, db.get(Fund, scheme.fund_id), scheme.id, file.filename or "upload.xlsx", await file.read())
    return import_out(db, user, batch)


@router.get("/member-imports/{import_id}", response_model=ImportOut)
def get_import(import_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> ImportOut:
    return import_out(db, user, portal_members.require_import(db, user, import_id))


@router.get("/member-imports/{import_id}/errors")
def import_errors(import_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> Response:
    batch = portal_members.require_import(db, user, import_id)
    return Response(member_import.errors_workbook(batch), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="member-upload-errors.xlsx"'})


@router.post("/member-imports/{import_id}/submit", response_model=PortalRequestOut, status_code=status.HTTP_202_ACCEPTED)
def submit_import(import_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(officer_only)) -> dict:
    """Sends the valid rows to a member checker."""
    batch = portal_members.require_import(db, user, import_id)
    if batch.uploaded_by_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the officer who uploaded the file can send it")
    return portal_members.request_row(db, portal_members.submit_import(db, user, batch))
