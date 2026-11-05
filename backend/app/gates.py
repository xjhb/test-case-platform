"""阶段准入/准出门禁:规则目录、指标计算与校验。

门禁按项目配置(StageGate),在阶段推进时校验"当前阶段准出 + 目标阶段准入",
在计划完成时校验"当前阶段准出"。管理员可强制越权,但会单独记入操作日志。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Defect, StageGate, TestCase, TestPlan, TestRun
from .scope import plan_case_ids

STAGES = ["SIT", "UAT", "PRE"]
KINDS = ["准入", "准出"]
CRITICAL_SEVERITY = ("致命", "严重")
APPROVED_REVIEW = ("已批准",)


@dataclass
class RuleDef:
    key: str
    label: str
    unit: str  # "%" 或计数单位
    op: str  # ">=" 达标方向
    hint: str


RULE_LIST = [
    RuleDef("case_total_min", "纳入用例数不少于", "条", ">=", "范围圈选过少会导致统计失真"),
    RuleDef("executed_rate_min", "执行率不低于", "%", ">=", "已执行用例占圈选用例的比例"),
    RuleDef("pass_rate_min", "通过率不低于", "%", ">=", "以圈选范围内每条用例的最新一次结果计"),
    RuleDef("failed_max", "失败用例不超过", "条", "<=", "仍处于失败状态的用例数"),
    RuleDef("blocked_max", "阻塞用例不超过", "条", "<=", "因环境或依赖被阻塞的用例数"),
    RuleDef("pending_max", "未执行用例不超过", "条", "<=", "尚未执行的用例数"),
    RuleDef("review_approved_min", "评审通过率不低于", "%", ">=", "圈选用例中评审状态为已批准的比例"),
    RuleDef("open_defects_max", "未关闭缺陷不超过", "个", "<=", "关联本计划或本范围用例的未关闭缺陷"),
    RuleDef("open_critical_defects_max", "未关闭致命/严重缺陷不超过", "个", "<=", "准出前必须清零的高危缺陷"),
]
RULES = {r.key: r for r in RULE_LIST}


def metrics(db: Session, plan: TestPlan, stage: str) -> dict:
    case_ids = plan_case_ids(db, plan)
    total = len(case_ids)

    runs = list(
        db.execute(
            select(TestRun)
            .where(TestRun.plan_id == plan.id, TestRun.stage == stage)
            .order_by(TestRun.id.desc())
        ).scalars()
    )
    latest: dict[int, str] = {}
    for r in runs:
        latest.setdefault(r.testcase_id, r.status)

    passed = failed = blocked = 0
    for cid in case_ids:
        st = latest.get(cid, "未执行")
        if st == "通过":
            passed += 1
        elif st == "失败":
            failed += 1
        elif st == "阻塞":
            blocked += 1
    pending = total - passed - failed - blocked

    approved = 0
    if case_ids:
        approved = sum(
            1
            for (status,) in db.execute(
                select(TestCase.review_status).where(TestCase.id.in_(case_ids))
            )
            if status in APPROVED_REVIEW
        )

    case_id_set = set(case_ids)
    open_defects = 0
    open_critical = 0
    for d in db.execute(select(Defect).where(Defect.project_id == plan.project_id, Defect.status != "关闭")).scalars():
        if d.plan_id == plan.id or (d.testcase_id and d.testcase_id in case_id_set):
            open_defects += 1
            if d.severity in CRITICAL_SEVERITY:
                open_critical += 1

    def pct(n: int) -> float:
        return round(n / total * 100, 1) if total else 0.0

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "pending": pending,
        "pass_rate": pct(passed),
        "executed_rate": pct(total - pending),
        "review_approved_rate": pct(approved),
        "open_defects": open_defects,
        "open_critical_defects": open_critical,
    }


def _actual(rule_key: str, m: dict):
    return {
        "case_total_min": m["total"],
        "executed_rate_min": m["executed_rate"],
        "pass_rate_min": m["pass_rate"],
        "failed_max": m["failed"],
        "blocked_max": m["blocked"],
        "pending_max": m["pending"],
        "review_approved_min": m["review_approved_rate"],
        "open_defects_max": m["open_defects"],
        "open_critical_defects_max": m["open_critical_defects"],
    }[rule_key]


def evaluate(db: Session, plan: TestPlan, stage: str, kind: str) -> dict:
    """返回 {stage, kind, configured, passed, items:[{rule,label,expected,actual,ok,unit}]}"""
    gates = list(
        db.execute(
            select(StageGate).where(
                StageGate.project_id == plan.project_id,
                StageGate.stage == stage,
                StageGate.kind == kind,
                StageGate.enabled.is_(True),
            ).order_by(StageGate.id)
        ).scalars()
    )
    m = metrics(db, plan, stage)
    items = []
    for g in gates:
        rule = RULES.get(g.rule)
        if not rule:
            items.append({
                "rule": g.rule, "label": f"未知规则[{g.rule}]", "unit": "",
                "expected": "-", "actual": "-", "ok": False, "hint": "该规则已下线,请删除或替换",
            })
            continue
        actual = _actual(rule.key, m)
        ok = actual >= g.threshold if rule.op == ">=" else actual <= g.threshold
        items.append({
            "rule": rule.key, "label": rule.label, "unit": rule.unit,
            "expected": f"{rule.op} {g.threshold}{rule.unit}",
            "actual": f"{actual}{rule.unit}",
            "ok": ok, "hint": rule.hint,
        })
    return {
        "stage": stage,
        "kind": kind,
        "configured": bool(gates),
        "passed": all(i["ok"] for i in items),
        "items": items,
        "metrics": m,
    }


def failures_text(results: list[dict]) -> str:
    parts = []
    for res in results:
        for i in res["items"]:
            if not i["ok"]:
                parts.append(f"[{res['stage']}·{res['kind']}] {i['label']} {i['expected']},实际 {i['actual']}")
    return ";".join(parts)
