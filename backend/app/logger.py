"""操作日志辅助函数:在各路由的关键操作里调用 log_op 记录"""
from sqlalchemy.orm import Session

from .models import OperationLog, User


def log_op(
    db: Session,
    user: User | None,
    action: str,
    target: str = "",
    detail: str = "",
    ip: str = "",
) -> None:
    """记录一条操作日志。user 可为 None(如登录失败时)。"""
    try:
        log = OperationLog(
            user_id=user.id if user else None,
            username=user.username if user else "",
            action=action,
            target=target,
            detail=detail,
            ip=ip or "",
        )
        db.add(log)
        db.commit()
    except Exception:
        # 日志记录失败不应影响主业务,回滚后忽略
        db.rollback()
