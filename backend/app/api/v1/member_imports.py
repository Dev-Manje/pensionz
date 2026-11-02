"""Bulk member upload and the printable application form (FR-MEM-006, 007)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, require_staff
from app.api.v1.approvals import _name, to_out
from app.core.database import get_db
from app.models.fund import Fund
from app.models.identity import User
from app.models.member import ImportStatus, MemberImport
from app.models.scheme import Scheme
from app.schemas.approval import ApprovalOut
from app.services import fund_access
from app.services import members as member_service
from app.services.io import member_forms, member_import

router = APIRouter(tags=["members"])

maker = require_roles(*member_service.MAKERS)
capture_roles = require_roles(*member_service.MAKERS, *member_service.CHECKERS)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ImportRowOut(BaseModel):
    row: int
    name: str
    raw: dict
    errors: list[str]
    warnings: list[str]
    member_id: uuid.UUID | None


class ImportSummaryOut(BaseModel):
    id: uuid.UUID
    fund_id: uuid.UUID
    scheme_id: uuid.UUID | None
    employer: str | None
    filename: str
    status: ImportStatus
    total_rows: int
    valid_rows: int
    imported_rows: int
    uploaded_by: str | None
    approval_request_id: uuid.UUID | None
    created_at: datetime


class ImportOut(ImportSummaryOut):
    rows: list[ImportRowOut]
    can_submit: bool


def _scheme(db: Session, user: User, scheme_id: uuid.UUID) -> Scheme:
    scheme = db.get(Scheme, scheme_id)
    if scheme is None or not fund_access.can_access(db, user, scheme.fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employer not found")
    return scheme


def _batch(db: Session, user: User, import_id: uuid.UUID) -> MemberImport:
    batch = db.get(MemberImport, import_id)
    if batch is None or not fund_access.can_access(db, user, batch.fund_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    return batch


def _summary(db: Session, b: MemberImport) -> dict:
    scheme = db.get(Scheme, b.scheme_id) if b.scheme_id else None
    return {"id": b.id, "fund_id": b.fund_id, "scheme_id": b.scheme_id, "employer": f"{scheme.code} — {scheme.name}" if scheme else None,
            "filename": b.filename, "status": b.status, "total_rows": b.total_rows, "valid_rows": b.valid_rows,
            "imported_rows": b.imported_rows, "uploaded_by": _name(db, b.uploaded_by_user_id), "approval_request_id": b.approval_request_id,
            "created_at": b.created_at}


def _out(db: Session, user: User, b: MemberImport) -> ImportOut:
    rows = [ImportRowOut(row=r["row"], name=" ".join(p for p in (r["raw"].get("first_name"), r["raw"].get("last_name")) if p) or "—",
                         raw=r["raw"], errors=r["errors"], warnings=r["warnings"], member_id=r.get("member_id")) for r in b.rows]
    return ImportOut(**_summary(db, b), rows=rows,
                     can_submit=b.status == ImportStatus.validated and b.valid_rows > 0 and b.uploaded_by_user_id == user.id)


@router.get("/members/import-template")
def import_template(scheme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(capture_roles)) -> Response:
    """The Excel template for an employer, with its categories and the allowed codes."""
    scheme = _scheme(db, user, scheme_id)
    content = member_import.template(db, db.get(Fund, scheme.fund_id), scheme)
    return Response(content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="members-{scheme.code}.xlsx"'})


@router.get("/members/application-form")
def application_form(scheme_id: uuid.UUID | None = None, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> Response:
    """Printable new-member application form (blank, or for one employer)."""
    scheme = _scheme(db, user, scheme_id) if scheme_id else None
    name = f"member-application-{scheme.code}.pdf" if scheme else "member-application.pdf"
    return Response(member_forms.application_form(db, scheme), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}"'})


@router.post("/members/imports", response_model=ImportOut, status_code=status.HTTP_201_CREATED)
async def upload(scheme_id: uuid.UUID = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(maker)) -> ImportOut:
    """Reads and checks a filled template; nothing is created until the valid rows are submitted and approved."""
    scheme = _scheme(db, user, scheme_id)
    fund = fund_access.require_fund_access(db, user, scheme.fund_id)
    batch = member_import.upload(db, user, fund, scheme.id, file.filename or "upload.xlsx", await file.read())
    return _out(db, user, batch)


@router.get("/members/imports", response_model=list[ImportSummaryOut])
def list_imports(fund_id: uuid.UUID | None = None, db: Session = Depends(get_db), user: User = Depends(capture_roles)) -> list[ImportSummaryOut]:
    query = select(MemberImport).order_by(MemberImport.created_at.desc()).limit(50)
    allowed = fund_access.fund_ids_for(db, user)
    if allowed is not None:
        query = query.where(MemberImport.fund_id.in_(allowed))
    if fund_id:
        query = query.where(MemberImport.fund_id == fund_id)
    return [ImportSummaryOut(**_summary(db, b)) for b in db.execute(query).scalars()]


@router.get("/members/imports/{import_id}", response_model=ImportOut)
def get_import(import_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(capture_roles)) -> ImportOut:
    return _out(db, user, _batch(db, user, import_id))


@router.get("/members/imports/{import_id}/errors")
def import_errors(import_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(capture_roles)) -> Response:
    """The rows with errors and why, in the template layout, to fix and upload again."""
    batch = _batch(db, user, import_id)
    return Response(member_import.errors_workbook(batch), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="member-upload-errors.xlsx"'})


@router.post("/members/imports/{import_id}/submit", response_model=ApprovalOut, status_code=status.HTTP_202_ACCEPTED)
def submit_import(import_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(maker)) -> ApprovalOut:
    """Sends the valid rows to a member checker."""
    return to_out(db, member_import.submit(db, user, _batch(db, user, import_id)), user)


@router.post("/members/imports/{import_id}/cancel", response_model=ImportSummaryOut)
def cancel_import(import_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(maker)) -> ImportSummaryOut:
    return ImportSummaryOut(**_summary(db, member_import.cancel(db, user, _batch(db, user, import_id))))
