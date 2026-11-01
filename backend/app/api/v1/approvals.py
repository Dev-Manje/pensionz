import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.identity import User
from app.schemas.approval import ApprovalDecision, ApprovalOut
from app.services import approvals

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _name(db: Session, user_id: uuid.UUID | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return (user.full_name or user.email) if user else None


def to_out(db: Session, request: ApprovalRequest, viewer: User) -> ApprovalOut:
    spec = approvals._KINDS.get(request.kind)
    return ApprovalOut(
        id=request.id,
        kind=request.kind,
        kind_label=spec.label if spec else request.kind,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        summary=request.summary,
        payload=request.payload,
        previous=request.previous,
        status=request.status,
        initiated_by=_name(db, request.initiated_by_user_id) or "",
        initiated_by_user_id=request.initiated_by_user_id,
        created_at=request.created_at,
        reviewed_by=_name(db, request.reviewed_by_user_id),
        reviewed_at=request.reviewed_at,
        review_comment=request.review_comment,
        can_review=approvals.can_review(db, viewer, request),
        can_cancel=request.status == ApprovalStatus.pending and request.initiated_by_user_id == viewer.id,
    )


@router.get("", response_model=list[ApprovalOut])
def list_approvals(
    status_filter: ApprovalStatus | None = ApprovalStatus.pending,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> list[ApprovalOut]:
    rows = db.execute(approvals.visible_query(db, user, status_filter).limit(500)).scalars()
    return [to_out(db, r, user) for r in rows]


@router.get("/{request_id}", response_model=ApprovalOut)
def get_approval(request_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> ApprovalOut:
    request = db.get(ApprovalRequest, request_id)
    if request is None or not approvals.can_view(db, user, request):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return to_out(db, request, user)


@router.post("/{request_id}/approve", response_model=ApprovalOut)
def approve(request_id: uuid.UUID, payload: ApprovalDecision, db: Session = Depends(get_db),
            user: User = Depends(require_staff)) -> ApprovalOut:
    return to_out(db, approvals.approve(db, request_id, user, payload.comment), user)


@router.post("/{request_id}/reject", response_model=ApprovalOut)
def reject(request_id: uuid.UUID, payload: ApprovalDecision, db: Session = Depends(get_db),
           user: User = Depends(require_staff)) -> ApprovalOut:
    return to_out(db, approvals.reject(db, request_id, user, payload.comment or ""), user)


@router.post("/{request_id}/cancel", response_model=ApprovalOut)
def cancel(request_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)) -> ApprovalOut:
    return to_out(db, approvals.cancel(db, request_id, user), user)
