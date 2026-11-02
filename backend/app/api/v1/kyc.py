import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user
from app.api.v1.approvals import _name
from app.core.database import get_db
from app.models.identity import User, UserRole
from app.models.kyc import ApplicationStatus, ClientType, KycApplication, KycDocument, Party
from app.schemas.kyc import (
    ApplicationCreate, ApplicationOut, ApplicationSave, ApplicationSummary, ApproveIn, DeclarationOut, DocTypeOut, DocumentOut, ExpiringOut,
    DocumentReviewIn, NoteIn, PartyRef, SeniorDecisionIn, SlotOut, SubmitIn,
)
from app.services import kyc, kyc_expiry, kyc_forms

# Setup staff who link employers and members to approved clients.
PARTY_PICKERS = (UserRole.scheme_config_maker, UserRole.scheme_config_checker, UserRole.member_admin, UserRole.member_checker)

router = APIRouter(prefix="/kyc", tags=["kyc"])


def _doc_out(db: Session, d: KycDocument, labels: dict[str, str]) -> DocumentOut:
    return DocumentOut(
        id=d.id, requirement=d.requirement, doc_type=d.doc_type, doc_type_label=labels.get(d.doc_type, d.doc_type),
        doc_type_other=d.doc_type_other, issue_date=d.issue_date, expiry_date=d.expiry_date, filename=d.filename,
        content_type=d.content_type, size_bytes=d.size_bytes, uploaded_at=d.uploaded_at, uploaded_by=_name(db, d.uploaded_by_user_id),
        review_status=d.review_status, review_reason=d.review_reason, reviewed_by=_name(db, d.reviewed_by_user_id),
    )


def _party(p: Party) -> PartyRef:
    return PartyRef(id=p.id, name=p.name, identifier=p.identifier, risk_rating=p.risk_rating, kyc_review_due=p.kyc_review_due)


def _summary(db: Session, a: KycApplication, staff: bool = True) -> dict:
    # The risk rating and its reasons are compliance's working, not shown to applicants.
    return {
        "id": a.id, "reference": a.reference, "client_type": a.client_type, "status": a.status, "display_name": a.display_name,
        "captured_by": _name(db, a.captured_by_user_id), "applicant": _name(db, a.applicant_user_id), "submitted_at": a.submitted_at,
        "risk_rating": a.risk_rating if staff else None, "edd_required": a.edd_required and staff,
        "reviewer": _name(db, a.reviewer_user_id) if staff else None, "updated_at": a.updated_at,
    }


def _out(db: Session, a: KycApplication, user: User) -> ApplicationOut:
    today = kyc.today()
    current = {d.requirement: d for d in kyc.current_documents(a)}
    slots = []
    for s in kyc_forms.slots(a.client_type, a.data):
        labels = {t.code: t.label for t in s.requirement.types}
        doc = current.get(s.key)
        slots.append(SlotOut(
            key=s.key, label=s.label, person=s.person,
            types=[DocTypeOut(code=t.code, label=t.label, max_age_months=t.max_age_months) for t in s.requirement.types],
            issue_date=s.requirement.issue_date, expiry_date=s.requirement.expiry_date,
            document=_doc_out(db, doc, labels) if doc else None, problems=kyc_forms.document_problems(s, doc, today) if doc else [],
        ))
    staff = kyc.is_staff_reader(user)
    declaration = db.get(kyc.DeclarationVersion, a.declaration_version_id) if a.declaration_version_id else None
    return ApplicationOut(
        **_summary(db, a, staff), data=a.data, risk_reasons=a.risk_reasons if staff else [], review_note=a.review_note,
        recommended_by=_name(db, a.recommended_by_user_id), decided_by=_name(db, a.decided_by_user_id), decided_at=a.decided_at,
        decision_reason=a.decision_reason, declaration_accepted_by=a.declaration_accepted_by, declaration_accepted_at=a.declaration_accepted_at,
        declaration_version=declaration.version if declaration else None,
        party=_party(db.get(Party, a.party_id)) if a.party_id and staff else None,
        slots=slots, problems=kyc.check(a) if a.status in kyc.EDITABLE else [],
        possible_duplicates=[_party(p) for p in kyc.possible_duplicates(db, a)] if staff else [],
        changed_fields=kyc.changed_fields(db, a), scheme_id=a.scheme_id, is_change=kyc.is_change(db, a),
        can_edit=kyc.can_edit(user, a),
        can_start_review=a.status == ApplicationStatus.submitted and user.has_role(kyc.REVIEW_ROLE) and not kyc.took_part(user, a),
        can_review=a.status == ApplicationStatus.in_review and a.reviewer_user_id == user.id,
        can_senior_decide=a.status == ApplicationStatus.awaiting_senior_approval and user.has_role(kyc.SENIOR_ROLE)
        and not kyc.took_part(user, a) and user.id != a.recommended_by_user_id,
    )


@router.get("/options")
def options(_: User = Depends(get_current_user)) -> dict:
    """Pick-list values and texts the KYC forms show (product list comes from Setup)."""
    pairs = lambda items: [{"value": v, "label": lbl} for v, lbl in items]  # noqa: E731
    return {
        "entity_forms": pairs(kyc_forms.ENTITY_FORMS), "group_kinds": pairs(kyc_forms.GROUP_KINDS),
        "marital_statuses": pairs(kyc_forms.MARITAL), "contact_modes": pairs(kyc_forms.CONTACT_MODES),
        "genders": pairs(kyc_forms.GENDERS), "income_sources": pairs(kyc_forms.INCOME_SOURCES),
        "pep_definition": kyc_forms.PEP_DEFINITION,
    }


@router.get("/declarations/{client_type}", response_model=DeclarationOut)
def declaration(client_type: ClientType, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> DeclarationOut:
    d = kyc.latest_declaration(db, client_type)
    return DeclarationOut(id=d.id, client_type=d.client_type, version=d.version, title=d.title, body=d.body)


@router.get("/applications", response_model=list[ApplicationSummary])
def list_applications(status_filter: ApplicationStatus | None = None, q: str | None = None, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)) -> list[ApplicationSummary]:
    query = kyc.visible_query(user)
    if status_filter is not None:
        query = query.where(KycApplication.status == status_filter)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(KycApplication.display_name).like(like), func.lower(KycApplication.reference).like(like)))
    rows = db.execute(query.order_by(KycApplication.updated_at.desc()).limit(300)).scalars()
    staff = kyc.is_staff_reader(user)
    return [ApplicationSummary(**_summary(db, a, staff)) for a in rows]


@router.post("/applications", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    return _out(db, kyc.create(db, user, payload.client_type, payload.data), user)


@router.get("/applications/{application_id}", response_model=ApplicationOut)
def get_application(application_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    return _out(db, kyc.get_visible(db, user, application_id), user)


@router.put("/applications/{application_id}", response_model=ApplicationOut)
def save_application(application_id: uuid.UUID, payload: ApplicationSave, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> ApplicationOut:
    """Saves the form as a draft (no completeness check until submit)."""
    app = kyc.get_visible(db, user, application_id)
    return _out(db, kyc.save(db, user, app, payload.data), user)


@router.post("/applications/{application_id}/documents", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    application_id: uuid.UUID,
    requirement: str = Form(...), doc_type: str = Form(...), doc_type_other: str | None = Form(None),
    issue_date: date | None = Form(None), expiry_date: date | None = Form(None),
    file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> ApplicationOut:
    app = kyc.get_visible(db, user, application_id)
    content = await file.read()
    kyc.upload(db, user, app, requirement=requirement, doc_type=doc_type, doc_type_other=doc_type_other, issue_date=issue_date,
               expiry_date=expiry_date, filename=file.filename or "document", content=content)
    db.refresh(app)
    return _out(db, app, user)


@router.delete("/applications/{application_id}/documents/{document_id}", response_model=ApplicationOut)
def remove_document(application_id: uuid.UUID, document_id: uuid.UUID, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> ApplicationOut:
    app = kyc.get_visible(db, user, application_id)
    doc = db.get(KycDocument, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    kyc.remove_document(db, user, app, doc)
    db.refresh(app)
    return _out(db, app, user)


@router.get("/applications/{application_id}/documents/{document_id}/file")
def download_document(application_id: uuid.UUID, document_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)) -> Response:
    """Streams the file; each view is audit-logged."""
    app = kyc.get_visible(db, user, application_id)
    doc, content = kyc.read_document(db, user, app, document_id, client_ip(request))
    safe = "".join(c for c in doc.filename if c.isalnum() or c in "._- ") or "document"
    return Response(content=content, media_type=doc.content_type,
                    headers={"Content-Disposition": f'inline; filename="{safe}"', "Cache-Control": "no-store"})


@router.post("/applications/{application_id}/submit", response_model=ApplicationOut)
def submit_application(application_id: uuid.UUID, payload: SubmitIn, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)) -> ApplicationOut:
    app = kyc.get_visible(db, user, application_id)
    return _out(db, kyc.submit(db, user, app, declaration_version_id=payload.declaration_version_id,
                               accepted_by=payload.accepted_by, ip=client_ip(request)), user)


# ---- compliance review


@router.post("/applications/{application_id}/start-review", response_model=ApplicationOut)
def start_review(application_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    return _out(db, kyc.start_review(db, user, kyc.get_visible(db, user, application_id)), user)


@router.post("/applications/{application_id}/documents/{document_id}/review", response_model=ApplicationOut)
def review_document(application_id: uuid.UUID, document_id: uuid.UUID, payload: DocumentReviewIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> ApplicationOut:
    app = kyc.get_visible(db, user, application_id)
    kyc.review_document(db, user, app, document_id, payload.accept, payload.reason)
    db.refresh(app)
    return _out(db, app, user)


@router.post("/applications/{application_id}/return", response_model=ApplicationOut)
def return_application(application_id: uuid.UUID, payload: NoteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    return _out(db, kyc.return_to_applicant(db, user, kyc.get_visible(db, user, application_id), payload.note), user)


@router.post("/applications/{application_id}/approve", response_model=ApplicationOut)
def approve_application(application_id: uuid.UUID, payload: ApproveIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    return _out(db, kyc.approve(db, user, kyc.get_visible(db, user, application_id), payload.note, payload.risk_override), user)


@router.post("/applications/{application_id}/reject", response_model=ApplicationOut)
def reject_application(application_id: uuid.UUID, payload: NoteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    return _out(db, kyc.reject(db, user, kyc.get_visible(db, user, application_id), payload.note), user)


@router.post("/applications/{application_id}/senior-decision", response_model=ApplicationOut)
def senior_decision(application_id: uuid.UUID, payload: SeniorDecisionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    app = kyc.get_visible(db, user, application_id)
    return _out(db, kyc.senior_decide(db, user, app, payload.approve, payload.reason), user)


@router.get("/expiring", response_model=list[ExpiringOut])
def list_expiring(within_days: int = 60, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[ExpiringOut]:
    """KYC reviews and identity documents due within `within_days` (and overdue ones) — staff only."""
    if not kyc.is_staff_reader(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to see clients")
    return [ExpiringOut(**vars(i)) for i in kyc_expiry.expiring(db, kyc.today(), max(1, min(within_days, 366)))]


@router.get("/parties", response_model=list[PartyRef])
def list_parties(q: str | None = None, client_type: ClientType | None = None, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> list[PartyRef]:
    """Approved clients (staff only)."""
    if not (kyc.is_staff_reader(user) or user.has_any_role(*PARTY_PICKERS)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to see clients")
    query = select(Party).order_by(Party.name)
    if client_type is not None:
        query = query.where(Party.client_type == client_type)
    if q:
        query = query.where(Party.name.ilike(f"%{q.strip()}%"))
    return [_party(p) for p in db.execute(query.limit(300)).scalars()]
