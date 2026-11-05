from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_project_access
from ..gates import KINDS, RULES, RULE_LIST, STAGES, evaluate
from ..logger import log_op
from ..models import Project, StageGate, TestPlan, User
from ..schemas import StageGateCreate, StageGateOut, StageGateUpdate

router = APIRouter(prefix="/api/gates", tags=["阶段门禁"], dependencies=[Depends(get_current_user)])


def _to_out(g: StageGate) -> StageGateOut:
    rule = RULES.get(g.rule)
    return StageGateOut(
        id=g.id, project_id=g.project_id, stage=g.stage, kind=g.kind, rule=g.rule,
        rule_label=rule.label if rule else g.rule,
        unit=rule.unit if rule else "", op=rule.op if rule else "", hint=rule.hint if rule else "",
        threshold=g.threshold, enabled=g.enabled, updated_at=g.updated_at,
    )


def _validate(payload_stage, payload_kind, payload_rule):
    if payload_stage and payload_stage not in STAGES:
        raise HTTPException(status_code=400, detail=f"阶段只能是 {'/'.join(STAGES)}")
    if payload_kind and payload_kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"门禁类型只能是 {'/'.join(KINDS)}")
    if payload_rule and payload_rule not in RULES:
        raise HTTPException(status_code=400, detail=f"未知规则: {payload_rule}")


@router.get("/rules")
def list_rules():
    """规则目录,供前端渲染配置项"""
    return [{"key": r.key, "label": r.label, "unit": r.unit, "op": r.op, "hint": r.hint} for r in RULE_LIST]


@router.get("", response_model=list[StageGateOut])
def list_gates(project_id: int, stage: str | None = None, kind: str | None = None, db: Session = Depends(get_db),
               current: User = Depends(get_current_user)):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    require_project_access(project_id, db, current)
    q = select(StageGate).where(StageGate.project_id == project_id)
    if stage:
        q = q.where(StageGate.stage == stage)
    if kind:
        q = q.where(StageGate.kind == kind)
    return [_to_out(g) for g in db.execute(q.order_by(StageGate.stage, StageGate.kind, StageGate.id)).scalars()]


@router.post("", response_model=StageGateOut)
def create_gate(payload: StageGateCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not db.get(Project, payload.project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    require_project_access(payload.project_id, db, current)
    _validate(payload.stage, payload.kind, payload.rule)
    gate = StageGate(**payload.model_dump())
    db.add(gate)
    db.commit()
    db.refresh(gate)
    log_op(db, current, "新增", target=f"门禁#{gate.id} {gate.stage}{gate.kind}",
           detail=f"{RULES[gate.rule].label} {gate.threshold}{RULES[gate.rule].unit}")
    return _to_out(gate)


@router.put("/{gate_id}", response_model=StageGateOut)
def update_gate(gate_id: int, payload: StageGateUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    gate = db.get(StageGate, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="门禁规则不存在")
    require_project_access(gate.project_id, db, current)
    data = payload.model_dump(exclude_unset=True)
    _validate(data.get("stage"), data.get("kind"), data.get("rule"))
    for k, v in data.items():
        setattr(gate, k, v)
    db.commit()
    db.refresh(gate)
    log_op(db, current, "编辑", target=f"门禁#{gate.id} {gate.stage}{gate.kind}",
           detail=f"{RULES[gate.rule].label} {gate.threshold}{RULES[gate.rule].unit}")
    return _to_out(gate)


@router.delete("/{gate_id}")
def delete_gate(gate_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    gate = db.get(StageGate, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="门禁规则不存在")
    require_project_access(gate.project_id, db, current)
    desc = f"门禁#{gate.id} {gate.stage}{gate.kind}"
    db.delete(gate)
    db.commit()
    log_op(db, current, "删除", target=desc)
    return {"ok": True}


@router.get("/check")
def check_gate(plan_id: int, stage: str, kind: str | None = None, db: Session = Depends(get_db),
               current: User = Depends(get_current_user)):
    """校验某计划在某阶段的门禁;kind 不传则同时返回准入与准出"""
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_project_access(plan.project_id, db, current)
    if stage not in STAGES:
        raise HTTPException(status_code=400, detail=f"阶段只能是 {'/'.join(STAGES)}")
    kinds = [kind] if kind else KINDS
    if kind and kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"门禁类型只能是 {'/'.join(KINDS)}")
    results = [evaluate(db, plan, stage, k) for k in kinds]
    return {"plan_id": plan_id, "stage": stage, "results": results,
            "passed": all(r["passed"] for r in results)}
