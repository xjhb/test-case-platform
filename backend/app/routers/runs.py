from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_project_access
from ..logger import log_op
from ..models import StepResult, TestCase, TestCaseStep, TestPlan, TestRun, User
from ..schemas import StepResultIn, TestRunCreate, TestRunOut
from ..scope import in_scope

router = APIRouter(prefix="/api/runs", tags=["测试执行"], dependencies=[Depends(get_current_user)])

VALID_STATUS = {"通过", "失败", "阻塞"}
VALID_STEP_STATUS = {"通过", "失败", "阻塞", "未执行"}
VALID_STAGES = ["SIT", "UAT", "PRE"]


def _derive_status(step_statuses: list[str]) -> str:
    """整条用例结果由步骤结果推导:任一失败=失败;否则有阻塞=阻塞;否则有通过且其余未执行为空=通过"""
    if "失败" in step_statuses:
        return "失败"
    if "阻塞" in step_statuses:
        return "阻塞"
    if "通过" in step_statuses:
        return "通过"
    return "未执行"


@router.post("", response_model=TestRunOut)
def create_run(payload: TestRunCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
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
    if not in_scope(db, plan, tc.id):
        raise HTTPException(status_code=400, detail=f"用例#{tc.id} 未纳入计划#{plan.id}的用例范围,请先圈选后再执行")

    # 逐步骤执行:用例状态由步骤结果推导,忽略前端传入的 status
    step_rows = list(
        db.execute(
            select(TestCaseStep).where(TestCaseStep.testcase_id == tc.id).order_by(TestCaseStep.step_no.asc())
        ).scalars()
    )
    step_map = {s.id: s for s in step_rows}
    derived_status = payload.status
    if payload.step_results:
        bad = [r.step_id for r in payload.step_results if r.step_id not in step_map]
        if bad:
            raise HTTPException(status_code=400, detail=f"步骤不存在或不属于用例#{tc.id}: {', '.join(map(str, bad))}")
        bad_st = [r.status for r in payload.step_results if r.status not in VALID_STEP_STATUS]
        if bad_st:
            raise HTTPException(
                status_code=400, detail=f"步骤状态只能是 {'/'.join(sorted(VALID_STEP_STATUS))}, 收到: {', '.join(map(str, set(bad_st)))}"
            )
        derived_status = _derive_status([r.status for r in payload.step_results])
    if derived_status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail="执行状态只能是 通过/失败/阻塞")
    if derived_status == "通过":
        has_shot = payload.screenshot or any(r.screenshot for r in payload.step_results)
        if not has_shot:
            raise HTTPException(status_code=400, detail='未上传图片,选择"通过"时必须上传成功截图')

    # 三阶段可独立执行:SIT/UAT/PRE 不再要求前置阶段完成,
    # 由前端显式指定 stage;未传时退回计划当前阶段(兼容旧调用)。
    stage = payload.stage or plan.current_stage
    if stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"阶段只能是 {'/'.join(VALID_STAGES)}")

    run = TestRun(
        testcase_id=payload.testcase_id,
        plan_id=payload.plan_id,
        stage=stage,
        status=derived_status,
        remark=payload.remark or "",
        screenshot=payload.screenshot or "",
        executed_by=current.id,
    )
    db.add(run)
    db.flush()

    for r in payload.step_results:
        db.add(StepResult(run_id=run.id, step_id=r.step_id, status=r.status, actual=r.actual, screenshot=r.screenshot))

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
           detail=f"计划#{plan.id} 阶段{stage} 结果:{derived_status}"
                  + (f" (步骤{len(payload.step_results)}条)" if payload.step_results else ""))
    return run


@router.get("/{run_id}/step-results")
def list_step_results(run_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """某次执行的逐步骤实际结果"""
    run = db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    tc = db.get(TestCase, run.testcase_id)
    if tc:
        require_project_access(tc.project_id, db, current)
    rows = list(
        db.execute(select(StepResult).where(StepResult.run_id == run_id).order_by(StepResult.id.asc())).scalars()
    )
    step_map = {s.id: s for s in db.execute(select(TestCaseStep).where(TestCaseStep.id.in_([r.step_id for r in rows] or [0]))).scalars()}
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "step_id": r.step_id,
            "step_no": step_map[r.step_id].step_no if r.step_id in step_map else None,
            "action": step_map[r.step_id].action if r.step_id in step_map else "",
            "expected": step_map[r.step_id].expected if r.step_id in step_map else "",
            "status": r.status,
            "actual": r.actual,
            "screenshot": r.screenshot,
        }
        for r in rows
    ]


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
