from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..logger import log_op
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


@router.get("/integrity")
def integrity(
    from_id: int | None = None,
    to_id: int | None = None,
    db: Session = Depends(get_db),
):
    """只读校验哈希链;不写日志,可随时轮询。传 from/to 可只校验一段区间"""
    return audit.verify(db, from_id=from_id, to_id=to_id)


@router.post("/integrity/verify")
def integrity_verify(
    from_id: int | None = None,
    to_id: int | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    """留痕校验:结果同上,但这次校验本身会写进日志链"""
    result = audit.verify(db, from_id=from_id, to_id=to_id)
    log_op(
        db, current, "校验",
        target=f"日志#1-{result['to_id'] or 0}",
        detail=(f"完整性校验 {'通过' if result['ok'] else '异常'}: "
                f"共 {result['checked']} 条, 异常 {len(result['issues'])} 条, "
                f"链头 {result['head_hash'][:16]}"),
    )
    return result


@router.get("/state")
def chain_state(db: Session = Depends(get_db)):
    """链头概况:前端顶部展示,数量与末条哈希对不上就说明日志被动过"""
    state = audit.peek_state(db)
    return {
        "log_count": state.log_count if state else 0,
        "last_log_id": state.last_log_id if state else 0,
        "head_hash": state.head_hash if state else audit.GENESIS,
        "updated_at": state.updated_at.isoformat(sep=" ", timespec="seconds") if state and state.updated_at else "",
        "salt_source": audit.secret_source(),
    }


@router.get("/anchor")
def chain_anchor(date: str = Query(min_length=10, max_length=10), db: Session = Depends(get_db)):
    """按自然日出锚定哈希,便于对外存证或周报比对"""
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    return audit.anchor(db, day.isoformat())
