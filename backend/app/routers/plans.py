from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_project_ids, get_current_user, require_project_access
from ..logger import log_op
from ..models import PlanTestCase, Project, SystemConfig, TestCase, TestPlan, TestRun, User
from ..schemas import PlanCasesPayload, StageAdvance, StageTimeUpdate, TestPlanCreate, TestPlanOut
from ..scope import has_scope, plan_case_ids

router = APIRouter(prefix="/api/plans", tags=["测试计划"], dependencies=[Depends(get_current_user)])

STAGE_ORDER = ["SIT", "UAT", "PRE"]


def _latest_status_map(db: Session, plan_id: int, stage: str) -> dict[int, str]:
    runs = list(
        db.execute(
            select(TestRun)
            .where(TestRun.plan_id == plan_id, TestRun.stage == stage)
            .order_by(TestRun.id.desc())
        ).scalars()
    )
    latest: dict[int, str] = {}
    for r in runs:
        if r.testcase_id not in latest:
            latest[r.testcase_id] = r.status
    return latest


def _fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else None


def _parse(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


def _get_stage_defaults(db: Session) -> dict:
    cfg = db.execute(select(SystemConfig).limit(1)).scalar_one_or_none()
    return {
        "sit": cfg.default_sit_days if cfg else 7,
        "uat": cfg.default_uat_days if cfg else 5,
        "pre": cfg.default_pre_days if cfg else 3,
    }


def _auto_set_stage_times(plan: TestPlan, db: Session):
    """根据默认天数自动设置三阶段时间"""
    defaults = _get_stage_defaults(db)
    now = datetime.now()
    plan.sit_start = now
    plan.sit_end = now + timedelta(days=defaults["sit"])
    plan.uat_start = plan.sit_end
    plan.uat_end = plan.uat_start + timedelta(days=defaults["uat"])
    plan.pre_start = plan.uat_end
    plan.pre_end = plan.pre_start + timedelta(days=defaults["pre"])


@router.get("")
def list_plans(project_id: int | None = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    accessible = accessible_project_ids(db, current)
    q = select(TestPlan)
    if project_id is not None:
        require_project_access(project_id, db, current)
        q = q.where(TestPlan.project_id == project_id)
    elif accessible is not None:
        if not accessible:
            return []
        q = q.where(TestPlan.project_id.in_(accessible))
    plans = list(db.execute(q.order_by(TestPlan.id.desc())).scalars())
    out = []
    for p in plans:
        ids = plan_case_ids(db, p)
        scoped = has_scope(db, p)
        latest = _latest_status_map(db, p.id, p.current_stage)
        passed = sum(1 for cid in ids if latest.get(cid) == "通过")
        executed = sum(1 for cid in ids if cid in latest)
        out.append({
            "id": p.id,
            "project_id": p.project_id,
            "version": p.version,
            "current_stage": p.current_stage,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "total_cases": len(ids),
            "passed_cases": passed,
            "executed_cases": executed,
            "scoped": scoped,
            "sit_start": _fmt(p.sit_start),
            "sit_end": _fmt(p.sit_end),
            "uat_start": _fmt(p.uat_start),
            "uat_end": _fmt(p.uat_end),
            "pre_start": _fmt(p.pre_start),
            "pre_end": _fmt(p.pre_end),
        })
    return out


@router.post("")
def create_plan(payload: TestPlanCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    project = db.get(Project, payload.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    require_project_access(payload.project_id, db, current)
    plan = TestPlan(
        project_id=payload.project_id,
        version=payload.version,
        current_stage="SIT",
        status="进行中",
        created_by=current.id,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    _auto_set_stage_times(plan, db)
    db.commit()
    db.refresh(plan)
    log_op(db, current, "创建", target=f"计划#{plan.id} {plan.version}", detail=f"项目#{payload.project_id}")
    return {
        "id": plan.id, "project_id": plan.project_id, "version": plan.version,
        "current_stage": plan.current_stage, "status": plan.status,
        "created_by": plan.created_by, "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "sit_start": _fmt(plan.sit_start), "sit_end": _fmt(plan.sit_end),
        "uat_start": _fmt(plan.uat_start), "uat_end": _fmt(plan.uat_end),
        "pre_start": _fmt(plan.pre_start), "pre_end": _fmt(plan.pre_end),
    }


@router.get("/{plan_id}/progress")
def progress(plan_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_project_access(plan.project_id, db, current)
    case_ids = plan_case_ids(db, plan)
    total = len(case_ids)
    stages = {}
    for stage in STAGE_ORDER:
        latest = _latest_status_map(db, plan_id, stage)
        passed = failed = blocked = pending = 0
        for cid in case_ids:
            st = latest.get(cid, "未执行")
            if st == "通过":
                passed += 1
            elif st == "失败":
                failed += 1
            elif st == "阻塞":
                blocked += 1
            else:
                pending += 1
        stages[stage] = {"total": total, "passed": passed, "failed": failed, "blocked": blocked, "pending": pending}
    current = plan.current_stage
    cur = stages[current]
    # 灵活模式：始终允许推进，不再强制要求 100% 通过
    can_advance = plan.status != "已完成"
    return {
        "plan_id": plan_id,
        "current_stage": current,
        "status": plan.status,
        "total": total,
        "stages": stages,
        "can_advance": can_advance,
    }


@router.post("/{plan_id}/advance")
def advance(plan_id: int, payload: StageAdvance | None = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """阶段推进：支持顺序推进或跳转到任意阶段"""
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_project_access(plan.project_id, db, current)
    if plan.status == "已完成":
        raise HTTPException(status_code=400, detail="计划已完成,无法推进")

    current_stage = plan.current_stage
    target_stage = payload.target_stage.upper() if payload and payload.target_stage else None

    # 确定目标阶段
    if target_stage:
        # 跳转到指定阶段
        if target_stage not in STAGE_ORDER:
            raise HTTPException(status_code=400, detail=f"阶段只能是 {'/'.join(STAGE_ORDER)}")
        if target_stage == current_stage:
            raise HTTPException(status_code=400, detail="目标阶段与当前阶段相同")
    else:
        # 顺序推进到下一阶段
        idx = STAGE_ORDER.index(current_stage)
        if idx == len(STAGE_ORDER) - 1:
            raise HTTPException(status_code=400, detail="已是最后阶段(PRE),无法继续推进")
        target_stage = STAGE_ORDER[idx + 1]

    # 检查目标阶段是否有效
    if STAGE_ORDER.index(target_stage) <= STAGE_ORDER.index(current_stage):
        raise HTTPException(status_code=400, detail="只能向前推进,不能回退")

    # 如果跳转到 PRE 或跳过中间阶段，标记计划为完成（如果目标是 PRE 之后）
    if target_stage == "PRE":
        # 推进到 PRE，不自动完成，让用户在 PRE 执行完后再手动完成
        plan.current_stage = target_stage
    else:
        plan.current_stage = target_stage

    db.commit()
    db.refresh(plan)
    log_op(db, current, "推进", target=f"计划#{plan.id} {plan.version}",
           detail=f"{current_stage} -> {plan.current_stage}")
    return {"id": plan.id, "current_stage": plan.current_stage, "status": plan.status}


@router.get("/{plan_id}/cases")
def get_plan_cases(plan_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """计划的用例圈选范围;scoped=False 表示尚未圈选,统计按项目全部用例"""
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_project_access(plan.project_id, db, current)
    scoped = has_scope(db, plan)
    ids = plan_case_ids(db, plan)
    rows = list(db.execute(select(TestCase).where(TestCase.id.in_(ids))).scalars()) if ids else []
    row_map = {c.id: c for c in rows}
    return {
        "plan_id": plan_id,
        "scoped": scoped,
        "case_ids": ids,
        "cases": [
            {"id": i, "title": row_map[i].title, "module": row_map[i].module, "priority": row_map[i].priority}
            for i in ids
            if i in row_map
        ],
    }


@router.post("/{plan_id}/cases")
def update_plan_cases(
    plan_id: int,
    payload: PlanCasesPayload,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """圈选/调整计划的用例范围。mode: replace 全量覆盖 / add 追加 / remove 移除 / all 纳入项目全部用例"""
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_project_access(plan.project_id, db, current)

    if payload.mode not in ("replace", "add", "remove", "all"):
        raise HTTPException(status_code=400, detail="mode 只能是 replace/add/remove/all")

    want = set(payload.testcase_ids)
    if want:
        valid = set(db.execute(select(TestCase.id).where(TestCase.id.in_(want), TestCase.project_id == plan.project_id)).scalars())
        bad = sorted(want - valid)
        if bad:
            raise HTTPException(status_code=400, detail=f"用例不存在或不属于该项目: {', '.join(map(str, bad))}")

    if payload.mode == "all":
        want = set(db.execute(select(TestCase.id).where(TestCase.project_id == plan.project_id)).scalars())
        current_ids = want
    else:
        existing = set(
            db.execute(select(PlanTestCase.testcase_id).where(PlanTestCase.plan_id == plan_id)).scalars()
        )
        if payload.mode == "add":
            current_ids = existing | want
        elif payload.mode == "remove":
            current_ids = existing - want
        else:
            current_ids = want

    db.execute(PlanTestCase.__table__.delete().where(PlanTestCase.plan_id == plan_id))
    for cid in sorted(current_ids):
        db.add(PlanTestCase(plan_id=plan_id, testcase_id=cid, added_by=current.id))
    db.commit()

    log_op(
        db, current, "编辑",
        target=f"计划#{plan_id} {plan.version}",
        detail=f"用例范围({payload.mode}):{len(current_ids)}条",
    )
    return {"plan_id": plan_id, "scoped": bool(current_ids), "total_cases": len(current_ids)}


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_project_access(plan.project_id, db, current)
    ver = plan.version
    db.delete(plan)
    db.commit()
    log_op(db, current, "删除", target=f"计划#{plan_id} {ver}")
    return {"ok": True}


@router.put("/{plan_id}/stage-times")
def update_stage_times(plan_id: int, payload: StageTimeUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """修改计划的三阶段时间"""
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_project_access(plan.project_id, db, current)
    if payload.sit_start is not None:
        plan.sit_start = _parse(payload.sit_start)
    if payload.sit_end is not None:
        plan.sit_end = _parse(payload.sit_end)
    if payload.uat_start is not None:
        plan.uat_start = _parse(payload.uat_start)
    if payload.uat_end is not None:
        plan.uat_end = _parse(payload.uat_end)
    if payload.pre_start is not None:
        plan.pre_start = _parse(payload.pre_start)
    if payload.pre_end is not None:
        plan.pre_end = _parse(payload.pre_end)
    db.commit()
    db.refresh(plan)
    log_op(db, current, "编辑", target=f"计划#{plan.id} 阶段时间")
    return {
        "sit_start": _fmt(plan.sit_start), "sit_end": _fmt(plan.sit_end),
        "uat_start": _fmt(plan.uat_start), "uat_end": _fmt(plan.uat_end),
        "pre_start": _fmt(plan.pre_start), "pre_end": _fmt(plan.pre_end),
    }


@router.get("/{plan_id}/countdown")
def countdown(
    plan_id: int,
    stage: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取指定阶段的倒计时;不传 stage 时用计划当前阶段"""
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_project_access(plan.project_id, db, current)

    # 三个阶段可独立查看,倒计时跟随所选阶段
    stage = (stage or plan.current_stage or "SIT").upper()
    if stage not in STAGE_ORDER:
        raise HTTPException(status_code=400, detail=f"阶段只能是 {'/'.join(STAGE_ORDER)}")

    start_map = {"SIT": (plan.sit_start, plan.sit_end), "UAT": (plan.uat_start, plan.uat_end), "PRE": (plan.pre_start, plan.pre_end)}
    start, end = start_map.get(stage, (None, None))
    now = datetime.now()
    result = {"stage": stage, "start": _fmt(start), "end": _fmt(end), "expired": False, "remaining_seconds": None}
    if end:
        diff = (end - now).total_seconds()
        result["remaining_seconds"] = max(int(diff), 0)
        result["expired"] = diff <= 0
    return result


@router.get("/calendar")
def calendar_view(
    year: int,
    month: int,
    project_id: int | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取指定月份的测试计划日历数据"""
    accessible = accessible_project_ids(db, current)
    q = select(TestPlan)

    if project_id is not None:
        require_project_access(project_id, db, current)
        q = q.where(TestPlan.project_id == project_id)
    elif accessible is not None:
        if not accessible:
            return []
        q = q.where(TestPlan.project_id.in_(accessible))

    plans = list(db.execute(q).scalars())

    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, month + 1, 1)

    calendar_items = []
    for plan in plans:
        project = db.get(Project, plan.project_id)
        project_name = project.name if project else ""

        for stage in STAGE_ORDER:
            start_attr = f"{stage.lower()}_start"
            end_attr = f"{stage.lower()}_end"
            start = getattr(plan, start_attr)
            end = getattr(plan, end_attr)

            if not start or not end:
                continue

            if end < month_start or start > month_end:
                continue

            calendar_items.append({
                "id": plan.id,
                "project_id": plan.project_id,
                "project_name": project_name,
                "version": plan.version,
                "stage": stage,
                "start": _fmt(start),
                "end": _fmt(end),
                "status": plan.status,
                "current_stage": plan.current_stage,
            })

    return calendar_items
