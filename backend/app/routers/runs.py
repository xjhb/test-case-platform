from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_project_access
from ..logger import log_op
from ..models import TestCase, TestPlan, TestRun, User
from ..schemas import TestRunCreate, TestRunOut

router = APIRouter(prefix="/api/runs", tags=["测试执行"], dependencies=[Depends(get_current_user)])

VALID_STATUS = {"通过", "失败", "阻塞"}
VALID_STAGES = ["SIT", "UAT", "PRE"]


@router.post("", response_model=TestRunOut)
def create_run(payload: TestRunCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if payload.status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail="执行状态只能是 通过/失败/阻塞")
    if payload.status == "通过" and not payload.screenshot:
        raise HTTPException(status_code=400, detail='未上传图片,选择"通过"时必须上传成功截图')
    plan = db.get(TestPlan, payload.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="测试计划不存在")
    require_project_access(plan.project_id, db, current)
    if plan.status == "已完成":
        raise HTTPException(status_code=400, detail="计划已完成,无法继续执行")
    tc = db.get(TestCase, payload.testcase_id)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)

    # 三阶段可独立执行:SIT/UAT/PRE 不再要求前置阶段完成,
    # 由前端显式指定 stage;未传时退回计划当前阶段(兼容旧调用)。
    stage = payload.stage or plan.current_stage
    if stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"阶段只能是 {'/'.join(VALID_STAGES)}")

    run = TestRun(
        testcase_id=payload.testcase_id,
        plan_id=payload.plan_id,
        stage=stage,
        status=payload.status,
        remark=payload.remark or "",
        screenshot=payload.screenshot or "",
        executed_by=current.id,
    )
    db.add(run)
    db.flush()

    # 用例当前状态取该用例最近一次执行(不限阶段),供导出与统计使用
    latest = db.execute(
        select(TestRun)
        .where(TestRun.testcase_id == payload.testcase_id)
        .order_by(TestRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest:
        tc.status = latest.status

    db.commit()
    db.refresh(run)
    log_op(db, current, "执行", target=f"用例#{tc.id} {tc.title}",
           detail=f"计划#{plan.id} 阶段{stage} 结果:{payload.status}")
    return run


@router.get("", response_model=list[TestRunOut])
def list_runs(testcase_id: int, plan_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_project_access(plan.project_id, db, current)
    return list(
        db.execute(
            select(TestRun)
            .where(TestRun.testcase_id == testcase_id, TestRun.plan_id == plan_id)
            .order_by(TestRun.id.desc())
        ).scalars()
    )
