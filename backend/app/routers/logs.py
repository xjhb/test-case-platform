from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import OperationLog, User
from ..schemas import OperationLogOut

router = APIRouter(prefix="/api/logs", tags=["操作日志"], dependencies=[Depends(require_admin)])


@router.get("")
def list_logs(
    action: str | None = None,
    username: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = select(OperationLog)
    if action:
        q = q.where(OperationLog.action == action)
    if username:
        q = q.where(OperationLog.username.like(f"%{username}%"))
    from sqlalchemy import func
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = list(
        db.execute(q.order_by(OperationLog.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [OperationLogOut.model_validate(r).model_dump(mode="json") for r in rows],
    }


@router.get("/actions")
def list_actions(db: Session = Depends(get_db)):
    """返回所有出现过的操作类型(供前端筛选用)"""
    from sqlalchemy import distinct
    rows = db.execute(select(distinct(OperationLog.action)).order_by(OperationLog.action)).all()
    return [r[0] for r in rows]
