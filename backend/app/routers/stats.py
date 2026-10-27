from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_project_ids, get_current_user, require_project_access
from ..models import Project, TestCase, TestPlan, TestRun, User

router = APIRouter(prefix="/api/stats", tags=["统计看板"], dependencies=[Depends(get_current_user)])

STAGE_ORDER = ["SIT", "UAT", "PRE"]


def _latest_runs(db: Session, plan_id: int, stage: str) -> dict[int, TestRun]:
    runs = list(
        db.execute(
            select(TestRun)
            .where(TestRun.plan_id == plan_id, TestRun.stage == stage)
            .order_by(TestRun.id.desc())
        ).scalars()
    )
    latest: dict[int, TestRun] = {}
    for r in runs:
        if r.testcase_id not in latest:
            latest[r.testcase_id] = r
    return latest


def _health_level(pass_rate: float) -> tuple[str, str]:
    """根据通过率返回 (等级颜色, 描述)
    <50% 红, 50-70% 红, 70-90% 黄, >=90% 绿
    """
    if pass_rate >= 90:
        return "green", "健康"
    elif pass_rate >= 70:
        return "yellow", "关注"
    else:
        return "red", "警告"


@router.get("/dashboard")
def dashboard(
    project_id: int | None = None,
    plan_id: int | None = None,
    stage: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    accessible = accessible_project_ids(db, current)

    # ---- 确定数据范围 ----
    # 如果选了 plan_id,以该计划为准(需校验权限)
    target_plan = None
    if plan_id:
        target_plan = db.get(TestPlan, plan_id)
        if not target_plan:
            return {"error": "计划不存在"}
        require_project_access(target_plan.project_id, db, current)
        project_id = target_plan.project_id

    # 如果选了 project_id,校验权限
    if project_id and not target_plan:
        require_project_access(project_id, db, current)

    # ---- 项目/计划计数(概览) ----
    pq = select(Project)
    if accessible is not None:
        if not accessible:
            return _empty_dashboard()
        pq = pq.where(Project.id.in_(accessible))
    if project_id:
        pq = pq.where(Project.id == project_id)
    project_count = db.execute(select(Project).select_from(pq.subquery())).scalar_one() if False else len(
        list(db.execute(pq).scalars())
    )

    # 用例
    cq = select(TestCase)
    if project_id:
        cq = cq.where(TestCase.project_id == project_id)
    elif accessible is not None:
        cq = cq.where(TestCase.project_id.in_(accessible))
    cases = list(db.execute(cq).scalars())
    case_count = len(cases)

    # 计划
    plq = select(TestPlan)
    if project_id:
        plq = plq.where(TestPlan.project_id == project_id)
    elif accessible is not None:
        plq = plq.where(TestPlan.project_id.in_(accessible))
    plans = list(db.execute(plq).scalars())
    plan_count = len(plans)
    plans_in_progress = sum(1 for p in plans if p.status == "进行中")

    # ---- 如果有 plan_id,计算该计划各阶段详细数据 ----
    quality_stages = []
    efficiency_stage_completion = []
    execution_progress = 0
    severe_defect_ratio = 0
    daily_trend = []
    per_person = []

    if target_plan:
        pid = target_plan.id
        total_cases = len(cases)

        for st in STAGE_ORDER:
            latest = _latest_runs(db, pid, st)
            passed = failed = blocked = pending = 0
            for c in cases:
                run = latest.get(c.id)
                s = run.status if run else "未执行"
                if s == "通过":
                    passed += 1
                elif s == "失败":
                    failed += 1
                elif s == "阻塞":
                    blocked += 1
                else:
                    pending += 1
            executed = passed + failed + blocked
            pass_rate = round(passed / total_cases * 100, 1) if total_cases else 0
            exec_rate = round(executed / total_cases * 100, 1) if total_cases else 0
            level, level_desc = _health_level(pass_rate)

            # 严重缺陷占比 = P0失败数 / P0用例数
            p0_cases = [c for c in cases if c.priority == "P0"]
            p0_failed = sum(1 for c in p0_cases if latest.get(c.id) and latest[c.id].status == "失败")
            p0_ratio = round(p0_failed / len(p0_cases) * 100, 1) if p0_cases else 0

            quality_stages.append({
                "stage": st,
                "total": total_cases,
                "passed": passed,
                "failed": failed,
                "blocked": blocked,
                "pending": pending,
                "pass_rate": pass_rate,
                "exec_rate": exec_rate,
                "health_level": level,
                "health_desc": level_desc,
                "severe_defect_ratio": p0_ratio,
            })
            efficiency_stage_completion.append({"stage": st, "rate": pass_rate, "total": total_cases, "passed": passed})

        # 执行进度(当前阶段或指定阶段)
        focus_stage = stage or target_plan.current_stage
        focus_latest = _latest_runs(db, pid, focus_stage)
        executed_count = sum(1 for c in cases if focus_latest.get(c.id))
        execution_progress = round(executed_count / len(cases) * 100, 1) if cases else 0

        # 严重缺陷占比(总览)
        p0_all = [c for c in cases if c.priority == "P0"]
        p0_fail_all = sum(1 for c in p0_all if focus_latest.get(c.id) and focus_latest[c.id].status == "失败")
        severe_defect_ratio = round(p0_fail_all / len(p0_all) * 100, 1) if p0_all else 0

        # 每日执行趋势(近7天)
        seven_days_ago = datetime.now() - timedelta(days=6)
        trend_q = select(TestRun).where(
            TestRun.plan_id == pid,
            TestRun.executed_at >= seven_days_ago.replace(hour=0, minute=0, second=0)
        )
        if stage:
            trend_q = trend_q.where(TestRun.stage == stage)
        trend_runs = list(db.execute(trend_q).scalars())
        for i in range(7):
            d = (datetime.now() - timedelta(days=6 - i)).date()
            count = sum(1 for r in trend_runs if r.executed_at.date() == d)
            daily_trend.append({"date": d.strftime("%m-%d"), "count": count})

        # 人均执行量
        all_runs_q = select(TestRun).where(TestRun.plan_id == pid)
        if stage:
            all_runs_q = all_runs_q.where(TestRun.stage == stage)
        all_runs = list(db.execute(all_runs_q).scalars())
        user_counts: dict[int, int] = {}
        for r in all_runs:
            user_counts[r.executed_by] = user_counts.get(r.executed_by, 0) + 1
        for uid, cnt in sorted(user_counts.items(), key=lambda x: -x[1]):
            u = db.get(User, uid)
            name = (u.display_name or u.username) if u else f"用户#{uid}"
            per_person.append({"name": name, "count": cnt})

    # ---- 质量健康度(总览) ----
    if quality_stages:
        focus = stage or (target_plan.current_stage if target_plan else "SIT")
        focus_data = next((s for s in quality_stages if s["stage"] == focus), quality_stages[0])
        health_score = focus_data["pass_rate"]
        health_level = focus_data["health_level"]
        health_desc = focus_data["health_desc"]
    else:
        health_score = 0
        health_level = "green"
        health_desc = "无数据"

    return {
        # 概览
        "overview": {
            "projects": project_count,
            "cases": case_count,
            "plans": plan_count,
            "plans_in_progress": plans_in_progress,
        },
        # 筛选上下文
        "filters": {
            "project_id": project_id,
            "plan_id": plan_id,
            "stage": stage or (target_plan.current_stage if target_plan else None),
        },
        # 测试质量
        "quality": {
            "health_score": health_score,
            "health_level": health_level,
            "health_desc": health_desc,
            "severe_defect_ratio": severe_defect_ratio,
            "stages": quality_stages,
        },
        # 测试效率
        "efficiency": {
            "execution_progress": execution_progress,
            "stage_completion": efficiency_stage_completion,
            "daily_trend": daily_trend,
            "per_person": per_person,
        },
    }


def _empty_dashboard():
    return {
        "overview": {"projects": 0, "cases": 0, "plans": 0, "plans_in_progress": 0},
        "filters": {"project_id": None, "plan_id": None, "stage": None},
        "quality": {"health_score": 0, "health_level": "green", "health_desc": "无数据",
                     "severe_defect_ratio": 0, "stages": []},
        "efficiency": {"execution_progress": 0, "stage_completion": [], "daily_trend": [], "per_person": []},
    }


@router.get("/trends/pass-rate")
def pass_rate_trends(
    project_id: int,
    stage: str = "SIT",
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取项目各版本通过率趋势"""
    require_project_access(project_id, db, current)

    plans = list(
        db.execute(
            select(TestPlan)
            .where(TestPlan.project_id == project_id)
            .order_by(TestPlan.created_at.asc())
        ).scalars()
    )

    trends = []
    for plan in plans:
        cases = list(db.execute(select(TestCase).where(TestCase.project_id == project_id)).scalars())
        total = len(cases)
        if total == 0:
            continue

        latest = _latest_runs(db, plan.id, stage)
        passed = sum(1 for c in cases if latest.get(c.id) and latest[c.id].status == "通过")
        pass_rate = round(passed / total * 100, 1) if total else 0

        trends.append({
            "plan_id": plan.id,
            "version": plan.version,
            "pass_rate": pass_rate,
            "total": total,
            "passed": passed,
            "created_at": plan.created_at.strftime("%Y-%m-%d") if plan.created_at else "",
        })

    return {"project_id": project_id, "stage": stage, "trends": trends}


@router.get("/trends/defect-convergence")
def defect_convergence(
    project_id: int,
    plan_id: int | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取缺陷收敛曲线(按天统计)"""
    require_project_access(project_id, db, current)

    from ..models import Defect

    q = select(Defect).where(Defect.project_id == project_id)
    if plan_id:
        q = q.where(Defect.plan_id == plan_id)

    defects = list(db.execute(q).scalars())

    # 按天统计新增和关闭的缺陷
    daily_stats = {}
    for d in defects:
        date_key = d.created_at.strftime("%Y-%m-%d") if d.created_at else ""
        if date_key:
            if date_key not in daily_stats:
                daily_stats[date_key] = {"new": 0, "resolved": 0, "cumulative": 0}
            daily_stats[date_key]["new"] += 1

        if d.resolved_at:
            resolve_key = d.resolved_at.strftime("%Y-%m-%d")
            if resolve_key not in daily_stats:
                daily_stats[resolve_key] = {"new": 0, "resolved": 0, "cumulative": 0}
            daily_stats[resolve_key]["resolved"] += 1

    # 计算累计缺陷数
    sorted_dates = sorted(daily_stats.keys())
    cumulative = 0
    result = []
    for date in sorted_dates:
        stats = daily_stats[date]
        cumulative += stats["new"] - stats["resolved"]
        result.append({
            "date": date,
            "new": stats["new"],
            "resolved": stats["resolved"],
            "cumulative": cumulative,
        })

    return {"project_id": project_id, "plan_id": plan_id, "convergence": result}


@router.get("/workload/distribution")
def workload_distribution(
    project_id: int,
    plan_id: int | None = None,
    days: int = 30,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取人员工作量分布(近N天)"""
    require_project_access(project_id, db, current)

    start_date = datetime.now() - timedelta(days=days)

    q = select(TestRun).where(TestRun.executed_at >= start_date)
    if plan_id:
        q = q.where(TestRun.plan_id == plan_id)

    # 获取该项目下的所有用例
    case_ids = [c.id for c in db.execute(select(TestCase.id).where(TestCase.project_id == project_id)).all()]
    if case_ids:
        q = q.where(TestRun.testcase_id.in_(case_ids))

    runs = list(db.execute(q).scalars())

    # 按用户统计
    user_stats = {}
    for r in runs:
        uid = r.executed_by
        if uid not in user_stats:
            user_stats[uid] = {"total": 0, "passed": 0, "failed": 0, "blocked": 0}
        user_stats[uid]["total"] += 1
        if r.status == "通过":
            user_stats[uid]["passed"] += 1
        elif r.status == "失败":
            user_stats[uid]["failed"] += 1
        elif r.status == "阻塞":
            user_stats[uid]["blocked"] += 1

    result = []
    for uid, stats in sorted(user_stats.items(), key=lambda x: -x[1]["total"]):
        user = db.get(User, uid)
        name = (user.display_name or user.username) if user else f"用户#{uid}"
        result.append({
            "user_id": uid,
            "name": name,
            "total": stats["total"],
            "passed": stats["passed"],
            "failed": stats["failed"],
            "blocked": stats["blocked"],
        })

    return {"project_id": project_id, "plan_id": plan_id, "days": days, "distribution": result}
