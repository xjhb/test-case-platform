from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Notification, User
from ..schemas import NotificationMarkRead, NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["通知"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    is_read: bool | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    q = select(Notification).where(Notification.user_id == current.id)
    if is_read is not None:
        q = q.where(Notification.is_read == is_read)
    items = list(db.execute(q.order_by(Notification.id.desc()).offset((page - 1) * size).limit(size)).scalars())
    return [
        NotificationOut(
            id=n.id, user_id=n.user_id, type=n.type, title=n.title,
            content=n.content, link=n.link, is_read=n.is_read, created_at=n.created_at,
        )
        for n in items
    ]


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    count = db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current.id,
            Notification.is_read == False,
        )
    ).scalar() or 0
    return {"count": count}


@router.post("/mark-read")
def mark_read(
    body: NotificationMarkRead,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if body.ids:
        q = select(Notification).where(
            Notification.id.in_(body.ids),
            Notification.user_id == current.id,
        )
        notifications = list(db.execute(q).scalars())
        for n in notifications:
            n.is_read = True
        db.commit()
        return {"detail": f"已标记 {len(notifications)} 条通知为已读"}
    else:
        q = select(Notification).where(
            Notification.user_id == current.id,
            Notification.is_read == False,
        )
        notifications = list(db.execute(q).scalars())
        for n in notifications:
            n.is_read = True
        db.commit()
        return {"detail": f"已标记全部 {len(notifications)} 条通知为已读"}


@router.delete("/{notification_id}")
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    n = db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current.id,
        )
    ).scalar_one_or_none()
    if not n:
        raise HTTPException(404, "通知不存在")
    db.delete(n)
    db.commit()
    return {"detail": "删除成功"}
