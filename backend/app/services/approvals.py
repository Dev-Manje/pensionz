"""Maker-checker engine (FR-SEC-002, pz-backend-feature skill).

A domain service registers an ApprovalKind once (who may approve, what
approval does) and then calls `submit(...)` instead of changing data directly.
A checker approves or rejects through the generic /approvals endpoints:

- the checker must hold one of the kind's checker roles, and must not be the maker;
- a request about a fund is only visible to, and decidable by, staff who
  administer that fund (FR-SEC-001);
- only a pending request can be decided (409 otherwise) — the row is locked,
  so two checkers can't both approve;
- approval runs the kind's `apply` in the same commit as the status change,
  its audit event and the maker's notification.
"""
import uuid
from dataclasses import dataclass, field
from typing import Callable

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select, true
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.identity import User, UserRole
from app.models.mixins import utcnow
from app.services import audit, fund_access, notifications

# Roles that may see every request (read-only for auditors).
OVERSIGHT_ROLES = frozenset({UserRole.admin, UserRole.auditor})


@dataclass(frozen=True)
class ApprovalKind:
    name: str
    label: str
    checker_roles: frozenset[UserRole]
    # Applies the approved change. Must not commit.
    apply: Callable[[Session, ApprovalRequest, User], None]
    # Optional clean-up when rejected or cancelled (release a hold, etc.). Must not commit.
    on_reject: Callable[[Session, ApprovalRequest, User], None] | None = field(default=None)


_KINDS: dict[str, ApprovalKind] = {}


def register(kind: ApprovalKind) -> ApprovalKind:
    _KINDS[kind.name] = kind
    return kind


def get_kind(name: str) -> ApprovalKind:
    try:
        return _KINDS[name]
    except KeyError:
        raise HTTPException(status_code=500, detail=f"Unknown approval kind '{name}'")


def kinds() -> list[ApprovalKind]:
    return list(_KINDS.values())


def submit(
    db: Session,
    maker: User,
    kind: str,
    *,
    entity_type: str,
    entity_id: object | None,
    summary: str,
    payload: dict,
    previous: dict | None = None,
    fund_id: uuid.UUID | None = None,
) -> ApprovalRequest:
    """Queues a change for a checker. Does not commit (the caller's service does)."""
    spec = get_kind(kind)
    if entity_id is not None:
        clash = db.execute(
            select(ApprovalRequest.id).where(
                ApprovalRequest.kind == kind,
                ApprovalRequest.entity_id == str(entity_id),
                ApprovalRequest.status == ApprovalStatus.pending,
            )
        ).first()
        if clash is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "There is already a change waiting for approval on this record")
    request = ApprovalRequest(
        kind=kind,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary=summary[:300],
        payload=audit._jsonable(payload),
        previous=audit._jsonable(previous) if previous is not None else None,
        fund_id=fund_id,
        initiated_by_user_id=maker.id,
    )
    db.add(request)
    db.flush()
    audit.record(db, maker.id, "approval_request", request.id, "submitted", after={"kind": kind, "summary": summary}, fund_id=fund_id)
    checkers = notifications.users_with_roles(db, set(spec.checker_roles), exclude={maker.id})
    if fund_id is not None:
        checkers = [c for c in checkers if fund_access.can_access(db, c, fund_id)]
    notifications.notify_approval_needed(db, checkers, summary, request.id)
    return request


def _in_scope(db: Session, user: User, request: ApprovalRequest) -> bool:
    return request.fund_id is None or fund_access.can_access(db, user, request.fund_id)


def can_review(db: Session, user: User, request: ApprovalRequest) -> bool:
    spec = _KINDS.get(request.kind)
    return (
        spec is not None
        and _in_scope(db, user, request)
        and request.status == ApprovalStatus.pending
        and request.initiated_by_user_id != user.id
        and user.has_any_role(*spec.checker_roles)
    )


def can_view(db: Session, user: User, request: ApprovalRequest) -> bool:
    spec = _KINDS.get(request.kind)
    return (
        request.initiated_by_user_id == user.id
        or user.has_any_role(*OVERSIGHT_ROLES)
        or (spec is not None and user.has_any_role(*spec.checker_roles) and _in_scope(db, user, request))
    )


def visible_query(db: Session, user: User, status_filter: ApprovalStatus | None):
    """Requests the user made, plus those for kinds they check within their
    funds (all for oversight roles)."""
    query = select(ApprovalRequest)
    if not user.has_any_role(*OVERSIGHT_ROLES):
        checkable = [k.name for k in _KINDS.values() if user.has_any_role(*k.checker_roles)]
        funds = fund_access.fund_ids_for(db, user)
        in_scope = true() if funds is None else or_(ApprovalRequest.fund_id.is_(None), ApprovalRequest.fund_id.in_(funds))
        query = query.where(or_(
            ApprovalRequest.initiated_by_user_id == user.id,
            and_(ApprovalRequest.kind.in_(checkable), in_scope),
        ))
    if status_filter is not None:
        query = query.where(ApprovalRequest.status == status_filter)
    return query.order_by(ApprovalRequest.created_at.desc())


def _load_for_decision(db: Session, request_id: uuid.UUID) -> ApprovalRequest:
    request = db.execute(select(ApprovalRequest).where(ApprovalRequest.id == request_id).with_for_update()).scalar_one_or_none()
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if request.status != ApprovalStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request was already {request.status.value}")
    return request


def _check_checker(db: Session, user: User, request: ApprovalRequest) -> ApprovalKind:
    spec = get_kind(request.kind)
    if not _in_scope(db, user, request):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if request.initiated_by_user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't approve or reject your own request — another person must check it")
    if not user.has_any_role(*spec.checker_roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to decide this request")
    return spec


def _finish(db: Session, request: ApprovalRequest, user: User, new_status: ApprovalStatus, comment: str | None) -> None:
    request.status = new_status
    request.reviewed_by_user_id = user.id
    request.reviewed_at = utcnow()
    request.review_comment = comment
    audit.record(db, user.id, "approval_request", request.id, new_status.value,
                 after={"kind": request.kind, "comment": comment}, fund_id=request.fund_id)
    maker = db.get(User, request.initiated_by_user_id)
    if maker is not None and maker.id != user.id:
        notifications.notify_approval_decided(db, maker, request.summary, new_status == ApprovalStatus.approved, comment, request.id)


def approve(db: Session, request_id: uuid.UUID, user: User, comment: str | None = None) -> ApprovalRequest:
    request = _load_for_decision(db, request_id)
    spec = _check_checker(db, user, request)
    spec.apply(db, request, user)
    _finish(db, request, user, ApprovalStatus.approved, comment)
    db.commit()
    db.refresh(request)
    return request


def reject(db: Session, request_id: uuid.UUID, user: User, comment: str) -> ApprovalRequest:
    if not comment or not comment.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give a reason so the person who asked knows what to fix")
    request = _load_for_decision(db, request_id)
    spec = _check_checker(db, user, request)
    if spec.on_reject:
        spec.on_reject(db, request, user)
    _finish(db, request, user, ApprovalStatus.rejected, comment.strip())
    db.commit()
    db.refresh(request)
    return request


def cancel(db: Session, request_id: uuid.UUID, user: User) -> ApprovalRequest:
    request = _load_for_decision(db, request_id)
    if request.initiated_by_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who made the request can withdraw it")
    spec = get_kind(request.kind)
    if spec.on_reject:
        spec.on_reject(db, request, user)
    request.status = ApprovalStatus.cancelled
    request.reviewed_at = utcnow()
    audit.record(db, user.id, "approval_request", request.id, "cancelled", fund_id=request.fund_id)
    db.commit()
    db.refresh(request)
    return request
