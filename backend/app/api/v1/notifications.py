import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.identity import User
from app.models.mixins import utcnow
from app.models.notification import UserNotification
from app.schemas.notification import NotificationOut, NotificationPage, UnreadCount

router = APIRouter(prefix="/me/notifications", tags=["notifications"])


@router.get("", response_model=NotificationPage)
def list_mine(unread_only: bool = False, limit: int = 20, offset: int = 0, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> NotificationPage:
    mine = UserNotification.user_id == user.id
    query = select(UserNotification).where(mine)
    if unread_only:
        query = query.where(UserNotification.read_at.is_(None))
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    unread = db.execute(select(func.count()).where(mine, UserNotification.read_at.is_(None))).scalar_one()
    items = db.execute(
        query.order_by(UserNotification.created_at.desc()).limit(min(max(limit, 1), 100)).offset(max(offset, 0))
    ).scalars()
    return NotificationPage(items=[NotificationOut.model_validate(i) for i in items], total=total, unread=unread)


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> UnreadCount:
    count = db.execute(
        select(func.count()).where(UserNotification.user_id == user.id, UserNotification.read_at.is_(None))
    ).scalar_one()
    return UnreadCount(unread=count)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(notification_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    row = db.get(UserNotification, notification_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    if row.read_at is None:
        row.read_at = utcnow()
        db.commit()


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    db.execute(
        update(UserNotification)
        .where(UserNotification.user_id == user.id, UserNotification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.commit()
