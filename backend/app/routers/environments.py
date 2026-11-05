"""测试环境台账:项目维度的环境配置,执行记录按环境归属。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_project_access
from ..logger import log_op
from ..models import Project, TestEnvironment, TestPlan, TestRun, TestCase, User
from ..schemas import EnvCreate, EnvOut, EnvUpdate

router = APIRouter(prefix="/api/environments", tags=["测试环境"], dependencies=[Depends(get_current_user)])

VALID_STAGE = ("SIT", "UAT", "PRE")
VALID_STATUS = ("可用", "占用中", "维护中", "已停用")


def _to_out(rows: list[TestEnvironment], db: Session) -> list[EnvOut]:
    if not rows:
        return []
    ids = [e.id for e in rows]
    owner_map = {
        u.id: (u.display_name or u.username)
        for u in db.execute(select(User).where(User.id.in_([e.owner_id for e in rows if e.owner_id] or [0]))).scalars()
    }
    stat_rows = db.execute(
        select(TestRun.env_id, func.count(), func.sum(TestRun.status == "失败"), func.sum(TestRun.status == "阻塞"))
        .where(TestRun.env_id.in_(ids))
        .group_by(TestRun.env_id)
    ).all()
    stat = {eid: {"total": t or 0, "failed": f or 0, "blocked": b or 0} for eid, t, f, b in stat_rows}
    out = []
    for e in rows:
        item = EnvOut.model_validate(e)
        item.owner_name = owner_map.get(e.owner_id, "") if e.owner_id else ""
        item.run_count = stat.get(e.id, {}).get("total", 0)
        item.failed_count = stat.get(e.id, {}).get("failed", 0) + stat.get(e.id, {}).get("blocked", 0)
        out.append(item)
    return out


def _validate(payload: EnvCreate | EnvUpdate, partial: bool = False):
    stage = getattr(payload, "stage", None)
    status = getattr(payload, "status", None)
    if partial and stage is None and status is None:
        return
    if stage and stage not in VALID_STAGE:
        raise HTTPException(status_code=400, detail=f"阶段只能是 {'/'.join(VALID_STAGE)}")
    if status and status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail=f"状态只能是 {'/'.join(VALID_STATUS)}")
    if not partial and not (payload.name or "").strip():
        raise HTTPException(status_code=400, detail="环境名称不能为空")


@router.get("", response_model=list[EnvOut])
def list_envs(project_id: int, stage: str | None = None, status: str | None = None,
              db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    require_project_access(project_id, db, current)
    q = select(TestEnvironment).where(TestEnvironment.project_id == project_id)
    if stage:
        q = q.where(TestEnvironment.stage == stage)
    if status:
        q = q.where(TestEnvironment.status == status)
    rows = list(db.execute(q.order_by(TestEnvironment.stage, TestEnvironment.id)).scalars())
    return _to_out(rows, db)


@router.post("", response_model=EnvOut)
def create_env(payload: EnvCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not db.get(Project, payload.project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    require_project_access(payload.project_id, db, current)
    _validate(payload)
    dup = db.execute(
        select(TestEnvironment).where(TestEnvironment.project_id == payload.project_id,
                                      TestEnvironment.name == payload.name.strip())
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=400, detail=f"环境「{payload.name}」已存在")
    if payload.owner_id and not db.get(User, payload.owner_id):
        raise HTTPException(status_code=400, detail="负责人不存在")
    env = TestEnvironment(**{**payload.model_dump(), "name": payload.name.strip()})
    db.add(env)
    db.commit()
    db.refresh(env)
    log_op(db, current, "新增", target=f"环境#{env.id} {env.name}", detail=f"{env.stage} {env.status}")
    return _to_out([env], db)[0]


@router.put("/{env_id}", response_model=EnvOut)
def update_env(env_id: int, payload: EnvUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    env = db.get(TestEnvironment, env_id)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")
    require_project_access(env.project_id, db, current)
    data = payload.model_dump(exclude_unset=True)
    _validate(payload, partial=True)
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="环境名称不能为空")
        dup = db.execute(
            select(TestEnvironment).where(TestEnvironment.project_id == env.project_id,
                                          TestEnvironment.name == name,
                                          TestEnvironment.id != env_id)
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=400, detail=f"环境「{name}」已存在")
        data["name"] = name
    if data.get("owner_id") and not db.get(User, data["owner_id"]):
        raise HTTPException(status_code=400, detail="负责人不存在")
    for k, v in data.items():
        setattr(env, k, v)
    db.commit()
    db.refresh(env)
    log_op(db, current, "编辑", target=f"环境#{env.id} {env.name}", detail=f"{env.stage} {env.status}")
    return _to_out([env], db)[0]


@router.delete("/{env_id}")
def delete_env(env_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    env = db.get(TestEnvironment, env_id)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")
    require_project_access(env.project_id, db, current)
    used = db.execute(select(func.count()).select_from(TestRun).where(TestRun.env_id == env_id)).scalar_one()
    if used:
        raise HTTPException(
            status_code=400,
            detail=f"该环境已被 {used} 条执行记录引用,请改为「已停用」而不是删除,以保留执行追溯链",
        )
    desc = f"环境#{env.id} {env.name}"
    db.delete(env)
    db.commit()
    log_op(db, current, "删除", target=desc)
    return {"ok": True}


@router.get("/{env_id}/runs")
def env_runs(env_id: int, plan_id: int | None = None, page_size: int = 50,
             db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """某环境的执行记录(默认取最近 50 条),用于从环境反查问题"""
    env = db.get(TestEnvironment, env_id)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")
    require_project_access(env.project_id, db, current)
    q = select(TestRun).where(TestRun.env_id == env_id)
    if plan_id:
        q = q.where(TestRun.plan_id == plan_id)
    rows = list(db.execute(q.order_by(TestRun.id.desc()).limit(min(page_size, 200))).scalars())
    case_map = {
        cid: title
        for cid, title in db.execute(select(TestCase.id, TestCase.title).where(
            TestCase.id.in_([r.testcase_id for r in rows] or [0])
        )).all()
    }
    plan_map = {
        p.id: p.version
        for p in db.execute(select(TestPlan).where(TestPlan.id.in_([r.plan_id for r in rows if r.plan_id] or [0]))).scalars()
    }
    return {
        "env": {"id": env.id, "name": env.name, "stage": env.stage, "status": env.status},
        "items": [
            {
                "run_id": r.id,
                "testcase_id": r.testcase_id,
                "testcase_title": case_map.get(r.testcase_id, ""),
                "plan_id": r.plan_id,
                "plan_version": plan_map.get(r.plan_id, ""),
                "stage": r.stage,
                "status": r.status,
                "remark": r.remark,
                "executed_at": r.executed_at.isoformat() if r.executed_at else None,
            }
            for r in rows
        ],
    }
