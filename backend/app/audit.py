"""操作日志防篡改:哈希链写入、完整性校验与按日锚定。

每条日志的 row_hash = SHA-256(密钥盐 + 前一条的 row_hash + 本条内容),
串成一条链;改动任意历史字段、删除或插入记录都会让后继的 prev_hash 对不上。
盐取自配置里的审计密钥(未单独配置则复用 JWT 签名密钥),它不进仓库,
只有数据库写权限的人无法整链重算。
"""

import hashlib

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .models import AuditChainState, OperationLog

GENESIS = "0" * 64
MAX_ISSUES = 50  # 明细只回前 50 条,整链被改时不至于把响应撑爆


def secret() -> str:
    return settings.audit_secret or settings.secret_key


def secret_source() -> str:
    """盐的来源,配置里没单独设审计密钥时会复用 JWT 签名密钥,前端据此提示风险"""
    return "audit_secret" if settings.audit_secret else "secret_key"


def canonical(log: OperationLog) -> str:
    """参与哈希的内容,字段顺序与分隔符固定。

    不含 user_id: 删除用户时外键会把历史日志的 user_id 置空,那是正常级联,
    不该被判成篡改;身份口径用冗余的 username。
    """
    ts = log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else ""
    return "|".join([
        str(log.id), log.username or "", log.action or "", log.target or "",
        log.detail or "", log.ip or "", ts,
    ])


def row_hash(prev_hash: str, log: OperationLog) -> str:
    h = hashlib.sha256()
    h.update(secret().encode("utf-8"))
    h.update((prev_hash or GENESIS).encode("utf-8"))
    h.update(canonical(log).encode("utf-8"))
    return h.hexdigest()


def get_state(db: Session, create: bool = True) -> AuditChainState | None:
    """取链头并加行锁;并发首插会撞主键,回滚到保存点后重读即可。"""
    def _locked():
        return db.execute(
            select(AuditChainState).where(AuditChainState.id == 1).with_for_update()
        ).scalars().first()

    state = _locked()
    if state is None and create:
        db.add(AuditChainState(id=1, last_log_id=0, head_hash=GENESIS, log_count=0))
        try:
            with db.begin_nested():
                db.flush()
        except Exception:
            pass
        state = _locked()
    return state


def seal(db: Session, log: OperationLog) -> OperationLog:
    """把日志挂到链尾:锁定链头 -> 落库取到 id -> 计算 row_hash -> 更新链头。

    只 flush 不 commit,让主业务与日志同事务成功或回滚。
    """
    state = get_state(db)
    log.prev_hash = state.head_hash or GENESIS
    db.add(log)
    db.flush()
    log.row_hash = row_hash(log.prev_hash, log)
    state.head_hash = log.row_hash
    state.last_log_id = log.id
    state.log_count = (state.log_count or 0) + 1
    db.flush()
    return log


def peek_state(db: Session) -> AuditChainState | None:
    """只读链头,不加行锁(校验接口不该挡住日志写入)"""
    return db.execute(select(AuditChainState).where(AuditChainState.id == 1)).scalars().first()


def _predecessor_hash(db: Session, first_id: int) -> str:
    row = db.execute(
        select(OperationLog)
        .where(OperationLog.id < first_id)
        .order_by(OperationLog.id.desc())
        .limit(1)
    ).scalars().first()
    return (row.row_hash or GENESIS) if row else GENESIS


def verify(db: Session, from_id: int | None = None, to_id: int | None = None,
           limit: int = 200000) -> dict:
    """按 id 升序重算链,逐条比对存储的 prev_hash / row_hash。"""
    q = select(OperationLog).order_by(OperationLog.id).limit(limit)
    if from_id:
        q = q.where(OperationLog.id >= from_id)
    if to_id:
        q = q.where(OperationLog.id <= to_id)
    rows = list(db.execute(q).scalars())
    # 链头在读完日志之后才取:并发追加会让链头比快照更新,那种情况不能算成篡改
    state = peek_state(db)

    issues: list[dict] = []
    prev = _predecessor_hash(db, rows[0].id) if rows else GENESIS
    for r in rows:
        recomputed = row_hash(prev, r)
        if not r.row_hash or not r.prev_hash:
            _add_issue(issues, r.id, "未入链", "该行还没有哈希,无法证明未被改动")
        elif r.prev_hash != prev:
            _add_issue(issues, r.id, "链断裂",
                       "前序哈希对不上:该位置之前的记录被删除、插入或重排")
        elif r.row_hash != recomputed:
            _add_issue(issues, r.id, "内容被篡改",
                       "按当前字段重算的哈希与存储值不一致,内容或时间被改过")
        # 未入链的行没有可信哈希,后续比对继续用它自己的存储值或重算值
        prev = r.row_hash or recomputed

    last_id = rows[-1].id if rows else 0
    if state and rows and to_id is None and len(rows) < limit:
        if state.last_log_id == last_id and state.head_hash != rows[-1].row_hash:
            _add_issue(issues, last_id, "链头不符",
                       "链头记录的最后哈希与末条日志不一致:末尾记录被删改,或写入时没更新链头")
        elif state.last_log_id < last_id:
            _add_issue(issues, last_id, "链头不符",
                       "存在比链头更新的日志:该记录绕过了正常写入流程被插入")

    return {
        "checked": len(rows),
        "ok": not issues,
        "from_id": rows[0].id if rows else None,
        "to_id": rows[-1].id if rows else None,
        "head_hash": state.head_hash if state else GENESIS,
        "log_count": state.log_count if state else 0,
        "issues": issues,
        "truncated": len(issues) >= MAX_ISSUES,
        # 未单配审计密钥时用的是 JWT 密钥,轮换 JWT 密钥会让整链校验失败
        "salt_source": secret_source(),
    }


def _add_issue(issues: list[dict], log_id: int, kind: str, reason: str) -> None:
    if len(issues) < MAX_ISSUES:
        issues.append({"id": log_id, "kind": kind, "reason": reason})


def anchor(db: Session, day: str) -> dict:
    """按自然日聚合一个锚定哈希,对外存证只需比对这一个值。"""
    rows = list(db.execute(
        select(OperationLog.id, OperationLog.row_hash)
        .where(func.date(OperationLog.created_at) == day)
        .order_by(OperationLog.id)
    ).all())
    h = hashlib.sha256()
    for _id, rh in rows:
        h.update((rh or "").encode("utf-8"))
    return {
        "date": day,
        "count": len(rows),
        "first_id": rows[0][0] if rows else None,
        "last_id": rows[-1][0] if rows else None,
        "anchor": h.hexdigest() if rows else "",
    }


def backfill(db: Session) -> int:
    """给尚未入链的历史日志补哈希,返回补写条数。

    只能保证补写之后的可验证性:回填前就已被删改的历史记录无从追溯。
    """
    rows = list(db.execute(
        select(OperationLog)
        .where(or_(OperationLog.row_hash.is_(None), OperationLog.row_hash == ""))
        .order_by(OperationLog.id)
    ).scalars())
    if not rows:
        return 0
    state = get_state(db)
    prev = state.head_hash or GENESIS
    if rows[0].id <= state.last_log_id:
        # 链头比这批起点新,说明是从中间补:按前一条的存储哈希接上
        prev = _predecessor_hash(db, rows[0].id)
    n = 0
    for r in rows:
        r.prev_hash = prev
        r.row_hash = row_hash(prev, r)
        prev = r.row_hash
        n += 1
    state.head_hash = prev
    state.last_log_id = rows[-1].id
    state.log_count = (state.log_count or 0) + n
    db.commit()
    return n
