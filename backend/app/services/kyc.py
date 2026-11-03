"""KYC applications (FR-ONB): draft → submit → compliance review → approve.

Who does what
- Staff capture paper applications (compliance, relationship manager, member
  admin); portal users (principal officer, individual) apply for themselves.
  Either can edit while the application is a draft or has been returned.
- A compliance officer who neither captured nor applied reviews it: accepts or
  rejects each document, returns it for fixes, rejects it, or approves it.
- High risk (any PEP) needs enhanced due diligence: compliance recommends, an
  administrator who took no other part approves (FR-ONB-103).
- Approval creates or refreshes the `Party` with its next KYC review date
  (regulatory parameters kyc_review_years_<rating>).
"""
import copy
import hashlib
import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, object_session

from app.core import storage
from app.models.identity import User, UserRole
from app.models.kyc import (
    ApplicationStatus, ClientType, DeclarationVersion, DocumentReview, KycApplication, KycDocument, Party, RiskRating,
)
from app.models.mixins import utcnow
from app.models.scheme import Scheme, SchemeOfficer
from app.services import audit, config_resolver, kyc_forms, notifications

CAPTURE_ROLES = (UserRole.compliance, UserRole.relationship_manager, UserRole.member_admin)
READ_ROLES = (*CAPTURE_ROLES, UserRole.admin, UserRole.auditor)
REVIEW_ROLE = UserRole.compliance
SENIOR_ROLE = UserRole.admin
APPLICANT_ROLES = {ClientType.corporate: UserRole.principal_officer, ClientType.group: UserRole.principal_officer,
                   ClientType.individual: UserRole.individual}
EDITABLE = (ApplicationStatus.draft, ApplicationStatus.returned)


def today() -> date:
    return date.today()


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 February in a non-leap year
        return d.replace(year=d.year + years, day=28)


# ---- access


def is_staff_reader(user: User) -> bool:
    return user.has_any_role(*READ_ROLES)


def _officer_scheme_ids(user: User):
    return select(SchemeOfficer.scheme_id).where(SchemeOfficer.user_id == user.id)


def visible_query(user: User):
    query = select(KycApplication)
    if not is_staff_reader(user):
        # Portal: their own applications, and any made for an employer they act for.
        query = query.where(or_(KycApplication.applicant_user_id == user.id, KycApplication.scheme_id.in_(_officer_scheme_ids(user))))
    return query


def acts_for(user: User, app: KycApplication) -> bool:
    """The portal applicant, or another principal officer of the employer the application is for."""
    if app.applicant_user_id == user.id:
        return True
    if app.scheme_id is None or not user.has_role(UserRole.principal_officer):
        return False
    return object_session(app).execute(
        select(SchemeOfficer.id).where(SchemeOfficer.scheme_id == app.scheme_id, SchemeOfficer.user_id == user.id)
    ).first() is not None


def get_visible(db: Session, user: User, application_id: uuid.UUID) -> KycApplication:
    app = db.get(KycApplication, application_id)
    if app is None or not (is_staff_reader(user) or acts_for(user, app)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return app


def can_edit(user: User, app: KycApplication) -> bool:
    if app.status not in EDITABLE:
        return False
    if app.applicant_user_id is None:
        return user.has_any_role(*CAPTURE_ROLES)
    return acts_for(user, app)


def applicant_link(app: KycApplication) -> str:
    """Where the applicant opens the application: the portal for officers, the KYC screen for staff."""
    if app.applicant_user_id and app.client_type != ClientType.individual:
        return f"/po/kyc/{app.id}"
    if app.applicant_user_id:  # a member's own KYC from the member portal
        return f"/member/kyc/{app.id}"
    return f"/kyc/{app.id}"


def _require_edit(user: User, app: KycApplication) -> None:
    if app.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "This application can't be changed now — it is with compliance")
    if not can_edit(user, app):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't change this application")


def took_part(user: User, app: KycApplication) -> bool:
    return user.id in (app.captured_by_user_id, app.applicant_user_id)


# ---- drafts


def _reference(db: Session) -> str:
    number = db.execute(text("SELECT nextval('kyc_reference_seq')")).scalar_one()
    return f"KYC-{today().year}-{number:06d}"


def create(db: Session, user: User, client_type: ClientType, data: dict | None = None) -> KycApplication:
    portal = not user.has_any_role(*CAPTURE_ROLES)
    # Members apply as individuals too (their own KYC from the member portal).
    allowed = {APPLICANT_ROLES[client_type]} | ({UserRole.member} if client_type == ClientType.individual else set())
    if portal and not user.has_any_role(*allowed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't start this kind of application")
    data = data or {}
    app = KycApplication(
        reference=_reference(db), client_type=client_type, data=data, display_name=kyc_forms.display_name(client_type, data),
        captured_by_user_id=None if portal else user.id, applicant_user_id=user.id if portal else None,
    )
    db.add(app)
    db.flush()
    audit.record(db, user.id, "kyc_application", app.id, "created", after={"reference": app.reference, "client_type": client_type.value})
    db.commit()
    db.refresh(app)
    return app


def save(db: Session, user: User, app: KycApplication, data: dict) -> KycApplication:
    _require_edit(user, app)
    app.data = data
    app.display_name = kyc_forms.display_name(app.client_type, data)
    db.commit()
    db.refresh(app)
    return app


def current_documents(app: KycApplication) -> list[KycDocument]:
    return [d for d in app.documents if not d.superseded]


def upload(db: Session, user: User, app: KycApplication, *, requirement: str, doc_type: str, doc_type_other: str | None,
           issue_date: date | None, expiry_date: date | None, filename: str, content: bytes) -> KycDocument:
    _require_edit(user, app)
    slot = next((s for s in kyc_forms.slots(app.client_type, app.data) if s.key == requirement), None)
    if slot is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This application doesn't ask for that document — save the form first")
    if doc_type not in {t.code for t in slot.requirement.types}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose the document type from the list")
    if len(content) > storage.MAX_EVIDENCE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is larger than 10 MB")
    content_type = storage.evidence_type(content)
    if content_type is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a PDF or a photo (JPEG, PNG or WebP)")
    if issue_date and issue_date > today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The issue date can't be in the future")
    if issue_date and expiry_date and expiry_date <= issue_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The expiry date must be after the issue date")
    key = storage.upload_file(content, content_type, f"kyc/{app.id}")
    for old in current_documents(app):
        if old.requirement == requirement:
            old.superseded = True
    doc = KycDocument(
        application_id=app.id, requirement=requirement, doc_type=doc_type,
        doc_type_other=(doc_type_other or "").strip() or None if doc_type == "other" else None,
        issue_date=issue_date, expiry_date=expiry_date, storage_key=key, filename=filename[:200] or "document",
        content_type=content_type, size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
        uploaded_by_user_id=user.id, uploaded_at=utcnow(),
    )
    db.add(doc)
    db.flush()
    audit.record(db, user.id, "kyc_document", doc.id, "uploaded", after={"application": app.reference, "requirement": requirement, "doc_type": doc_type})
    db.commit()
    db.refresh(doc)
    return doc


def remove_document(db: Session, user: User, app: KycApplication, doc: KycDocument) -> None:
    """Withdraw a draft upload (kept, marked superseded, for the record)."""
    _require_edit(user, app)
    if doc.application_id != app.id or doc.superseded:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    doc.superseded = True
    audit.record(db, user.id, "kyc_document", doc.id, "withdrawn")
    db.commit()


def read_document(db: Session, user: User, app: KycApplication, doc_id: uuid.UUID, ip: str | None) -> tuple[KycDocument, bytes]:
    doc = db.get(KycDocument, doc_id)
    if doc is None or doc.application_id != app.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    # Every view of identity evidence is logged (FR-SEC-003).
    audit.record(db, user.id, "kyc_document", doc.id, "viewed", ip_address=ip)
    db.commit()
    return doc, storage.download_file(doc.storage_key)


# ---- submit


def latest_declaration(db: Session, client_type: ClientType) -> DeclarationVersion:
    declaration = db.execute(
        select(DeclarationVersion).where(DeclarationVersion.client_type == client_type, DeclarationVersion.effective_from <= today())
        .order_by(DeclarationVersion.version.desc()).limit(1)
    ).scalar_one_or_none()
    if declaration is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No declaration has been set up for this kind of client")
    return declaration


def check(app: KycApplication) -> list[str]:
    return kyc_forms.problems(app.client_type, app.data, current_documents(app), today())


def submit(db: Session, user: User, app: KycApplication, *, declaration_version_id: uuid.UUID, accepted_by: str, ip: str | None) -> KycApplication:
    _require_edit(user, app)
    issues = check(app)
    if issues:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{len(issues)} thing(s) to finish first: " + "; ".join(issues[:8]))
    declaration = latest_declaration(db, app.client_type)
    if declaration.id != declaration_version_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "The declaration has been updated — read the new wording and accept it again")
    if len(accepted_by.strip()) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Type the full name of the person accepting the declaration")
    rating, reasons = kyc_forms.risk(app.client_type, app.data)
    app.declaration_version_id, app.declaration_accepted_by = declaration.id, accepted_by.strip()
    app.declaration_accepted_at, app.declaration_accepted_ip = utcnow(), ip
    app.risk_rating, app.risk_reasons, app.edd_required = rating, reasons, rating == RiskRating.high
    resubmitted = app.status == ApplicationStatus.returned
    app.status, app.submitted_at = ApplicationStatus.submitted, utcnow()
    # A resubmission goes back to the reviewer who returned it.
    if not resubmitted:
        app.reviewer_user_id = None
    audit.record(db, user.id, "kyc_application", app.id, "submitted",
                 after={"risk_rating": rating.value, "declaration_version": declaration.version, "resubmitted": resubmitted}, ip_address=ip)
    reviewers = [db.get(User, app.reviewer_user_id)] if resubmitted and app.reviewer_user_id else \
        notifications.users_with_roles(db, {REVIEW_ROLE}, exclude={user.id})
    notifications.notify_kyc_submitted(db, [r for r in reviewers if r], app.reference, app.display_name, app.id)
    db.commit()
    db.refresh(app)
    return app


# ---- review


def _require_reviewer(user: User, app: KycApplication) -> None:
    if not user.has_role(REVIEW_ROLE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only compliance can review KYC applications")
    if took_part(user, app):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You captured this application, so another person must review it")


def start_review(db: Session, user: User, app: KycApplication) -> KycApplication:
    _require_reviewer(user, app)
    if app.status != ApplicationStatus.submitted:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a submitted application can be taken for review")
    app.status, app.reviewer_user_id = ApplicationStatus.in_review, user.id
    audit.record(db, user.id, "kyc_application", app.id, "review_started")
    db.commit()
    db.refresh(app)
    return app


def _require_my_review(user: User, app: KycApplication) -> None:
    _require_reviewer(user, app)
    if app.status != ApplicationStatus.in_review:
        raise HTTPException(status.HTTP_409_CONFLICT, "This application isn't in review")
    if app.reviewer_user_id != user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Another compliance officer is reviewing this application")


def review_document(db: Session, user: User, app: KycApplication, doc_id: uuid.UUID, accept: bool, reason: str | None) -> KycDocument:
    _require_my_review(user, app)
    doc = db.get(KycDocument, doc_id)
    if doc is None or doc.application_id != app.id or doc.superseded:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if not accept and not (reason or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say why the document isn't acceptable so the applicant can fix it")
    doc.review_status = DocumentReview.accepted if accept else DocumentReview.rejected
    doc.review_reason = None if accept else reason.strip()
    doc.reviewed_by_user_id, doc.reviewed_at = user.id, utcnow()
    audit.record(db, user.id, "kyc_document", doc.id, doc.review_status.value, after={"reason": doc.review_reason})
    db.commit()
    db.refresh(doc)
    return doc


def _applicant_or_capturer(db: Session, app: KycApplication) -> User | None:
    user_id = app.applicant_user_id or app.captured_by_user_id
    return db.get(User, user_id) if user_id else None


def return_to_applicant(db: Session, user: User, app: KycApplication, note: str) -> KycApplication:
    _require_my_review(user, app)
    if not note or not note.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say what needs to change")
    app.status, app.review_note = ApplicationStatus.returned, note.strip()
    audit.record(db, user.id, "kyc_application", app.id, "returned", after={"note": app.review_note})
    who = _applicant_or_capturer(db, app)
    if who:
        notifications.notify_kyc_returned(db, who, app.reference, app.review_note, app.id, applicant_link(app))
    db.commit()
    db.refresh(app)
    return app


def _review_years(db: Session, rating: RiskRating) -> int:
    years = config_resolver.regulatory(db, f"kyc_review_years_{rating.value}", today())
    if years is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Set the KYC review period for {rating.value} risk under Regulatory first")
    return int(years)


def _approve(db: Session, user: User, app: KycApplication) -> None:
    years = _review_years(db, app.risk_rating)
    now = utcnow()
    due = add_years(today(), years)
    is_pep = app.risk_rating == RiskRating.high and any("politically exposed" in r for r in app.risk_reasons)
    party = db.get(Party, app.party_id) if app.party_id else None
    if party is None:
        party = Party(client_type=app.client_type, name=app.display_name, identifier=kyc_forms.identifier(app.client_type, app.data),
                      risk_rating=app.risk_rating, is_pep=is_pep, kyc_approved_at=now, kyc_review_due=due)
        db.add(party)
        db.flush()
        app.party_id = party.id
    else:
        party.name, party.identifier = app.display_name, kyc_forms.identifier(app.client_type, app.data)
        party.risk_rating, party.is_pep, party.kyc_approved_at, party.kyc_review_due = app.risk_rating, is_pep, now, due
    party.latest_application_id = app.id
    app.status, app.decided_by_user_id, app.decided_at = ApplicationStatus.approved, user.id, now
    audit.record(db, user.id, "kyc_application", app.id, "approved", after={"party_id": party.id, "review_due": due, "risk": app.risk_rating.value})
    _link_scheme(db, user, app, party)
    from app.services import employer_applications  # imports this module

    employer_applications.kyc_approved(db, app)
    who = _applicant_or_capturer(db, app)
    if who:
        notifications.notify_kyc_decided(db, who, app.reference, True, None, app.id, applicant_link(app))


def _link_scheme(db: Session, user: User, app: KycApplication, party: Party) -> None:
    """An employer's first approved KYC from the portal links the employer to the client.
    The compliance approval is the check; an employer already linked keeps its client."""
    scheme = db.get(Scheme, app.scheme_id) if app.scheme_id else None
    if scheme is None or scheme.party_id is not None or app.client_type == ClientType.individual:
        return
    scheme.party_id = party.id
    audit.record(db, user.id, "scheme", scheme.id, "client_linked", after={"party_id": party.id, "kyc_application": app.reference})


def approve(db: Session, user: User, app: KycApplication, note: str | None, risk_override: RiskRating | None) -> KycApplication:
    _require_my_review(user, app)
    pending = [d for d in current_documents(app) if d.review_status != DocumentReview.accepted]
    if pending:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Accept every document first ({len(pending)} not accepted)")
    if risk_override is not None and risk_override != app.risk_rating:
        if not (note or "").strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give a reason for changing the risk rating")
        app.risk_reasons = [*app.risk_reasons, f"Rating changed from {app.risk_rating.value} to {risk_override.value} by compliance: {note.strip()}"]
        app.risk_rating = risk_override
        app.edd_required = risk_override == RiskRating.high
    app.review_note = (note or "").strip() or None
    if app.risk_rating == RiskRating.high:
        app.status, app.recommended_by_user_id = ApplicationStatus.awaiting_senior_approval, user.id
        audit.record(db, user.id, "kyc_application", app.id, "recommended", after={"note": app.review_note})
        approvers = notifications.users_with_roles(db, {SENIOR_ROLE}, exclude={user.id})
        notifications.notify_kyc_senior_approval(db, approvers, app.reference, app.display_name, app.id)
    else:
        _approve(db, user, app)
    db.commit()
    db.refresh(app)
    return app


def senior_decide(db: Session, user: User, app: KycApplication, approve_it: bool, reason: str | None) -> KycApplication:
    if app.status != ApplicationStatus.awaiting_senior_approval:
        raise HTTPException(status.HTTP_409_CONFLICT, "This application isn't waiting for senior approval")
    if not user.has_role(SENIOR_ROLE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can approve a high-risk client")
    if took_part(user, app) or user.id == app.recommended_by_user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You took part in this application, so another person must decide")
    if approve_it:
        _approve(db, user, app)
    else:
        _reject(db, user, app, reason)
    db.commit()
    db.refresh(app)
    return app


def _reject(db: Session, user: User, app: KycApplication, reason: str | None) -> None:
    if not (reason or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give a reason for rejecting the application")
    app.status, app.decided_by_user_id, app.decided_at, app.decision_reason = ApplicationStatus.rejected, user.id, utcnow(), reason.strip()
    audit.record(db, user.id, "kyc_application", app.id, "rejected", after={"reason": app.decision_reason})
    who = _applicant_or_capturer(db, app)
    if who:
        notifications.notify_kyc_decided(db, who, app.reference, False, app.decision_reason, app.id, applicant_link(app))


def reject(db: Session, user: User, app: KycApplication, reason: str) -> KycApplication:
    _require_my_review(user, app)
    _reject(db, user, app, reason)
    db.commit()
    db.refresh(app)
    return app


# ---- staff-side duplicate matching (FR-ONB-002: never shown to applicants)


def possible_duplicates(db: Session, app: KycApplication) -> list[Party]:
    ident = kyc_forms.identifier(app.client_type, app.data)
    conditions = [func.lower(Party.name) == app.display_name.lower()] if app.display_name else []
    if ident:
        conditions.append(func.lower(Party.identifier) == ident.lower())
    if not conditions:
        return []
    return list(db.execute(
        select(Party).where(Party.client_type == app.client_type, or_(*conditions), Party.id != (app.party_id or uuid.uuid4())).limit(10)
    ).scalars())


# ---- principal officer portal: the employer's own KYC and changes to it (FR-PRT-001)

OPEN = (ApplicationStatus.draft, ApplicationStatus.submitted, ApplicationStatus.in_review, ApplicationStatus.returned,
        ApplicationStatus.awaiting_senior_approval)


def scheme_applications(db: Session, scheme: Scheme) -> list[KycApplication]:
    """Applications for this employer: made from the portal, or refreshing its linked client."""
    condition = KycApplication.scheme_id == scheme.id
    if scheme.party_id:
        condition = or_(condition, KycApplication.party_id == scheme.party_id)
    return list(db.execute(select(KycApplication).where(condition).order_by(KycApplication.created_at.desc()).limit(30)).scalars())


def open_application(db: Session, scheme: Scheme) -> KycApplication | None:
    return next((a for a in scheme_applications(db, scheme) if a.status in OPEN), None)


def start_for_scheme(db: Session, user: User, scheme: Scheme) -> KycApplication:
    """A principal officer starts the employer's KYC, or a change to it.

    A change starts from the last approved answers, with the accepted documents
    carried over (pending review again) so only what changed needs uploading."""
    current = open_application(db, scheme)
    if current is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{current.reference} is already in progress for this employer — continue that one")
    party = db.get(Party, scheme.party_id) if scheme.party_id else None
    base = db.get(KycApplication, party.latest_application_id) if party and party.latest_application_id else None
    client_type = base.client_type if base else ClientType.corporate
    data = copy.deepcopy(base.data) if base else {"entity_name": scheme.name}
    app = KycApplication(
        reference=_reference(db), client_type=client_type, data=data, display_name=kyc_forms.display_name(client_type, data),
        applicant_user_id=user.id, scheme_id=scheme.id, party_id=party.id if party else None,
    )
    db.add(app)
    db.flush()
    carried = 0
    for doc in current_documents(base) if base else []:
        if doc.review_status != DocumentReview.accepted:
            continue
        db.add(KycDocument(
            application_id=app.id, requirement=doc.requirement, doc_type=doc.doc_type, doc_type_other=doc.doc_type_other,
            issue_date=doc.issue_date, expiry_date=doc.expiry_date, storage_key=doc.storage_key, filename=doc.filename,
            content_type=doc.content_type, size_bytes=doc.size_bytes, sha256=doc.sha256,
            uploaded_by_user_id=doc.uploaded_by_user_id, uploaded_at=doc.uploaded_at,
        ))
        carried += 1
    audit.record(db, user.id, "kyc_application", app.id, "created",
                 after={"reference": app.reference, "scheme_id": scheme.id, "change_of": base.reference if base else None,
                        "documents_carried_over": carried})
    db.commit()
    db.refresh(app)
    return app


def start_change_for_party(db: Session, user: User, party: Party) -> KycApplication:
    """A portal applicant (a member) changes their own approved KYC: the last
    approved answers prefilled, accepted documents carried over pending review."""
    base = db.get(KycApplication, party.latest_application_id) if party.latest_application_id else None
    data = copy.deepcopy(base.data) if base else {}
    app = KycApplication(reference=_reference(db), client_type=party.client_type, data=data,
                         display_name=kyc_forms.display_name(party.client_type, data), applicant_user_id=user.id, party_id=party.id)
    db.add(app)
    db.flush()
    carried = 0
    for doc in current_documents(base) if base else []:
        if doc.review_status != DocumentReview.accepted:
            continue
        db.add(KycDocument(
            application_id=app.id, requirement=doc.requirement, doc_type=doc.doc_type, doc_type_other=doc.doc_type_other,
            issue_date=doc.issue_date, expiry_date=doc.expiry_date, storage_key=doc.storage_key, filename=doc.filename,
            content_type=doc.content_type, size_bytes=doc.size_bytes, sha256=doc.sha256,
            uploaded_by_user_id=doc.uploaded_by_user_id, uploaded_at=doc.uploaded_at,
        ))
        carried += 1
    audit.record(db, user.id, "kyc_application", app.id, "created",
                 after={"reference": app.reference, "party_id": party.id, "change_of": base.reference if base else None,
                        "documents_carried_over": carried})
    db.commit()
    db.refresh(app)
    return app


def is_change(db: Session, app: KycApplication) -> bool:
    """A change to an approved client — not its first KYC (approval sets party_id on both)."""
    if app.party_id is None:
        return False
    earlier = select(KycApplication.id).where(
        KycApplication.party_id == app.party_id, KycApplication.id != app.id, KycApplication.status == ApplicationStatus.approved,
        KycApplication.created_at < app.created_at,
    )
    return db.execute(earlier.limit(1)).first() is not None


def _flat(data: dict) -> dict:
    out = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out.update({f"{key}.{k}": v for k, v in value.items()})
        else:
            out[key] = value
    return out


def changed_fields(db: Session, app: KycApplication) -> list[str]:
    """Answers that differ from the client's last approved application (a change request), by field name;
    a changed director / signatory list is reported once under the list's name."""
    party = db.get(Party, app.party_id) if app.party_id else None
    if party is None or not party.latest_application_id or party.latest_application_id == app.id:
        return []
    base = db.get(KycApplication, party.latest_application_id)
    if base is None:
        return []
    old, new = _flat(base.data or {}), _flat(app.data or {})
    blank = lambda v: v in (None, "", [], {})  # noqa: E731
    return sorted(k for k in set(old) | set(new) if not (blank(old.get(k)) and blank(new.get(k))) and old.get(k) != new.get(k))
