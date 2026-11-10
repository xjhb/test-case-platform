"""数据血缘与影响分析

血缘图: 需求 / 用例 / 批次 / 执行记录 / 缺陷 / 环境 六类节点,按已落库的关联关系
        逐层展开,前端用 ECharts 关系图渲染。
影响分析: 给定一个对象与"要改它 / 要删它",列出被牵连的上下游对象、风险等级与处置建议。

关系全部直读业务表(requirement_testcases / plan_testcases / testruns / defects),
不另建血缘表,因此不会出现血缘与业务数据对不上的情况。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from .. import gates
from ..database import get_db
from ..deps import get_current_user, require_project_access
from ..models import (
    Defect,
    PlanTestCase,
    Requirement,
    TestCase,
    TestCaseVersion,
    TestEnvironment,
    TestPlan,
    TestRound,
    TestRun,
    requirement_testcases,
)
from ..scope import has_scope, plan_case_ids

router = APIRouter(prefix="/api/lineage", tags=["数据血缘"])

TYPE_LABEL = {
    "requirement": "需求",
    "testcase": "用例",
    "plan": "批次",
    "run": "执行记录",
    "defect": "缺陷",
    "environment": "环境",
}
TYPE_PREFIX = {
    "requirement": "req",
    "testcase": "tc",
    "plan": "plan",
    "run": "run",
    "defect": "def",
    "environment": "env",
}
# 节点在图上的分类序号,决定 ECharts 的图例与配色顺序
TYPE_ORDER = ["requirement", "testcase", "plan", "run", "defect", "environment"]
CHANGE_LABEL = {"modify": "修改", "delete": "删除"}
MAX_ITEMS = 50  # 影响分析每个分组最多列出的条目数,超出只给计数


def _key(ntype: str, nid: int) -> str:
    return f"{TYPE_PREFIX[ntype]}:{nid}"


def _stamp(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "-"


# ===================== 节点 =====================
def build_node(db: Session, pid: int, ntype: str, nid: int) -> dict | None:
    """构造一个图节点;对象不存在或不属于该项目时返回 None"""
    if ntype == "requirement":
        o = db.get(Requirement, nid)
        if not o or o.project_id != pid:
            return None
        name = f"{o.req_no} {o.title}".strip()
        info = {"优先级": o.priority, "状态": o.status}
    elif ntype == "testcase":
        o = db.get(TestCase, nid)
        if not o or o.project_id != pid:
            return None
        name = o.title
        info = {"模块": o.module or "-", "优先级": o.priority, "结果": o.status, "评审": o.review_status}
    elif ntype == "plan":
        o = db.get(TestPlan, nid)
        if not o or o.project_id != pid:
            return None
        name = f"批次 {o.version}"
        info = {"当前阶段": o.current_stage, "状态": o.status}
    elif ntype == "run":
        o = db.get(TestRun, nid)
        if not o:
            return None
        tc = db.get(TestCase, o.testcase_id)
        if not tc or tc.project_id != pid:
            return None
        name = f"执行#{o.id} {o.stage} {o.status}"
        info = {"用例": tc.title, "执行时间": _stamp(o.executed_at)}
    elif ntype == "defect":
        o = db.get(Defect, nid)
        if not o or o.project_id != pid:
            return None
        name = o.title
        info = {"严重程度": o.severity, "优先级": o.priority, "状态": o.status}
    elif ntype == "environment":
        o = db.get(TestEnvironment, nid)
        if not o or o.project_id != pid:
            return None
        name = o.name
        info = {"服务阶段": o.stage, "状态": o.status, "部署版本": o.version or "-"}
    else:
        return None
    return {
        "id": _key(ntype, nid),
        "type": ntype,
        "type_label": TYPE_LABEL[ntype],
        "category": TYPE_ORDER.index(ntype),
        "name": name,
        "info": info,
    }


def _neighbors(db: Session, pid: int, ntype: str, nid: int) -> list[tuple[str, int, str, str, str]]:
    """返回 [(对端类型, 对端ID, 边的起点, 边的终点, 关系名)],边的方向统一为业务流向"""
    me = _key(ntype, nid)
    out: list[tuple[str, int, str, str, str]] = []

    def edge(other: str, oid: int, label: str, incoming: bool = False) -> None:
        ok = _key(other, oid)
        out.append((other, oid, ok if incoming else me, me if incoming else ok, label))

    if ntype == "requirement":
        rows = db.execute(
            select(requirement_testcases.c.testcase_id).where(requirement_testcases.c.requirement_id == nid)
        ).all()
        for (tcid,) in rows:
            edge("testcase", tcid, "覆盖")
    elif ntype == "testcase":
        for (rid,) in db.execute(
            select(requirement_testcases.c.requirement_id).where(requirement_testcases.c.testcase_id == nid)
        ).all():
            edge("requirement", rid, "覆盖", incoming=True)
        for (rid,) in db.execute(select(TestRun.id).where(TestRun.testcase_id == nid)).all():
            edge("run", rid, "执行")
        for (plan_id,) in db.execute(select(PlanTestCase.plan_id).where(PlanTestCase.testcase_id == nid)).all():
            edge("plan", plan_id, "圈选", incoming=True)
        for (did,) in db.execute(select(Defect.id).where(Defect.testcase_id == nid)).all():
            edge("defect", did, "关联")
    elif ntype == "plan":
        for (tcid,) in db.execute(select(PlanTestCase.testcase_id).where(PlanTestCase.plan_id == nid)).all():
            edge("testcase", tcid, "圈选")
        for (rid,) in db.execute(select(TestRun.id).where(TestRun.plan_id == nid)).all():
            edge("run", rid, "归属", incoming=True)
        for (did,) in db.execute(select(Defect.id).where(Defect.plan_id == nid)).all():
            edge("defect", did, "关联")
    elif ntype == "run":
        run = db.get(TestRun, nid)
        if run:
            edge("testcase", run.testcase_id, "执行", incoming=True)
            if run.plan_id:
                edge("plan", run.plan_id, "归属")
            if run.env_id:
                edge("environment", run.env_id, "运行于")
            for (did,) in db.execute(select(Defect.id).where(Defect.run_id == nid)).all():
                edge("defect", did, "产生")
    elif ntype == "defect":
        d = db.get(Defect, nid)
        if d:
            if d.testcase_id:
                edge("testcase", d.testcase_id, "关联", incoming=True)
            if d.run_id:
                edge("run", d.run_id, "产生", incoming=True)
            if d.plan_id:
                edge("plan", d.plan_id, "关联", incoming=True)
    elif ntype == "environment":
        for (rid,) in db.execute(select(TestRun.id).where(TestRun.env_id == nid)).all():
            edge("run", rid, "运行于", incoming=True)
    return out


def _graph(db: Session, pid: int, seeds: list[tuple[str, int]], depth: int, max_nodes: int) -> dict:
    nodes: dict[str, dict] = {}
    links: set[tuple[str, str, str]] = set()
    visited: set[tuple[str, int]] = set()
    frontier = list(seeds)
    truncated = False
    for _ in range(depth + 1):
        nxt: list[tuple[str, int]] = []
        for ntype, nid in frontier:
            if (ntype, nid) in visited:
                continue
            visited.add((ntype, nid))
            if len(nodes) >= max_nodes:
                truncated = True
                break
            node = build_node(db, pid, ntype, nid)
            if node is None:
                continue
            nodes[node["id"]] = node
            for other, oid, src, tgt, label in _neighbors(db, pid, ntype, nid):
                links.add((src, tgt, label))
                nxt.append((other, oid))
        if truncated or not nxt:
            break
        frontier = nxt
    # 截断掉的节点不能留下悬空边
    kept = [
        {"source": s, "target": t, "type": label}
        for (s, t, label) in sorted(links)
        if s in nodes and t in nodes
    ]
    counts: dict[str, int] = {t: 0 for t in TYPE_ORDER}
    for n in nodes.values():
        counts[n["type"]] += 1
    return {
        "project_id": pid,
        "depth": depth,
        "max_nodes": max_nodes,
        "truncated": truncated,
        "categories": [{"name": TYPE_LABEL[t]} for t in TYPE_ORDER],
        "counts": counts,
        "nodes": list(nodes.values()),
        "links": kept,
    }


@router.get("/graph")
def lineage_graph(
    project_id: int = Query(..., ge=1),
    root_type: str = "",
    root_id: int = Query(0, ge=0),
    depth: int = Query(2, ge=0, le=5),
    max_nodes: int = Query(300, ge=10, le=2000),
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """血缘关系图。不指定 root_type/root_id 时以该项目的需求与批次为起点展开全景图。"""
    require_project_access(project_id, db, current)
    if bool(root_type) != bool(root_id):
        raise HTTPException(status_code=400, detail="root_type 与 root_id 需同时提供")
    if root_type:
        if root_type not in TYPE_LABEL:
            raise HTTPException(status_code=400, detail=f"root_type 只能是 {'/'.join(TYPE_LABEL)}")
        seeds = [(root_type, root_id)]
    else:
        # 全景图: 项目内所有对象都作为起点,否则孤儿用例/孤儿缺陷会悄悄从图上消失。
        # 顺序即截断优先级——需求、批次、用例先保留,执行记录与缺陷其次。
        seeds = []
        for ntype, model in (
            ("requirement", Requirement),
            ("plan", TestPlan),
            ("testcase", TestCase),
            ("run", TestRun),
            ("defect", Defect),
            ("environment", TestEnvironment),
        ):
            if ntype == "run":
                rows = db.execute(
                    select(TestRun.id)
                    .join(TestCase, TestRun.testcase_id == TestCase.id)
                    .where(TestCase.project_id == project_id)
                    .order_by(TestRun.id)
                ).all()
            else:
                rows = db.execute(
                    select(model.id).where(model.project_id == project_id).order_by(model.id)
                ).all()
            seeds += [(ntype, r[0]) for r in rows]
    g = _graph(db, project_id, seeds, depth, max_nodes)
    g["root"] = _key(root_type, root_id) if root_type else ""
    return g


@router.get("/roots")
def lineage_roots(
    project_id: int = Query(..., ge=1),
    type: str = Query("testcase"),
    keyword: str = "",
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """血缘图起点候选列表(供前端下拉选择)"""
    require_project_access(project_id, db, current)
    if type not in TYPE_LABEL:
        raise HTTPException(status_code=400, detail=f"type 只能是 {'/'.join(TYPE_LABEL)}")
    kw = f"%{keyword}%" if keyword else None
    items: list[dict] = []
    if type == "requirement":
        q = select(Requirement).where(Requirement.project_id == project_id)
        if kw:
            q = q.where(Requirement.title.like(kw) | Requirement.req_no.like(kw))
        for o in db.execute(q.order_by(Requirement.id).limit(limit)).scalars():
            items.append({"id": o.id, "name": f"{o.req_no} {o.title}".strip(), "note": f"{o.priority} / {o.status}"})
    elif type == "testcase":
        q = select(TestCase).where(TestCase.project_id == project_id)
        if kw:
            q = q.where(TestCase.title.like(kw) | TestCase.module.like(kw))
        for o in db.execute(q.order_by(TestCase.id).limit(limit)).scalars():
            items.append({"id": o.id, "name": o.title, "note": f"{o.priority} / {o.status}"})
    elif type == "plan":
        for o in db.execute(
            select(TestPlan).where(TestPlan.project_id == project_id).order_by(TestPlan.id).limit(limit)
        ).scalars():
            items.append({"id": o.id, "name": f"批次 {o.version}", "note": f"{o.current_stage} / {o.status}"})
    elif type == "run":
        q = (
            select(TestRun)
            .join(TestCase, TestRun.testcase_id == TestCase.id)
            .where(TestCase.project_id == project_id)
        )
        for o in db.execute(q.order_by(TestRun.id.desc()).limit(limit)).scalars():
            tc = db.get(TestCase, o.testcase_id)
            items.append({"id": o.id, "name": f"执行#{o.id} {o.stage} {o.status}", "note": tc.title if tc else "-"})
    elif type == "defect":
        q = select(Defect).where(Defect.project_id == project_id)
        if kw:
            q = q.where(Defect.title.like(kw))
        for o in db.execute(q.order_by(Defect.id.desc()).limit(limit)).scalars():
            items.append({"id": o.id, "name": o.title, "note": f"{o.severity} / {o.status}"})
    else:
        for o in db.execute(
            select(TestEnvironment)
            .where(TestEnvironment.project_id == project_id)
            .order_by(TestEnvironment.id)
            .limit(limit)
        ).scalars():
            items.append({"id": o.id, "name": o.name, "note": f"{o.stage} / {o.status}"})
    return {"project_id": project_id, "type": type, "type_label": TYPE_LABEL[type], "items": items}


# ===================== 影响分析 =====================
def _plans_covering_case(db: Session, pid: int, tcid: int) -> list[tuple[TestPlan, bool]]:
    """覆盖该用例的批次;第二项为 True 表示批次未圈选范围,按项目全部用例隐式覆盖"""
    explicit = set(db.execute(select(PlanTestCase.plan_id).where(PlanTestCase.testcase_id == tcid)).scalars())
    out: list[tuple[TestPlan, bool]] = []
    for p in db.execute(select(TestPlan).where(TestPlan.project_id == pid).order_by(TestPlan.id)).scalars():
        if p.id in explicit:
            out.append((p, False))
        elif not has_scope(db, p):
            out.append((p, True))
    return out


def _case_runs(db: Session, tcid: int, limit: int = MAX_ITEMS) -> list[TestRun]:
    return list(
        db.execute(
            select(TestRun).where(TestRun.testcase_id == tcid).order_by(TestRun.id.desc()).limit(limit)
        ).scalars()
    )


def _case_defects(db: Session, tcid: int) -> list[Defect]:
    """直接挂在用例上的缺陷 + 由该用例执行记录产生的缺陷"""
    run_ids = list(db.execute(select(TestRun.id).where(TestRun.testcase_id == tcid)).scalars())
    conds = [Defect.testcase_id == tcid]
    if run_ids:
        conds.append(Defect.run_id.in_(run_ids))
    return list(
        db.execute(select(Defect).where(or_(*conds)).order_by(Defect.id.desc())).scalars()
    )


def _link(pid: int, ntype: str, nid: int) -> str:
    if ntype == "testcase":
        return f"/testcases?project_id={pid}&focus={nid}"
    if ntype == "plan":
        return f"/plans?project_id={pid}&focus={nid}"
    if ntype == "defect":
        return f"/defects?project_id={pid}&focus={nid}"
    if ntype == "requirement":
        return "/requirements"
    if ntype == "environment":
        return "/environments"
    return ""


def _section(key: str, title: str, level: str, note: str, items: list[dict], action: str) -> dict:
    return {
        "key": key,
        "title": title,
        "level": level,
        "note": note,
        "count": len(items),
        "shown": min(len(items), MAX_ITEMS),
        "items": items[:MAX_ITEMS],
        "action": action,
    }


def _aggregate_case_impact(db: Session, pid: int, tcids: list[int]) -> dict:
    """把一批用例的下游影响汇总成 plans/runs/defects/envs 四组"""
    plans: dict[int, TestPlan] = {}
    implicit: set[int] = set()
    for tcid in tcids:
        for p, imp in _plans_covering_case(db, pid, tcid):
            plans[p.id] = p
            if imp:
                implicit.add(p.id)
    runs = list(
        db.execute(
            select(TestRun).where(TestRun.testcase_id.in_(tcids)).order_by(TestRun.id.desc())
        ).scalars()
    ) if tcids else []
    defects = list(
        db.execute(
            select(Defect).where(Defect.testcase_id.in_(tcids)).order_by(Defect.id.desc())
        ).scalars()
    ) if tcids else []
    if runs:
        defects += list(
            db.execute(select(Defect).where(Defect.run_id.in_([r.id for r in runs]))).scalars()
        )
    seen_d: dict[int, Defect] = {d.id: d for d in defects}
    env_ids = {r.env_id for r in runs if r.env_id}
    envs = [db.get(TestEnvironment, e) for e in sorted(env_ids)]
    return {
        "plans": list(plans.values()),
        "implicit_plans": implicit,
        "runs": runs,
        "defects": list(seen_d.values()),
        "envs": [e for e in envs if e],
    }


def _risk(level: str, reason: str) -> dict:
    return {"level": level, "label": {"high": "高", "medium": "中", "low": "低"}[level], "reason": reason}


def _impact_testcase(db: Session, pid: int, tc: TestCase, change: str, critical: tuple[str, ...]) -> dict:
    plans = _plans_covering_case(db, pid, tc.id)
    runs = _case_runs(db, tc.id)
    defects = _case_defects(db, tc.id)
    open_d = [d for d in defects if d.status != "关闭"]
    critical_d = [d for d in open_d if d.severity in critical]
    env_ids = {r.env_id for r in runs if r.env_id}
    reqs = [
        db.get(Requirement, rid)
        for (rid,) in db.execute(
            select(requirement_testcases.c.requirement_id).where(requirement_testcases.c.testcase_id == tc.id)
        ).all()
    ]
    reqs = [r for r in reqs if r]
    versions = db.execute(
        select(func.count()).select_from(TestCaseVersion).where(TestCaseVersion.testcase_id == tc.id)
    ).scalar_one()
    latest = runs[0] if runs else None
    active_plans = [p for p, _ in plans if p.status != "已完成"]

    sections = [
        _section(
            "requirements", "关联需求", "warning" if reqs else "info",
            "用例内容变化后,需求覆盖关系需要重新确认" if reqs else "该用例未关联任何需求,无法证明需求被覆盖",
            [{"id": r.id, "name": f"{r.req_no} {r.title}".strip(), "note": f"{r.priority} / {r.status}",
              "link": _link(pid, "requirement", r.id)} for r in reqs],
            "确认修改后的用例仍能覆盖这些需求,否则需求覆盖率会虚高",
        ),
        _section(
            "plans", "受影响批次", "danger" if active_plans else ("info" if plans else "warning"),
            "以下批次的统计分母与通过率都包含该用例" if plans else "该用例尚未被任何批次圈选",
            [{"id": p.id, "name": f"批次 {p.version}",
              "note": f"{p.current_stage} / {p.status}" + ("(未圈选范围,隐式覆盖)" if imp else ""),
              "link": _link(pid, "plan", p.id)} for p, imp in plans],
            "进行中的批次需要重新执行该用例,已完成批次的历史结论应保留原样",
        ),
        _section(
            "runs", "历史执行记录", "warning" if latest and latest.status == "失败" else "info",
            f"共 {len(runs)} 条记录,最近一次 {latest.stage} {latest.status} ({_stamp(latest.executed_at)})"
            if latest else "尚无执行记录",
            [{"id": r.id, "name": f"执行#{r.id} {r.stage} {r.status}",
              "note": _stamp(r.executed_at), "link": ""} for r in runs],
            "历史结果代表旧版本用例的表现,修改后应新增执行而不是改写历史",
        ),
        _section(
            "defects", "关联缺陷", "danger" if critical_d else ("warning" if open_d else "info"),
            f"未关闭 {len(open_d)} 个,其中计入紧急 {len(critical_d)} 个" if open_d else f"共 {len(defects)} 个缺陷,均已关闭",
            [{"id": d.id, "name": d.title, "note": f"{d.severity} / {d.status}",
              "link": _link(pid, "defect", d.id)} for d in defects],
            "未关闭缺陷的复现步骤会随用例修改而失效,需同步更新缺陷描述",
        ),
        _section(
            "environments", "涉及环境", "info",
            f"该用例在 {len(env_ids)} 个环境上执行过" if env_ids else "执行记录未归属环境",
            [{"id": e.id, "name": e.name, "note": f"{e.stage} / {e.status}",
              "link": _link(pid, "environment", e.id)} for e in (db.get(TestEnvironment, i) for i in sorted(env_ids)) if e],
            "环境相关的失败结论在修改用例后需要重新验证",
        ),
    ]

    summary = [
        {"label": "关联需求", "value": len(reqs)},
        {"label": "受影响批次", "value": len(plans)},
        {"label": "进行中批次", "value": len(active_plans)},
        {"label": "执行记录", "value": len(runs)},
        {"label": "关联缺陷", "value": len(defects)},
        {"label": "未关闭缺陷", "value": len(open_d)},
        {"label": "历史版本", "value": versions},
    ]

    suggestion = []
    if change == "delete":
        if runs:
            suggestion.append(f"该用例有 {len(runs)} 条执行记录,删除会连带删除这些记录,批次通过率的分母同时变小,请先确认是否需要归档而不是删除")
        if open_d:
            suggestion.append(f"仍有 {len(open_d)} 个未关闭缺陷挂在该用例上,删除后缺陷会失去来源用例,追溯链断裂")
        if reqs:
            suggestion.append("删除前请把这些需求的覆盖关系转移到其它用例,否则需求覆盖率下降")
    else:
        if active_plans:
            suggestion.append("修改后请在进行中的批次里重新执行该用例,旧结果不代表新版本")
        if open_d:
            suggestion.append("同步更新未关闭缺陷里的复现步骤,避免开发按旧步骤无法复现")
        if reqs:
            suggestion.append("确认修改后的步骤仍覆盖关联需求,必要时补充新用例")
        suggestion.append("修改会自动留下版本记录,可在用例版本历史里对比与回滚")
    if not any(s for s in suggestion):
        suggestion.append("该用例暂无下游数据,可以安全操作")

    if critical_d:
        risk = _risk("high", f"存在 {len(critical_d)} 个未关闭的紧急缺陷,且 {len(active_plans)} 个进行中批次依赖该用例")
    elif active_plans or open_d:
        risk = _risk("medium", f"{len(active_plans)} 个进行中批次、{len(open_d)} 个未关闭缺陷会受影响")
    elif plans or runs:
        risk = _risk("low", "只影响历史数据,不影响进行中的批次")
    else:
        risk = _risk("low", "该用例没有下游数据")

    return {"sections": sections, "summary": summary, "suggestion": suggestion, "risk": risk}


def _impact_requirement(db: Session, pid: int, req: Requirement, change: str, critical: tuple[str, ...]) -> dict:
    tcids = list(
        db.execute(
            select(requirement_testcases.c.testcase_id).where(requirement_testcases.c.requirement_id == req.id)
        ).scalars()
    )
    cases = list(db.execute(select(TestCase).where(TestCase.id.in_(tcids)).order_by(TestCase.id)).scalars()) if tcids else []
    agg = _aggregate_case_impact(db, pid, tcids) if tcids else {"plans": [], "implicit_plans": set(), "runs": [], "defects": [], "envs": []}
    open_d = [d for d in agg["defects"] if d.status != "关闭"]
    critical_d = [d for d in open_d if d.severity in critical]
    draft = [c for c in cases if c.review_status != "已批准"]
    active_plans = [p for p in agg["plans"] if p.status != "已完成"]

    sections = [
        _section(
            "testcases", "覆盖用例", "warning" if not cases else ("danger" if draft else "info"),
            "该需求当前没有任何用例覆盖,属于覆盖盲区" if not cases
            else f"{len(cases)} 条用例覆盖,其中 {len(draft)} 条评审未通过",
            [{"id": c.id, "name": c.title, "note": f"{c.priority} / {c.status} / {c.review_status}",
              "link": _link(pid, "testcase", c.id)} for c in cases],
            "需求变更后逐条核对用例步骤与预期结果,未评审通过的用例要先补评审",
        ),
        _section(
            "plans", "受影响批次", "danger" if active_plans else "info",
            f"覆盖用例被 {len(agg['plans'])} 个批次纳入" if agg["plans"] else "覆盖用例尚未进入任何批次",
            [{"id": p.id, "name": f"批次 {p.version}", "note": f"{p.current_stage} / {p.status}",
              "link": _link(pid, "plan", p.id)} for p in agg["plans"]],
            "进行中的批次需要按新需求重跑相关用例",
        ),
        _section(
            "runs", "执行记录", "info",
            f"覆盖用例累计 {len(agg['runs'])} 条执行记录",
            [{"id": r.id, "name": f"执行#{r.id} {r.stage} {r.status}", "note": _stamp(r.executed_at), "link": ""}
             for r in agg["runs"]],
            "历史执行记录对应旧需求版本,仅作留痕",
        ),
        _section(
            "defects", "关联缺陷", "danger" if critical_d else ("warning" if open_d else "info"),
            f"未关闭 {len(open_d)} 个,其中计入紧急 {len(critical_d)} 个" if open_d else "没有未关闭缺陷",
            [{"id": d.id, "name": d.title, "note": f"{d.severity} / {d.status}",
              "link": _link(pid, "defect", d.id)} for d in agg["defects"]],
            "需求变更可能导致这些缺陷不再成立,或需要重新定级",
        ),
    ]
    summary = [
        {"label": "覆盖用例", "value": len(cases)},
        {"label": "评审未通过", "value": len(draft)},
        {"label": "受影响批次", "value": len(agg["plans"])},
        {"label": "执行记录", "value": len(agg["runs"])},
        {"label": "关联缺陷", "value": len(agg["defects"])},
        {"label": "未关闭缺陷", "value": len(open_d)},
    ]
    suggestion = []
    if change == "delete":
        if cases:
            suggestion.append(f"删除需求会同时删除 {len(cases)} 条用例的覆盖关系(用例本身保留),需求覆盖率会下降")
        if open_d:
            suggestion.append("仍有未关闭缺陷通过这些用例间接挂在该需求上,建议先关闭或改判缺陷")
    else:
        if not cases:
            suggestion.append("该需求还没有覆盖用例,变更后应先补齐用例再纳入批次")
        if draft:
            suggestion.append(f"{len(draft)} 条覆盖用例评审未通过,建议先完成评审")
        if active_plans:
            suggestion.append("进行中的批次需要按新需求重新执行覆盖用例")
    if not suggestion:
        suggestion.append("该需求下游数据干净,可以安全操作")

    if critical_d or (change == "delete" and cases):
        risk = _risk("high", f"存在 {len(critical_d)} 个未关闭紧急缺陷,变更会波及 {len(cases)} 条用例与 {len(agg['plans'])} 个批次")
    elif cases or open_d:
        risk = _risk("medium", f"{len(cases)} 条覆盖用例、{len(open_d)} 个未关闭缺陷会受影响")
    else:
        risk = _risk("low", "该需求尚无覆盖用例,影响面为空")
    return {"sections": sections, "summary": summary, "suggestion": suggestion, "risk": risk}


def _impact_plan(db: Session, pid: int, plan: TestPlan, change: str, critical: tuple[str, ...]) -> dict:
    case_ids = plan_case_ids(db, plan)
    scoped = has_scope(db, plan)
    runs = list(db.execute(select(TestRun).where(TestRun.plan_id == plan.id).order_by(TestRun.id.desc())).scalars())
    conds = [Defect.plan_id == plan.id]
    if case_ids:
        conds.append(Defect.testcase_id.in_(case_ids))
    defects = list(
        db.execute(
            select(Defect).where(or_(*conds)).order_by(Defect.id.desc())
        ).scalars()
    )
    open_d = [d for d in defects if d.status != "关闭"]
    critical_d = [d for d in open_d if d.severity in critical]
    rounds = list(db.execute(select(TestRound).where(TestRound.plan_id == plan.id).order_by(TestRound.round_number)).scalars())
    env_ids = {r.env_id for r in runs if r.env_id}
    envs = [db.get(TestEnvironment, e) for e in sorted(env_ids)]
    gate = gates.evaluate(db, plan, plan.current_stage, "准出")

    cases = list(
        db.execute(select(TestCase).where(TestCase.id.in_(case_ids)).order_by(TestCase.id).limit(MAX_ITEMS)).scalars()
    ) if case_ids else []
    sections = [
        _section(
            "testcases", "纳入用例", "warning" if not scoped else "info",
            f"已圈选 {len(case_ids)} 条用例,统计分母以此为准" if scoped
            else f"未圈选范围,按项目全部用例计入统计,共 {len(case_ids)} 条",
            [{"id": c.id, "name": c.title, "note": f"{c.priority} / {c.status}",
              "link": _link(pid, "testcase", c.id)} for c in cases],
            "改动批次范围会直接改变通过率与执行率的分母,门禁结论随之变化",
        ),
        _section(
            "runs", "执行记录", "info",
            f"该批次累计 {len(runs)} 条执行记录",
            [{"id": r.id, "name": f"执行#{r.id} {r.stage} {r.status}", "note": _stamp(r.executed_at), "link": ""}
             for r in runs],
            "删除批次会连带删除这些执行记录,历史结论将不可追溯",
        ),
        _section(
            "defects", "关联缺陷", "danger" if critical_d else ("warning" if open_d else "info"),
            f"未关闭 {len(open_d)} 个,其中计入紧急 {len(critical_d)} 个" if open_d else f"共 {len(defects)} 个缺陷,均已关闭",
            [{"id": d.id, "name": d.title, "note": f"{d.severity} / {d.status}",
              "link": _link(pid, "defect", d.id)} for d in defects],
            "准出门禁要求未关闭紧急缺陷清零,处理完这些缺陷才能推进阶段",
        ),
        _section(
            "rounds", "测试轮次", "info",
            f"共 {len(rounds)} 个轮次" if rounds else "尚未划分轮次",
            [{"id": r.id, "name": r.name, "note": f"第{r.round_number}轮 / {r.status}", "link": ""} for r in rounds],
            "轮次下的执行记录会随批次一并变化",
        ),
        _section(
            "environments", "使用环境", "info",
            f"执行记录覆盖 {len(env_ids)} 个环境" if env_ids else "执行记录未归属环境",
            [{"id": e.id, "name": e.name, "note": f"{e.stage} / {e.status}",
              "link": _link(pid, "environment", e.id)} for e in envs if e],
            "环境停用或删除后,这些执行记录的环境归属会置空",
        ),
    ]
    summary = [
        {"label": "纳入用例", "value": len(case_ids)},
        {"label": "执行记录", "value": len(runs)},
        {"label": "测试轮次", "value": len(rounds)},
        {"label": "关联缺陷", "value": len(defects)},
        {"label": "未关闭缺陷", "value": len(open_d)},
        {"label": "使用环境", "value": len(env_ids)},
        {"label": f"{plan.current_stage} 准出门禁", "value": "达标" if gate["passed"] else ("未达标" if gate["configured"] else "未配置")},
    ]
    suggestion = []
    if change == "delete":
        if runs:
            suggestion.append(f"删除批次会连带删除 {len(runs)} 条执行记录与 {len(rounds)} 个轮次,历史测试结论将无法追溯")
        if open_d:
            suggestion.append(f"仍有 {len(open_d)} 个未关闭缺陷挂在该批次上,删除后缺陷失去批次归属")
        suggestion.append("已完成的批次建议归档而不是删除,审计与回溯都依赖它")
    else:
        if not scoped:
            suggestion.append("该批次尚未圈选用例范围,统计口径是项目全部用例,建议先圈选以便结论可复现")
        if not gate["passed"] and gate["configured"]:
            bad = [i["label"] for i in gate["items"] if not i["ok"]]
            suggestion.append(f"{plan.current_stage} 准出门禁未达标: {'、'.join(bad)}")
        if critical_d:
            suggestion.append(f"存在 {len(critical_d)} 个未关闭紧急缺陷,准出前必须清零")
    if not suggestion:
        suggestion.append("该批次当前状态健康,可以安全操作")

    if critical_d or (change == "delete" and runs):
        risk = _risk("high", f"{len(critical_d)} 个未关闭紧急缺陷、{len(runs)} 条执行记录会受影响")
    elif open_d or runs:
        risk = _risk("medium", f"{len(case_ids)} 条用例、{len(open_d)} 个未关闭缺陷会受影响")
    else:
        risk = _risk("low", "该批次尚无执行数据")
    return {"sections": sections, "summary": summary, "suggestion": suggestion, "risk": risk}


def _impact_environment(db: Session, pid: int, env: TestEnvironment, change: str, critical: tuple[str, ...]) -> dict:
    runs = list(
        db.execute(select(TestRun).where(TestRun.env_id == env.id).order_by(TestRun.id.desc())).scalars()
    )
    tcids = sorted({r.testcase_id for r in runs})
    plan_ids = sorted({r.plan_id for r in runs if r.plan_id})
    run_ids = [r.id for r in runs]
    defects = list(
        db.execute(select(Defect).where(Defect.run_id.in_(run_ids)).order_by(Defect.id.desc())).scalars()
    ) if run_ids else []
    open_d = [d for d in defects if d.status != "关闭"]
    critical_d = [d for d in open_d if d.severity in critical]
    failed = [r for r in runs if r.status == "失败"]

    sections = [
        _section(
            "runs", "该环境上的执行记录", "warning" if failed else "info",
            f"共 {len(runs)} 条,其中失败 {len(failed)} 条" if runs else "尚无执行记录归属该环境",
            [{"id": r.id, "name": f"执行#{r.id} {r.stage} {r.status}", "note": _stamp(r.executed_at), "link": ""}
             for r in runs],
            "环境删除后这些记录的环境归属会置空,失败原因是环境还是产品将无法区分",
        ),
        _section(
            "testcases", "涉及用例", "info",
            f"{len(tcids)} 条用例在该环境上执行过",
            [{"id": c.id, "name": c.title, "note": f"{c.priority} / {c.status}",
              "link": _link(pid, "testcase", c.id)}
             for c in db.execute(select(TestCase).where(TestCase.id.in_(tcids)).order_by(TestCase.id).limit(MAX_ITEMS)).scalars()]
            if tcids else [],
            "环境变更(版本/地址)后,这些用例的既有结论需要重新验证",
        ),
        _section(
            "plans", "涉及批次", "info",
            f"{len(plan_ids)} 个批次的执行落在该环境上" if plan_ids else "无",
            [{"id": p.id, "name": f"批次 {p.version}", "note": f"{p.current_stage} / {p.status}",
              "link": _link(pid, "plan", p.id)}
             for p in db.execute(select(TestPlan).where(TestPlan.id.in_(plan_ids)).order_by(TestPlan.id)).scalars()]
            if plan_ids else [],
            "批次报告里的环境说明需要同步更新",
        ),
        _section(
            "defects", "环境相关缺陷", "danger" if critical_d else ("warning" if open_d else "info"),
            f"由该环境执行记录产生的缺陷 {len(defects)} 个,未关闭 {len(open_d)} 个" if defects else "无相关缺陷",
            [{"id": d.id, "name": d.title, "note": f"{d.severity} / {d.status}",
              "link": _link(pid, "defect", d.id)} for d in defects],
            "停用环境前先确认这些缺陷不是环境问题,否则会误判产品质量",
        ),
    ]
    summary = [
        {"label": "执行记录", "value": len(runs)},
        {"label": "失败记录", "value": len(failed)},
        {"label": "涉及用例", "value": len(tcids)},
        {"label": "涉及批次", "value": len(plan_ids)},
        {"label": "相关缺陷", "value": len(defects)},
        {"label": "未关闭缺陷", "value": len(open_d)},
    ]
    suggestion = []
    if change == "delete":
        if runs:
            suggestion.append(f"该环境已被 {len(runs)} 条执行记录引用,建议改为「已停用」而不是删除,保留历史归属")
        if open_d:
            suggestion.append(f"仍有 {len(open_d)} 个未关闭缺陷来自该环境,先确认是否为环境问题")
    else:
        if env.status == "维护中":
            suggestion.append("环境处于维护中,落在该环境的执行结论可能不可信,恢复后建议重跑关键用例")
        if failed:
            suggestion.append(f"{len(failed)} 条失败记录发生在该环境,变更前先区分是环境故障还是产品缺陷")
        if tcids:
            suggestion.append(f"版本或地址变更后,{len(tcids)} 条用例的既有通过结论需要重新验证")
    if not suggestion:
        suggestion.append("该环境没有关联执行数据,可以安全操作")

    if change == "delete" and runs:
        risk = _risk("high", f"{len(runs)} 条执行记录引用该环境,删除会造成历史归属丢失")
    elif open_d or failed:
        risk = _risk("medium", f"{len(open_d)} 个未关闭缺陷、{len(failed)} 条失败记录与该环境相关")
    elif runs:
        risk = _risk("low", "仅有历史执行记录引用,结论均已通过")
    else:
        risk = _risk("low", "该环境尚未被任何执行记录引用")
    return {"sections": sections, "summary": summary, "suggestion": suggestion, "risk": risk}


def _impact_defect(db: Session, pid: int, defect: Defect, change: str, critical: tuple[str, ...]) -> dict:
    tc = db.get(TestCase, defect.testcase_id) if defect.testcase_id else None
    run = db.get(TestRun, defect.run_id) if defect.run_id else None
    plan = db.get(TestPlan, defect.plan_id) if defect.plan_id else None
    if not plan and run and run.plan_id:
        plan = db.get(TestPlan, run.plan_id)
    reqs = []
    if tc:
        reqs = [
            db.get(Requirement, rid)
            for (rid,) in db.execute(
                select(requirement_testcases.c.requirement_id).where(requirement_testcases.c.testcase_id == tc.id)
            ).all()
        ]
        reqs = [r for r in reqs if r]
    is_critical = defect.severity in critical
    blocks_gate = is_critical and defect.status != "关闭" and plan is not None

    sections = [
        _section(
            "testcase", "来源用例", "warning" if not tc else "info",
            "该缺陷未关联来源用例,无法定位到具体测试内容" if not tc else f"来源用例: {tc.title}",
            [{"id": tc.id, "name": tc.title, "note": f"{tc.priority} / {tc.status}",
              "link": _link(pid, "testcase", tc.id)}] if tc else [],
            "补齐用例关联后,缺陷才能进入需求→用例→缺陷的追溯链",
        ),
        _section(
            "run", "来源执行记录", "info",
            f"执行#{run.id} {run.stage} {run.status} ({_stamp(run.executed_at)})" if run else "未关联执行记录",
            [{"id": run.id, "name": f"执行#{run.id} {run.stage} {run.status}",
              "note": _stamp(run.executed_at), "link": ""}] if run else [],
            "执行记录决定了该缺陷属于哪个阶段与轮次",
        ),
        _section(
            "plan", "所属批次", "danger" if blocks_gate else "info",
            (f"批次 {plan.version} / {plan.current_stage} / {plan.status}" if plan else "未归属任何批次")
            + (",该紧急缺陷未关闭会卡住准出门禁" if blocks_gate else ""),
            [{"id": plan.id, "name": f"批次 {plan.version}", "note": f"{plan.current_stage} / {plan.status}",
              "link": _link(pid, "plan", plan.id)}] if plan else [],
            "关闭该缺陷后需要重新校验批次准出门禁",
        ),
        _section(
            "requirements", "间接影响需求", "warning" if reqs else "info",
            f"通过来源用例关联到 {len(reqs)} 条需求" if reqs else "未关联到需求",
            [{"id": r.id, "name": f"{r.req_no} {r.title}".strip(), "note": f"{r.priority} / {r.status}",
              "link": _link(pid, "requirement", r.id)} for r in reqs],
            "缺陷未修复意味着这些需求的验收结论存疑",
        ),
    ]
    summary = [
        {"label": "严重程度", "value": defect.severity},
        {"label": "计入紧急", "value": "是" if is_critical else "否"},
        {"label": "当前状态", "value": defect.status},
        {"label": "来源用例", "value": "有" if tc else "无"},
        {"label": "所属批次", "value": plan.version if plan else "无"},
        {"label": "影响需求", "value": len(reqs)},
    ]
    suggestion = []
    if change == "delete":
        suggestion.append("缺陷删除后追溯链会断裂,建议改为「关闭」并填写结论,保留审计痕迹")
        if blocks_gate:
            suggestion.append("该缺陷是准出门禁的卡点,删除会让门禁虚高通过,请谨慎")
    else:
        if not tc:
            suggestion.append("先补齐来源用例关联,否则该缺陷无法参与需求覆盖率与用例质量分析")
        if blocks_gate:
            suggestion.append(f"关闭该紧急缺陷后,{plan.current_stage} 准出门禁的「未关闭紧急缺陷」计数才会清零")
        if reqs:
            suggestion.append("状态变更会影响这些需求的验收结论,需求侧需要同步确认")
    if not suggestion:
        suggestion.append("该缺陷变更不影响门禁与追溯,可以安全操作")

    if blocks_gate:
        risk = _risk("high", "该紧急缺陷未关闭,直接卡住批次准出门禁")
    elif tc or plan:
        risk = _risk("medium", "变更会影响追溯链与批次缺陷统计")
    else:
        risk = _risk("low", "该缺陷未关联用例与批次,影响面很小")
    return {"sections": sections, "summary": summary, "suggestion": suggestion, "risk": risk}


@router.get("/impact")
def lineage_impact(
    project_id: int = Query(..., ge=1),
    type: str = Query(...),
    id: int = Query(..., ge=1),
    change: str = Query("modify"),
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """影响分析: 改动/删除某对象会牵连哪些上下游数据"""
    require_project_access(project_id, db, current)
    if type not in ("requirement", "testcase", "plan", "environment", "defect"):
        raise HTTPException(status_code=400, detail="type 只能是 requirement/testcase/plan/environment/defect")
    if change not in CHANGE_LABEL:
        raise HTTPException(status_code=400, detail="change 只能是 modify/delete")

    model = {
        "requirement": Requirement,
        "testcase": TestCase,
        "plan": TestPlan,
        "environment": TestEnvironment,
        "defect": Defect,
    }[type]
    obj = db.get(model, id)
    if not obj or obj.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"{TYPE_LABEL[type]}不存在或不属于该项目")

    critical = gates.critical_severities(db, project_id)
    handler = {
        "requirement": _impact_requirement,
        "testcase": _impact_testcase,
        "plan": _impact_plan,
        "environment": _impact_environment,
        "defect": _impact_defect,
    }[type]
    result = handler(db, project_id, obj, change, critical)

    node = build_node(db, project_id, type, id)
    result["root"] = node
    result["change"] = change
    result["change_label"] = CHANGE_LABEL[change]
    result["project_id"] = project_id
    result["critical_severities"] = list(critical)
    return result


@router.get("/overview")
def lineage_overview(
    project_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """项目血缘概况: 各类对象数量与断链情况,用于提示哪里缺追溯关系"""
    require_project_access(project_id, db, current)

    def count(model) -> int:
        return db.execute(
            select(func.count()).select_from(model).where(model.project_id == project_id)
        ).scalar_one()

    total_cases = count(TestCase)
    total_reqs = count(Requirement)
    linked_cases = db.execute(
        select(func.count(distinct(requirement_testcases.c.testcase_id)))
        .select_from(requirement_testcases)
        .join(TestCase, TestCase.id == requirement_testcases.c.testcase_id)
        .where(TestCase.project_id == project_id)
    ).scalar_one()
    covered_reqs = db.execute(
        select(func.count(distinct(requirement_testcases.c.requirement_id)))
        .select_from(requirement_testcases)
        .join(Requirement, Requirement.id == requirement_testcases.c.requirement_id)
        .where(Requirement.project_id == project_id)
    ).scalar_one()
    runs = list(
        db.execute(
            select(TestRun.id, TestRun.env_id, TestRun.plan_id)
            .join(TestCase, TestRun.testcase_id == TestCase.id)
            .where(TestCase.project_id == project_id)
        ).all()
    )
    defects = list(
        db.execute(
            select(Defect.id, Defect.testcase_id, Defect.run_id, Defect.plan_id, Defect.status)
            .where(Defect.project_id == project_id)
        ).all()
    )
    orphan_defects = [d for d in defects if not d.testcase_id and not d.run_id and not d.plan_id]
    plans = list(db.execute(select(TestPlan).where(TestPlan.project_id == project_id).order_by(TestPlan.id)).scalars())
    unscoped_plans = [p.id for p in plans if not has_scope(db, p)]

    gaps = []
    if total_reqs and covered_reqs < total_reqs:
        gaps.append({"level": "warning", "text": f"{total_reqs - covered_reqs} 条需求没有任何用例覆盖"})
    if total_cases and linked_cases < total_cases:
        gaps.append({"level": "info", "text": f"{total_cases - linked_cases} 条用例未关联需求,无法证明需求覆盖"})
    if orphan_defects:
        gaps.append({"level": "warning", "text": f"{len(orphan_defects)} 个缺陷没有来源用例/执行记录/批次,追溯链断裂"})
    if unscoped_plans:
        gaps.append({"level": "info", "text": f"{len(unscoped_plans)} 个批次未圈选用例范围,统计口径为项目全部用例"})
    if runs and sum(1 for r in runs if not r.env_id) :
        gaps.append({"level": "info", "text": f"{sum(1 for r in runs if not r.env_id)} 条执行记录未归属环境"})
    if not gaps:
        gaps.append({"level": "success", "text": "追溯关系完整,没有发现断链"})

    return {
        "project_id": project_id,
        "counts": {
            "requirement": total_reqs,
            "testcase": total_cases,
            "plan": len(plans),
            "run": len(runs),
            "defect": len(defects),
            "environment": count(TestEnvironment),
        },
        "coverage": {
            "covered_requirements": covered_reqs,
            "requirement_coverage": round(covered_reqs / total_reqs * 100, 1) if total_reqs else 0.0,
            "linked_testcases": linked_cases,
            "testcase_link_rate": round(linked_cases / total_cases * 100, 1) if total_cases else 0.0,
            "orphan_defects": len(orphan_defects),
        },
        "gaps": gaps,
    }
