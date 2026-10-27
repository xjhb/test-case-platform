from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_project_ids, get_current_user, require_project_access
from ..logger import log_op
from ..models import Defect, Notification, Project, TestCase, TestPlan, User
from ..schemas import DefectCreate, DefectOut, DefectUpdate

router = APIRouter(prefix="/api/defects", tags=["缺陷管理"], dependencies=[Depends(get_current_user)])

VALID_SEVERITY = {"致命", "严重", "一般", "提示"}
VALID_PRIORITY = {"P0", "P1", "P2", "P3"}
VALID_STATUS = {"新建", "处理中", "已修复", "已验证", "关闭", "重新打开"}


def _send_notification(db: Session, user_id: int, ntype: str, title: str, content: str, link: str):
    n = Notification(user_id=user_id, type=ntype, title=title, content=content, link=link)
    db.add(n)


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

    total = db.execute(select(func.count(Defect.id)).where(q.whereclause)).scalar() or 0
    items = list(db.execute(q.order_by(Defect.id.desc()).offset((page - 1) * size).limit(size)).scalars())

    result = []
    for d in items:
        reporter = db.get(User, d.reporter_id)
        assignee = db.get(User, d.assignee_id) if d.assignee_id else None
        out = DefectOut(
            id=d.id,
            title=d.title,
            description=d.description,
            severity=d.severity,
            priority=d.priority,
            status=d.status,
            testcase_id=d.testcase_id,
            plan_id=d.plan_id,
            project_id=d.project_id,
            reporter_id=d.reporter_id,
            reporter_name=reporter.display_name if reporter else "",
            assignee_id=d.assignee_id,
            assignee_name=assignee.display_name if assignee else "",
            created_at=d.created_at,
            updated_at=d.updated_at,
            resolved_at=d.resolved_at,
            closed_at=d.closed_at,
        )
        result.append(out)
    return {"total": total, "page": page, "size": size, "items": result}


@router.post("", response_model=DefectOut)
def create_defect(
    body: DefectCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_project_access(body.project_id, db, current)
    if body.severity not in VALID_SEVERITY:
        raise HTTPException(400, f"严重程度只能是: {', '.join(VALID_SEVERITY)}")
    if body.priority not in VALID_PRIORITY:
        raise HTTPException(400, f"优先级只能是: {', '.join(VALID_PRIORITY)}")

    d = Defect(
        title=body.title,
        description=body.description,
        severity=body.severity,
        priority=body.priority,
        status="新建",
        testcase_id=body.testcase_id,
        plan_id=body.plan_id,
        project_id=body.project_id,
        reporter_id=current.id,
        assignee_id=body.assignee_id,
    )
    db.add(d)
    db.commit()
    db.refresh(d)

    log_op(db, current, "创建", target=f"缺陷#{d.id}", detail=d.title)

    if d.assignee_id and d.assignee_id != current.id:
        _send_notification(
            db, d.assignee_id, "defect_assigned",
            f"你被指派了一个缺陷: {d.title}",
            f"严重程度: {d.severity}, 优先级: {d.priority}",
            f"#/defects/{d.id}",
        )
        db.commit()

    reporter = db.get(User, d.reporter_id)
    assignee = db.get(User, d.assignee_id) if d.assignee_id else None
    return DefectOut(
        id=d.id, title=d.title, description=d.description,
        severity=d.severity, priority=d.priority, status=d.status,
        testcase_id=d.testcase_id, plan_id=d.plan_id, project_id=d.project_id,
        reporter_id=d.reporter_id, reporter_name=reporter.display_name if reporter else "",
        assignee_id=d.assignee_id, assignee_name=assignee.display_name if assignee else "",
        created_at=d.created_at, updated_at=d.updated_at,
        resolved_at=d.resolved_at, closed_at=d.closed_at,
    )


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
    reporter = db.get(User, d.reporter_id)
    assignee = db.get(User, d.assignee_id) if d.assignee_id else None
    return DefectOut(
        id=d.id, title=d.title, description=d.description,
        severity=d.severity, priority=d.priority, status=d.status,
        testcase_id=d.testcase_id, plan_id=d.plan_id, project_id=d.project_id,
        reporter_id=d.reporter_id, reporter_name=reporter.display_name if reporter else "",
        assignee_id=d.assignee_id, assignee_name=assignee.display_name if assignee else "",
        created_at=d.created_at, updated_at=d.updated_at,
        resolved_at=d.resolved_at, closed_at=d.closed_at,
    )


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
    if body.title is not None:
        d.title = body.title
        changes.append("标题")
    if body.description is not None:
        d.description = body.description
    if body.severity is not None:
        if body.severity not in VALID_SEVERITY:
            raise HTTPException(400, f"严重程度只能是: {', '.join(VALID_SEVERITY)}")
        d.severity = body.severity
        changes.append("严重程度")
    if body.priority is not None:
        if body.priority not in VALID_PRIORITY:
            raise HTTPException(400, f"优先级只能是: {', '.join(VALID_PRIORITY)}")
        d.priority = body.priority
        changes.append("优先级")
    if body.status is not None:
        if body.status not in VALID_STATUS:
            raise HTTPException(400, f"状态只能是: {', '.join(VALID_STATUS)}")
        old_status = d.status
        d.status = body.status
        changes.append(f"状态({old_status}→{body.status})")
        if body.status == "已修复" and not d.resolved_at:
            d.resolved_at = datetime.now()
        if body.status == "关闭" and not d.closed_at:
            d.closed_at = datetime.now()
    if body.assignee_id is not None:
        old_assignee = d.assignee_id
        d.assignee_id = body.assignee_id
        if old_assignee != body.assignee_id and body.assignee_id and body.assignee_id != current.id:
            _send_notification(
                db, body.assignee_id, "defect_assigned",
                f"你被指派了一个缺陷: {d.title}",
                f"严重程度: {d.severity}, 优先级: {d.priority}",
                f"#/defects/{d.id}",
            )

    log_op(db, current, "编辑", target=f"缺陷#{d.id}", detail="; ".join(changes) if changes else "无变更")
    db.commit()
    db.refresh(d)

    reporter = db.get(User, d.reporter_id)
    assignee = db.get(User, d.assignee_id) if d.assignee_id else None
    return DefectOut(
        id=d.id, title=d.title, description=d.description,
        severity=d.severity, priority=d.priority, status=d.status,
        testcase_id=d.testcase_id, plan_id=d.plan_id, project_id=d.project_id,
        reporter_id=d.reporter_id, reporter_name=reporter.display_name if reporter else "",
        assignee_id=d.assignee_id, assignee_name=assignee.display_name if assignee else "",
        created_at=d.created_at, updated_at=d.updated_at,
        resolved_at=d.resolved_at, closed_at=d.closed_at,
    )


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
    db.delete(d)
    log_op(db, current, "删除", target=f"缺陷#{defect_id}", detail=title)
    db.commit()
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
