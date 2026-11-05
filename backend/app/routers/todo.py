"""我的待办:把散落在各模块里"与我有关且需要我动手"的事项聚合成一个工作台。

只读聚合,不产生新数据;每条待办都带上前端的真实路由参数,点击即可跳转处理。
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_project_ids, get_current_user
from ..models import (
    Defect,
    Notification,
    Project,
    ProjectRole,
    TestCase,
    TestPlan,
    TestRun,
    User,
)
from ..scope import plan_case_ids

router = APIRouter(prefix="/api/todo", tags=["我的待办"], dependencies=[Depends(get_current_user)])

LIST_LIMIT = 50  # 每类待办最多返回条数,总数另用 count 查询给出
PLAN_LIMIT = 20  # 最多聚合多少个进行中批次,避免负责人批次过多时逐批统计拖慢接口
OPEN_DEFECT_STATUS = ("新建", "处理中", "重新打开")
STAGE_FIELDS = {
    "SIT": ("sit_start", "sit_end"),
    "UAT": ("uat_start", "uat_end"),
    "PRE": ("pre_start", "pre_end"),
}


def _fmt(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def _total(db: Session, col, *conds) -> int:
    return db.execute(select(func.count(col)).where(*conds)).scalar() or 0


def _latest_status(db: Session, plan_id: int, stage: str) -> dict[int, str]:
    rows = db.execute(
        select(TestRun.testcase_id, TestRun.status)
        .where(TestRun.plan_id == plan_id, TestRun.stage == stage)
        .order_by(TestRun.id.desc())
    ).all()
    latest: dict[int, str] = {}
    for cid, status in rows:
        latest.setdefault(cid, status)
    return latest


@router.get("/summary")
def todo_summary(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    pids = accessible_project_ids(db, current)  # None 表示 admin,全部可见

    def scope(model):
        return [] if pids is None else [model.project_id.in_(pids)]

    # ---- 待我评审的用例 ----
    review_conds = [TestCase.reviewer_id == current.id, TestCase.review_status == "评审中"] + scope(TestCase)
    review_cases = [
        {
            "id": tc.id,
            "title": tc.title,
            "project_id": tc.project_id,
            "project_name": pname,
            "priority": tc.priority,
            "submitted_at": _fmt(tc.updated_at),
            "link": f"/testcases?project_id={tc.project_id}&focus={tc.id}",
        }
        for tc, pname in db.execute(
            select(TestCase, Project.name)
            .join(Project, Project.id == TestCase.project_id)
            .where(*review_conds)
            .order_by(TestCase.updated_at.desc())
            .limit(LIST_LIMIT)
        ).all()
    ]

    # ---- 被驳回、需要我改完重新提交的用例 ----
    reject_conds = [TestCase.created_by == current.id, TestCase.review_status == "已驳回"] + scope(TestCase)
    rejected_cases = [
        {
            "id": tc.id,
            "title": tc.title,
            "project_id": tc.project_id,
            "project_name": pname,
            "priority": tc.priority,
            "comment": (tc.review_comment or "")[:200],
            "link": f"/testcases?project_id={tc.project_id}&focus={tc.id}",
        }
        for tc, pname in db.execute(
            select(TestCase, Project.name)
            .join(Project, Project.id == TestCase.project_id)
            .where(*reject_conds)
            .order_by(TestCase.updated_at.desc())
            .limit(LIST_LIMIT)
        ).all()
    ]

    # ---- 指派给我、尚未修复的缺陷 ----
    assign_conds = [Defect.assignee_id == current.id, Defect.status.in_(OPEN_DEFECT_STATUS)] + scope(Defect)
    my_defects = [
        {
            "id": d.id,
            "title": d.title,
            "project_id": d.project_id,
            "project_name": pname,
            "severity": d.severity,
            "priority": d.priority,
            "status": d.status,
            "updated_at": _fmt(d.updated_at),
            "link": f"/defects?focus={d.id}",
        }
        for d, pname in db.execute(
            select(Defect, Project.name)
            .join(Project, Project.id == Defect.project_id)
            .where(*assign_conds)
            .order_by(Defect.updated_at.desc())
            .limit(LIST_LIMIT)
        ).all()
    ]

    # ---- 我报的缺陷已修复,等着我验证 ----
    verify_conds = [Defect.reporter_id == current.id, Defect.status == "已修复"] + scope(Defect)
    verify_defects = [
        {
            "id": d.id,
            "title": d.title,
            "project_id": d.project_id,
            "project_name": pname,
            "severity": d.severity,
            "resolved_at": _fmt(d.resolved_at),
            "link": f"/defects?focus={d.id}",
        }
        for d, pname in db.execute(
            select(Defect, Project.name)
            .join(Project, Project.id == Defect.project_id)
            .where(*verify_conds)
            .order_by(Defect.resolved_at.desc())
            .limit(LIST_LIMIT)
        ).all()
    ]

    # ---- 我负责的批次(创建人,或项目上是测试负责人/项目经理)及其当前阶段待执行用例 ----
    lead_pids = select(ProjectRole.project_id).where(
        ProjectRole.user_id == current.id, ProjectRole.role.in_(("manager", "test_lead"))
    )
    plan_conds = [TestPlan.status == "进行中"] + ([] if pids is None else [TestPlan.project_id.in_(pids)])
    plans = list(
        db.execute(
            select(TestPlan)
            .where(*plan_conds, or_(TestPlan.created_by == current.id, TestPlan.project_id.in_(lead_pids)))
            .order_by(TestPlan.id.desc())
            .limit(PLAN_LIMIT)
        ).scalars()
    )
    my_plans: list[dict] = []
    pending_cases: list[dict] = []
    pending_total = 0
    today = datetime.now().date()
    for plan in plans:
        stage = plan.current_stage if plan.current_stage in STAGE_FIELDS else "SIT"
        end_at = getattr(plan, STAGE_FIELDS[stage][1])
        remain_days = (end_at.date() - today).days if end_at else None
        case_ids = plan_case_ids(db, plan)
        latest = _latest_status(db, plan.id, stage)
        plan_pending = [cid for cid in case_ids if cid not in latest]
        pending_total += len(plan_pending)
        failed = sum(1 for cid in case_ids if latest.get(cid) == "失败")
        project_name = db.get(Project, plan.project_id).name
        my_plans.append(
            {
                "id": plan.id,
                "project_id": plan.project_id,
                "project_name": project_name,
                "version": plan.version,
                "current_stage": stage,
                "stage_end": _fmt(end_at),
                "remain_days": remain_days,
                "overdue": remain_days is not None and remain_days < 0,
                "total": len(case_ids),
                "pending": len(plan_pending),
                "failed": failed,
                "link": f"/plans?project_id={plan.project_id}&focus={plan.id}&stage={stage}",
            }
        )
        if plan_pending:
            rows = db.execute(
                select(TestCase)
                .where(TestCase.id.in_(plan_pending[:LIST_LIMIT]))
                .order_by(TestCase.priority, TestCase.id)
            ).scalars()
            for tc in rows:
                pending_cases.append(
                    {
                        "id": tc.id,
                        "title": tc.title,
                        "project_id": tc.project_id,
                        "project_name": project_name,
                        "plan_id": plan.id,
                        "plan_version": plan.version,
                        "stage": stage,
                        "priority": tc.priority,
                        "link": f"/plans?project_id={plan.project_id}&focus={plan.id}&stage={stage}",
                    }
                )
    pending_cases.sort(key=lambda c: (c["priority"], c["plan_id"]))
    pending_cases = pending_cases[:LIST_LIMIT]

    unread_count = db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current.id, Notification.is_read == False  # noqa: E712
        )
    ).scalar() or 0
    counts = {
        "review_cases": _total(db, TestCase.id, *review_conds),
        "rejected_cases": _total(db, TestCase.id, *reject_conds),
        "my_defects": _total(db, Defect.id, *assign_conds),
        "verify_defects": _total(db, Defect.id, *verify_conds),
        "pending_cases": pending_total,
        "my_plans": len(my_plans),
    }
    return {
        "review_cases": review_cases,
        "rejected_cases": rejected_cases,
        "my_defects": my_defects,
        "verify_defects": verify_defects,
        "my_plans": my_plans,
        "pending_cases": pending_cases,
        "unread_notifications": unread_count,
        "counts": counts,
        "total": sum(counts[k] for k in (
            "review_cases", "rejected_cases", "my_defects", "verify_defects", "pending_cases"
        )),
        "plan_scanned": len(plans) == PLAN_LIMIT,
    }
