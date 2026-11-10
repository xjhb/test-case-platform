import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from urllib.parse import quote
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dictionaries import check_400, urgent_labels
from ..deps import accessible_project_ids, get_current_user, require_project_access
from ..logger import log_op
from ..models import Defect, DefectAttachment, Project, TestCase, TestPlan, TestRun, User
from ..notify import emit
from ..schemas import DefectAttachmentOut, DefectCreate, DefectOut, DefectUpdate

router = APIRouter(prefix="/api/defects", tags=["缺陷管理"], dependencies=[Depends(get_current_user)])

# 缺陷状态是状态机的键,保持固定;严重程度与优先级走数据字典,可按项目配置
VALID_STATUS = {"新建", "处理中", "已修复", "已验证", "关闭", "重新打开"}

# 缺陷状态机:与主流平台一致,修复后必须由提单人验证才能关闭
STATUS_TRANSITIONS: dict[str, list[str]] = {
    "新建": ["处理中", "关闭"],
    "处理中": ["已修复", "关闭"],
    "已修复": ["已验证", "重新打开"],
    "已验证": ["关闭", "重新打开"],
    "关闭": ["重新打开"],
    "重新打开": ["处理中", "已修复", "关闭"],
}

ATTACH_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "defects")
ATTACH_MAX_SIZE = 20 * 1024 * 1024  # 20MB
ATTACH_EXT_WHITELIST = {
    "png", "jpg", "jpeg", "gif", "webp",           # 截图
    "txt", "log", "csv", "json", "xml", "har",     # 日志
    "pdf", "doc", "docx", "xls", "xlsx", "zip", "rar", "7z",  # 文档与打包
}
IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}


def _attachment_out(db: Session, a: DefectAttachment, current: User) -> DefectAttachmentOut:
    uploader = db.get(User, a.uploaded_by) if a.uploaded_by else None
    return DefectAttachmentOut(
        id=a.id,
        defect_id=a.defect_id,
        original_name=a.original_name,
        content_type=a.content_type,
        size=a.size,
        uploaded_by=a.uploaded_by,
        uploaded_by_name=(uploader.display_name or uploader.username) if uploader else "",
        uploaded_at=a.uploaded_at,
        url=f"/uploads/defects/{a.stored_name}",
        # 前端拿不到当前用户ID(登录响应只存 role/display_name),删除权限由后端判定
        can_delete=a.uploaded_by == current.id or current.role == "admin",
    )


def _validate_status_change(d: Defect, new_status: str, operator: User) -> None:
    """状态流转校验:非法跳转直接拒绝,管理员可强制流转"""
    if new_status == d.status:
        return
    if operator.role == "admin":
        return
    allowed = STATUS_TRANSITIONS.get(d.status, [])
    if new_status not in allowed:
        raise HTTPException(
            400,
            f"缺陷状态不能从 {d.status} 直接流转到 {new_status},当前可选: {', '.join(allowed) or '无'}",
        )


def _apply_status_timestamps(d: Defect, old_status: str, new_status: str) -> None:
    """按状态维护修复/关闭时间;回退或重新打开时清掉旧时间"""
    if new_status == old_status:
        return
    if new_status == "已修复":
        d.resolved_at = datetime.now()
    elif new_status == "关闭":
        d.closed_at = datetime.now()
        if old_status != "已修复":
            # 未经修复就关闭(拒绝/重复),同样记为已处理时间
            d.resolved_at = d.resolved_at or datetime.now()
    elif new_status in ("重新打开", "处理中"):
        d.resolved_at = None
        d.closed_at = None


def _to_out(db: Session, d: Defect, attachment_count: int | None = None) -> DefectOut:
    """组装缺陷响应;附件数不传时实时查询"""
    reporter = db.get(User, d.reporter_id)
    assignee = db.get(User, d.assignee_id) if d.assignee_id else None
    if attachment_count is None:
        attachment_count = db.execute(
            select(func.count(DefectAttachment.id)).where(DefectAttachment.defect_id == d.id)
        ).scalar() or 0
    return DefectOut(
        id=d.id, title=d.title, description=d.description,
        severity=d.severity, priority=d.priority, status=d.status,
        testcase_id=d.testcase_id, plan_id=d.plan_id, project_id=d.project_id,
        reporter_id=d.reporter_id, reporter_name=reporter.display_name if reporter else "",
        assignee_id=d.assignee_id, assignee_name=assignee.display_name if assignee else "",
        created_at=d.created_at, updated_at=d.updated_at,
        resolved_at=d.resolved_at, closed_at=d.closed_at,
        attachment_count=attachment_count,
    )


def _is_urgent(db: Session, d: Defect) -> bool:
    """紧急口径由字典项的"计入紧急"标记决定,不再写死值串"""
    return (d.severity in urgent_labels(db, "defect_severity", d.project_id)
            or d.priority in urgent_labels(db, "defect_priority", d.project_id))



def _notify_assignee(db: Session, d: Defect, operator: User, action: str) -> None:
    if not d.assignee_id or d.assignee_id == operator.id:
        return
    who = operator.display_name or operator.username
    emit(
        db, [d.assignee_id], "defect_assigned",
        f"{action}: {d.title}",
        f"严重程度: {d.severity}, 优先级: {d.priority}, 操作人: {who}",
        f"/defects?focus={d.id}",
        broadcast=_is_urgent(db, d),
    )


@router.get("")
def list_defects(
    project_id: int | None = None,
    plan_id: int | None = None,
    testcase_id: int | None = None,
    status: str | None = None,
    severity: str | None = None,
    priority: str | None = None,
    assignee_id: int | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    accessible = accessible_project_ids(db, current)
    q = select(Defect)
    if project_id is not None:
        require_project_access(project_id, db, current)
        q = q.where(Defect.project_id == project_id)
    elif accessible is not None:
        if not accessible:
            return []
        q = q.where(Defect.project_id.in_(accessible))
    if plan_id is not None:
        q = q.where(Defect.plan_id == plan_id)
    if testcase_id is not None:
        q = q.where(Defect.testcase_id == testcase_id)
    if status:
        q = q.where(Defect.status == status)
    if severity:
        q = q.where(Defect.severity == severity)
    if priority:
        q = q.where(Defect.priority == priority)
    if assignee_id is not None:
        q = q.where(Defect.assignee_id == assignee_id)
    if keyword:
        like = f"%{keyword}%"
        q = q.where(Defect.title.ilike(like) | Defect.description.ilike(like))

    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    items = list(db.execute(q.order_by(Defect.id.desc()).offset((page - 1) * size).limit(size)).scalars())

    counts = {}
    if items:
        rows = db.execute(
            select(DefectAttachment.defect_id, func.count(DefectAttachment.id))
            .where(DefectAttachment.defect_id.in_([d.id for d in items]))
            .group_by(DefectAttachment.defect_id)
        ).all()
        counts = {r[0]: r[1] for r in rows}
    return {"total": total, "page": page, "size": size, "items": [_to_out(db, d, counts.get(d.id, 0)) for d in items]}


@router.get("/status-flow")
def get_status_flow():
    """返回缺陷状态机流转表,前端按当前状态渲染可用操作按钮"""
    return {"statuses": list(VALID_STATUS), "transitions": STATUS_TRANSITIONS}


@router.post("", response_model=DefectOut)
def create_defect(
    body: DefectCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_project_access(body.project_id, db, current)
    check_400(db, "defect_severity", body.severity, body.project_id)
    check_400(db, "defect_priority", body.priority, body.project_id)

    d = Defect(
        title=body.title,
        description=body.description,
        severity=body.severity,
        priority=body.priority,
        status="新建",
        testcase_id=body.testcase_id,
        plan_id=body.plan_id,
        run_id=body.run_id,
        project_id=body.project_id,
        reporter_id=current.id,
        assignee_id=body.assignee_id,
    )
    db.add(d)
    db.commit()
    db.refresh(d)

    log_op(db, current, "创建", target=f"缺陷#{d.id}", detail=d.title)
    _notify_assignee(db, d, current, "你被指派了一个缺陷")

    return _to_out(db, d)


@router.get("/{defect_id}", response_model=DefectOut)
def get_defect(
    defect_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    d = db.get(Defect, defect_id)
    if not d:
        raise HTTPException(404, "缺陷不存在")
    require_project_access(d.project_id, db, current)
    return _to_out(db, d)


@router.put("/{defect_id}", response_model=DefectOut)
def update_defect(
    defect_id: int,
    body: DefectUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    d = db.get(Defect, defect_id)
    if not d:
        raise HTTPException(404, "缺陷不存在")
    require_project_access(d.project_id, db, current)

    changes = []
    status_changed_to = None
    assignee_changed = False
    if body.title is not None:
        d.title = body.title
        changes.append("标题")
    if body.description is not None:
        d.description = body.description
    if body.severity is not None:
        check_400(db, "defect_severity", body.severity, d.project_id, current=d.severity)
        d.severity = body.severity
        changes.append("严重程度")
    if body.priority is not None:
        check_400(db, "defect_priority", body.priority, d.project_id, current=d.priority)
        d.priority = body.priority
        changes.append("优先级")
    if body.status is not None:
        if body.status not in VALID_STATUS:
            raise HTTPException(400, f"状态只能是: {', '.join(VALID_STATUS)}")
        old_status = d.status
        _validate_status_change(d, body.status, current)
        _apply_status_timestamps(d, old_status, body.status)
        d.status = body.status
        changes.append(f"状态({old_status}→{body.status})")
        if body.status != old_status:
            status_changed_to = body.status
    if body.assignee_id is not None:
        old_assignee = d.assignee_id
        d.assignee_id = body.assignee_id
        if old_assignee != body.assignee_id and body.assignee_id:
            assignee_changed = True

    log_op(db, current, "编辑", target=f"缺陷#{d.id}", detail="; ".join(changes) if changes else "无变更")
    db.commit()
    db.refresh(d)

    who = current.display_name or current.username
    if assignee_changed:
        _notify_assignee(db, d, current, "你被指派了一个缺陷")
    if status_changed_to == "已修复" and d.reporter_id != current.id:
        emit(
            db, [d.reporter_id], "defect_verify",
            f"缺陷已修复,请验证: {d.title}",
            f"处理人: {who}, 严重程度: {d.severity}, 优先级: {d.priority}",
            f"/defects?focus={d.id}",
            broadcast=_is_urgent(db, d),
        )
    elif status_changed_to == "重新打开" and d.assignee_id and d.assignee_id != current.id:
        emit(
            db, [d.assignee_id], "defect_verify",
            f"缺陷被重新打开: {d.title}",
            f"操作人: {who}, 原因: {d.description[:80] or '未填写'}",
            f"/defects?focus={d.id}",
            broadcast=_is_urgent(db, d),
        )

    return _to_out(db, d)


@router.delete("/{defect_id}")
def delete_defect(
    defect_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    d = db.get(Defect, defect_id)
    if not d:
        raise HTTPException(404, "缺陷不存在")
    require_project_access(d.project_id, db, current)
    if current.role != "admin":
        raise HTTPException(403, "仅管理员可删除缺陷")
    title = d.title
    # 附件行随缺陷级联删除,磁盘文件要一并清掉,否则留下孤儿文件
    stored = [a.stored_name for a in db.execute(
        select(DefectAttachment).where(DefectAttachment.defect_id == defect_id)
    ).scalars()]
    db.delete(d)
    log_op(db, current, "删除", target=f"缺陷#{defect_id}", detail=title)
    db.commit()
    for name in stored:
        path = os.path.join(ATTACH_DIR, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return {"detail": "删除成功"}


@router.get("/{defect_id}/attachments", response_model=list[DefectAttachmentOut])
def list_attachments(
    defect_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    d = db.get(Defect, defect_id)
    if not d:
        raise HTTPException(404, "缺陷不存在")
    require_project_access(d.project_id, db, current)
    rows = list(db.execute(
        select(DefectAttachment).where(DefectAttachment.defect_id == defect_id).order_by(DefectAttachment.id.desc())
    ).scalars())
    return [_attachment_out(db, a, current) for a in rows]


@router.post("/{defect_id}/attachments", response_model=DefectAttachmentOut)
async def upload_attachment(
    defect_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    d = db.get(Defect, defect_id)
    if not d:
        raise HTTPException(404, "缺陷不存在")
    require_project_access(d.project_id, db, current)

    original_name = os.path.basename(file.filename or "")
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if ext not in ATTACH_EXT_WHITELIST:
        raise HTTPException(400, f"不支持的附件类型 .{ext or '?'}，允许: {', '.join(sorted(ATTACH_EXT_WHITELIST))}")
    content = await file.read()
    if len(content) > ATTACH_MAX_SIZE:
        raise HTTPException(400, "附件大小不能超过 20MB")
    if not content:
        raise HTTPException(400, "附件内容为空")

    os.makedirs(ATTACH_DIR, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(ATTACH_DIR, stored_name), "wb") as f:
        f.write(content)

    a = DefectAttachment(
        defect_id=defect_id,
        stored_name=stored_name,
        original_name=original_name[:255],
        content_type=file.content_type or "",
        size=len(content),
        uploaded_by=current.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    log_op(db, current, "上传", target=f"缺陷#{defect_id}", detail=f"附件 {original_name}")
    return _attachment_out(db, a, current)


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    a = db.get(DefectAttachment, attachment_id)
    if not a:
        raise HTTPException(404, "附件不存在")
    d = db.get(Defect, a.defect_id)
    if not d:
        raise HTTPException(404, "附件所属缺陷不存在")
    require_project_access(d.project_id, db, current)
    path = os.path.join(ATTACH_DIR, a.stored_name)
    if not os.path.isfile(path):
        raise HTTPException(404, "附件文件已丢失,请重新上传")
    # 中文文件名按 RFC 5987 编码,避免各浏览器乱码
    ascii_name = quote(a.original_name).replace(" ", "_")
    return FileResponse(
        path,
        media_type=a.content_type or "application/octet-stream",
        filename=a.original_name,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(a.original_name)}"
            )
        },
    )


@router.delete("/attachments/{attachment_id}")
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    a = db.get(DefectAttachment, attachment_id)
    if not a:
        raise HTTPException(404, "附件不存在")
    d = db.get(Defect, a.defect_id)
    if not d:
        raise HTTPException(404, "附件所属缺陷不存在")
    require_project_access(d.project_id, db, current)
    if a.uploaded_by != current.id and current.role != "admin":
        raise HTTPException(403, "只能删除自己上传的附件")

    path = os.path.join(ATTACH_DIR, a.stored_name)
    defect_id = a.defect_id
    original_name = a.original_name
    db.delete(a)
    db.commit()
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            # 文件被占用时数据库记录已删除,磁盘残留由人工清理
            pass
    log_op(db, current, "删除", target=f"缺陷#{defect_id}", detail=f"附件 {original_name}")
    return {"detail": "删除成功"}


@router.get("/stats/summary")
def defect_stats(
    project_id: int | None = None,
    plan_id: int | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    accessible = accessible_project_ids(db, current)
    q = select(Defect)
    if project_id is not None:
        require_project_access(project_id, db, current)
        q = q.where(Defect.project_id == project_id)
    elif accessible is not None:
        if not accessible:
            return {"total": 0, "by_status": {}, "by_severity": {}, "by_priority": {}}
        q = q.where(Defect.project_id.in_(accessible))
    if plan_id is not None:
        q = q.where(Defect.plan_id == plan_id)

    defects = list(db.execute(q).scalars())
    total = len(defects)
    by_status = {}
    by_severity = {}
    by_priority = {}
    for d in defects:
        by_status[d.status] = by_status.get(d.status, 0) + 1
        by_severity[d.severity] = by_severity.get(d.severity, 0) + 1
        by_priority[d.priority] = by_priority.get(d.priority, 0) + 1

    return {
        "total": total,
        "by_status": by_status,
        "by_severity": by_severity,
        "by_priority": by_priority,
    }


@router.get("/{defect_id}/traceability")
def defect_traceability(
    defect_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取缺陷的完整追溯信息：关联的用例、执行记录、计划"""
    defect = db.get(Defect, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="缺陷不存在")
    require_project_access(defect.project_id, db, current)

    result = {
        "defect_id": defect_id,
        "defect_title": defect.title,
        "testcase": None,
        "run": None,
        "plan": None,
    }

    # 关联的测试用例
    if defect.testcase_id:
        tc = db.get(TestCase, defect.testcase_id)
        if tc:
            result["testcase"] = {
                "id": tc.id,
                "title": tc.title,
                "module": tc.module,
                "priority": tc.priority,
                "status": tc.status,
            }

    # 关联的执行记录
    if defect.run_id:
        run = db.get(TestRun, defect.run_id)
        if run:
            executor = db.get(User, run.executed_by)
            result["run"] = {
                "id": run.id,
                "status": run.status,
                "stage": run.stage,
                "remark": run.remark,
                "executed_at": run.executed_at.isoformat() if run.executed_at else None,
                "executed_by": executor.display_name or executor.username if executor else None,
            }

    # 关联的测试计划
    if defect.plan_id:
        plan = db.get(TestPlan, defect.plan_id)
        if plan:
            result["plan"] = {
                "id": plan.id,
                "version": plan.version,
                "current_stage": plan.current_stage,
                "status": plan.status,
            }

    return result
