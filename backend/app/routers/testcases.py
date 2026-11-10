import io

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dictionaries import check_400
from ..deps import accessible_project_ids, get_current_user, require_project_access
from ..logger import log_op
from ..models import Defect, ProjectRole, TestCase, TestCaseStep, TestCaseVersion, TestPlan, TestRun, User
from ..notify import emit
from ..schemas import TestCaseCreate, TestCaseOut, TestCaseStepIn, TestCaseStepOut, TestCaseUpdate

router = APIRouter(prefix="/api/testcases", tags=["测试用例"], dependencies=[Depends(get_current_user)])


class ReviewSubmit(BaseModel):
    reviewer_id: int | None = None  # 指定评审人;不传则提醒项目上的测试负责人


def _review_pool(db: Session, project_id: int) -> list[int]:
    """项目上的测试负责人/项目经理,作为未指定评审人时的默认提醒对象"""
    rows = list(
        db.execute(
            select(ProjectRole).where(
                ProjectRole.project_id == project_id,
                ProjectRole.role.in_(["manager", "test_lead"]),
            )
        ).scalars()
    )
    ids = {r.user_id for r in rows}
    return [i for i in sorted(ids) if i]


def _save_version(db: Session, tc: TestCase, user: User, summary: str = ""):
    latest = db.execute(
        select(TestCaseVersion)
        .where(TestCaseVersion.testcase_id == tc.id)
        .order_by(TestCaseVersion.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    next_ver = (latest.version + 1) if latest else 1
    v = TestCaseVersion(
        testcase_id=tc.id, version=next_ver,
        module=tc.module, title=tc.title,
        precondition=tc.precondition, steps=tc.steps,
        expected=tc.expected, priority=tc.priority,
        changed_by=user.id, change_summary=summary,
    )
    db.add(v)


@router.get("/export")
def export_testcases(
    project_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """导出某项目下所有测试用例为 Excel"""
    require_project_access(project_id, db, current)
    cases = list(
        db.execute(select(TestCase).where(TestCase.project_id == project_id).order_by(TestCase.id.asc())).scalars()
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "测试用例"
    hdr_font = Font(bold=True, color="FFFFFF")
    hdr_fill = PatternFill("solid", fgColor="4472C4")
    cols = ["ID", "模块", "用例标题", "优先级", "前置条件", "测试步骤", "预期结果", "当前状态", "创建时间"]
    for c, h in enumerate(cols, start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = hdr_font
        cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for r, tc in enumerate(cases, start=2):
        ws.cell(row=r, column=1, value=tc.id)
        ws.cell(row=r, column=2, value=tc.module)
        ws.cell(row=r, column=3, value=tc.title)
        ws.cell(row=r, column=4, value=tc.priority)
        ws.cell(row=r, column=5, value=tc.precondition)
        ws.cell(row=r, column=6, value=tc.steps)
        ws.cell(row=r, column=7, value=tc.expected)
        ws.cell(row=r, column=8, value=tc.status)
        ws.cell(row=r, column=9, value=tc.created_at.strftime("%Y-%m-%d %H:%M") if tc.created_at else "")
    widths = [6, 14, 30, 8, 24, 30, 24, 12, 18]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    log_op(db, current, "导出", target=f"用例列表 项目#{project_id}", detail=f"{len(cases)}条")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=testcases.xlsx"},
    )


@router.get("/stats")
def stats(
    project_id: int | None = None,
    plan_id: int | None = None,
    stage: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    accessible = accessible_project_ids(db, current)
    q = select(TestCase)
    if project_id is not None:
        require_project_access(project_id, db, current)
        q = q.where(TestCase.project_id == project_id)
    elif accessible is not None:
        if not accessible:
            return {"total": 0, "by_status": {"未执行": 0, "通过": 0, "失败": 0, "阻塞": 0}, "by_priority": {}}
        q = q.where(TestCase.project_id.in_(accessible))
    cases = list(db.execute(q).scalars())
    total = len(cases)

    by_priority: dict[str, int] = {}
    for c in cases:
        by_priority[c.priority] = by_priority.get(c.priority, 0) + 1

    by_status: dict[str, int] = {"未执行": 0, "通过": 0, "失败": 0, "阻塞": 0}
    if plan_id and stage:
        case_ids = [c.id for c in cases]
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
        for cid in case_ids:
            st = latest.get(cid, "未执行")
            by_status[st] = by_status.get(st, 0) + 1
    else:
        by_status["未执行"] = total

    return {"total": total, "by_status": by_status, "by_priority": by_priority}


@router.get("")
def list_testcases(
    project_id: int | None = None,
    plan_id: int | None = None,
    stage: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    review_status: str | None = None,
    keyword: str | None = None,
    all_stages: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    accessible = accessible_project_ids(db, current)
    q = select(TestCase)
    if project_id is not None:
        require_project_access(project_id, db, current)
        q = q.where(TestCase.project_id == project_id)
    elif accessible is not None:
        if not accessible:
            return {"total": 0, "page": page, "page_size": page_size, "items": []}
        q = q.where(TestCase.project_id.in_(accessible))
    if priority:
        q = q.where(TestCase.priority == priority)
    if review_status:
        q = q.where(TestCase.review_status == review_status)
    if keyword:
        kw = f"%{keyword}%"
        q = q.where(TestCase.title.like(kw) | TestCase.module.like(kw))

    all_rows = list(db.execute(q.order_by(TestCase.id.desc())).scalars())

    STAGES = ["SIT", "UAT", "PRE"]

    # ---- all_stages 模式:超管总览,返回三阶段各自状态(忽略 stage 参数) ----
    if all_stages and current.role == "admin" and plan_id:
        plan = db.get(TestPlan, plan_id)
        cur_stage = plan.current_stage if plan else "SIT"
        stage_maps: dict[str, dict[int, dict]] = {}
        for st in STAGES:
            runs = list(
                db.execute(
                    select(TestRun)
                    .where(TestRun.plan_id == plan_id, TestRun.stage == st)
                    .order_by(TestRun.id.desc())
                ).scalars()
            )
            m: dict[int, dict] = {}
            for r in runs:
                if r.testcase_id not in m:
                    m[r.testcase_id] = {"status": r.status, "screenshot": r.screenshot}
            stage_maps[st] = m

        items_all = []
        for r in all_rows:
            # Manually construct dict to handle None values
            data_dict = {
                "id": r.id,
                "project_id": r.project_id,
                "module": r.module,
                "title": r.title,
                "precondition": r.precondition or "",
                "steps": r.steps or "",
                "expected": r.expected or "",
                "priority": r.priority,
                "status": r.status,
                "review_status": r.review_status or "草稿",
                "reviewer_id": r.reviewer_id,
                "reviewer_name": "",
                "review_comment": r.review_comment or "",
                "reviewed_at": r.reviewed_at,
                "created_by": r.created_by,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            d = TestCaseOut.model_validate(data_dict).model_dump(mode="json")
            if r.reviewer_id:
                reviewer = db.get(User, r.reviewer_id)
                d["reviewer_name"] = reviewer.display_name or reviewer.username if reviewer else ""
            for st in STAGES:
                info = stage_maps[st].get(r.id)
                d[f"{st.lower()}_status"] = info["status"] if info else "未执行"
                d[f"{st.lower()}_screenshot"] = info["screenshot"] if info else ""
            d["latest_status"] = d.get(f"{cur_stage.lower()}_status", "未执行")
            items_all.append(d)

        if status:
            items_all = [it for it in items_all if any(it.get(f"{s.lower()}_status") == status for s in STAGES)]
        total = len(items_all)
        page_items = items_all[(page - 1) * page_size : page * page_size]
        return {"total": total, "page": page, "page_size": page_size, "items": page_items, "all_stages": True}

    # ---- 普通模式:单阶段状态 ----
    latest_map: dict[int, dict] = {}
    if plan_id and stage:
        runs = list(
            db.execute(
                select(TestRun)
                .where(TestRun.plan_id == plan_id, TestRun.stage == stage)
                .order_by(TestRun.id.desc())
            ).scalars()
        )
        for r in runs:
            if r.testcase_id not in latest_map:
                latest_map[r.testcase_id] = {
                    "latest_status": r.status,
                    "latest_run_id": r.id,
                    "latest_screenshot": r.screenshot,
                }

    items_all = []
    for r in all_rows:
        # Manually construct dict to handle None values
        data_dict = {
            "id": r.id,
            "project_id": r.project_id,
            "module": r.module,
            "title": r.title,
            "precondition": r.precondition or "",
            "steps": r.steps or "",
            "expected": r.expected or "",
            "priority": r.priority,
            "status": r.status,
            "review_status": r.review_status or "草稿",
            "reviewer_id": r.reviewer_id,
            "reviewer_name": "",
            "review_comment": r.review_comment or "",
            "reviewed_at": r.reviewed_at,
            "created_by": r.created_by,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        d = TestCaseOut.model_validate(data_dict).model_dump(mode="json")
        # 填充评审人姓名
        if r.reviewer_id:
            reviewer = db.get(User, r.reviewer_id)
            d["reviewer_name"] = reviewer.display_name or reviewer.username if reviewer else ""
        lr = latest_map.get(r.id, {})
        d["latest_status"] = lr.get("latest_status", "未执行")
        d["latest_run_id"] = lr.get("latest_run_id")
        d["latest_screenshot"] = lr.get("latest_screenshot", "")
        items_all.append(d)

    if status:
        items_all = [it for it in items_all if it["latest_status"] == status]

    total = len(items_all)
    page_items = items_all[(page - 1) * page_size : page * page_size]
    return {"total": total, "page": page, "page_size": page_size, "items": page_items, "all_stages": False}


@router.post("", response_model=TestCaseOut)
def create_testcase(payload: TestCaseCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_project_access(payload.project_id, db, current)
    check_400(db, "case_priority", payload.priority, payload.project_id)
    tc = TestCase(
        project_id=payload.project_id,
        module=payload.module,
        title=payload.title,
        precondition=payload.precondition,
        steps=payload.steps,
        expected=payload.expected,
        priority=payload.priority,
        status="未执行",
        created_by=current.id,
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    _save_version(db, tc, current, "初始创建")
    db.commit()
    log_op(db, current, "创建", target=f"用例#{tc.id} {tc.title}", detail=f"项目#{payload.project_id}")
    return tc


@router.get("/{tcid}", response_model=TestCaseOut)
def get_testcase(tcid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)
    return tc


@router.put("/{tcid}", response_model=TestCaseOut)
def update_testcase(tcid: int, payload: TestCaseUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)
    data = payload.model_dump(exclude_unset=True)
    if "priority" in data:
        check_400(db, "case_priority", data["priority"], tc.project_id, current=tc.priority)
    for k, v in data.items():
        setattr(tc, k, v)
    _save_version(db, tc, current, "编辑保存")
    db.commit()
    db.refresh(tc)
    log_op(db, current, "编辑", target=f"用例#{tc.id} {tc.title}")
    return tc


@router.delete("/{tcid}")
def delete_testcase(tcid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)
    title = tc.title
    db.delete(tc)
    db.commit()
    log_op(db, current, "删除", target=f"用例#{tcid} {title}")
    return {"ok": True}


# ===================== 结构化步骤 =====================
def _steps_of(db: Session, tcid: int) -> list[TestCaseStep]:
    return list(
        db.execute(
            select(TestCaseStep).where(TestCaseStep.testcase_id == tcid).order_by(TestCaseStep.step_no.asc(), TestCaseStep.id.asc())
        ).scalars()
    )


@router.get("/{tcid}/steps", response_model=list[TestCaseStepOut])
def get_steps(tcid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)
    return _steps_of(db, tcid)


@router.put("/{tcid}/steps", response_model=list[TestCaseStepOut])
def save_steps(
    tcid: int,
    payload: list[TestCaseStepIn] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """整体覆盖用例步骤列表;steps 自由文本保留不动,前端有结构化步骤时优先展示步骤"""
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)

    db.execute(TestCaseStep.__table__.delete().where(TestCaseStep.testcase_id == tcid))
    rows = []
    for i, s in enumerate(payload, start=1):
        row = TestCaseStep(
            testcase_id=tcid,
            step_no=s.step_no or i,
            action=s.action or "",
            expected=s.expected or "",
            data=s.data or "",
        )
        db.add(row)
        rows.append(row)
    db.commit()
    log_op(db, current, "编辑", target=f"用例#{tcid} {tc.title}", detail=f"步骤{len(rows)}条")
    return _steps_of(db, tcid)


# ---------- 评审流程 ----------
VALID_REVIEW_STATUS = {"草稿", "评审中", "已批准", "已驳回"}


@router.post("/{tcid}/submit-review")
def submit_review(
    tcid: int,
    payload: ReviewSubmit | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)
    if tc.review_status not in ("草稿", "已驳回"):
        raise HTTPException(status_code=400, detail=f"当前状态[{tc.review_status}]不允许提交评审,只有草稿或被驳回的用例可以提交评审")
    reviewer_id = payload.reviewer_id if payload else None
    if reviewer_id:
        reviewer = db.get(User, reviewer_id)
        if not reviewer or not reviewer.is_active:
            raise HTTPException(status_code=400, detail="评审人不存在或已停用")
        if reviewer.id == tc.created_by:
            raise HTTPException(status_code=400, detail="评审人不能是用例编写人")
    tc.review_status = "评审中"
    tc.reviewer_id = reviewer_id
    tc.review_comment = ""
    tc.reviewed_at = None
    db.commit()
    db.refresh(tc)
    log_op(db, current, "提交评审", target=f"用例#{tc.id} {tc.title}")

    # 没有指定评审人时,通知项目上的测试负责人/项目经理,避免评审请求石沉大海
    targets = [reviewer_id] if reviewer_id else _review_pool(db, tc.project_id)
    who = current.display_name or current.username
    emit(
        db, [t for t in targets if t != current.id], "review_assigned",
        f"用例待评审: {tc.title}",
        f"提交人: {who}, 优先级: {tc.priority}",
        f"/testcases?project_id={tc.project_id}&focus={tc.id}",
    )
    return tc


@router.post("/{tcid}/approve")
def approve_testcase(
    tcid: int,
    comment: str = Body("", embed=True),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)
    if tc.review_status != "评审中":
        raise HTTPException(status_code=400, detail="只有评审中的用例才能被批准")
    tc.review_status = "已批准"
    tc.reviewer_id = current.id
    tc.review_comment = comment
    tc.reviewed_at = datetime.now()
    db.commit()
    db.refresh(tc)
    log_op(db, current, "批准", target=f"用例#{tc.id} {tc.title}")
    who = current.display_name or current.username
    emit(
        db, [tc.created_by], "review_result",
        f"用例评审通过: {tc.title}",
        f"评审人: {who}" + (f", 意见: {comment}" if comment else ""),
        f"/testcases?project_id={tc.project_id}&focus={tc.id}",
    )
    return tc


@router.post("/{tcid}/reject")
def reject_testcase(
    tcid: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)
    if tc.review_status != "评审中":
        raise HTTPException(status_code=400, detail="只有评审中的用例才能被驳回")
    comment = body.get("comment", "")
    if not comment.strip():
        raise HTTPException(status_code=400, detail="驳回时必须填写意见")
    tc.review_status = "已驳回"
    tc.reviewer_id = current.id
    tc.review_comment = comment
    tc.reviewed_at = datetime.now()
    db.commit()
    db.refresh(tc)
    log_op(db, current, "驳回", target=f"用例#{tc.id} {tc.title}", detail=comment[:50])
    who = current.display_name or current.username
    emit(
        db, [tc.created_by], "review_result",
        f"用例被驳回: {tc.title}",
        f"评审人: {who}, 意见: {comment}",
        f"/testcases?project_id={tc.project_id}&focus={tc.id}",
    )
    return tc


@router.get("/{tcid}/traceability")
def testcase_traceability(
    tcid: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取用例的完整追溯信息：关联的计划、执行记录、缺陷"""
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)

    # 关联的执行记录（含计划信息）
    runs = list(
        db.execute(
            select(TestRun).where(TestRun.testcase_id == tcid).order_by(TestRun.executed_at.desc())
        ).scalars()
    )
    runs_with_plan = []
    for r in runs:
        plan = db.get(TestPlan, r.plan_id) if r.plan_id else None
        runs_with_plan.append({
            "id": r.id,
            "status": r.status,
            "stage": r.stage,
            "remark": r.remark,
            "screenshot": r.screenshot,
            "executed_at": r.executed_at.isoformat() if r.executed_at else None,
            "plan_id": r.plan_id,
            "plan_version": plan.version if plan else None,
        })

    # 关联的缺陷: 直接挂在用例上的 + 由该用例执行记录产生的
    run_ids = [r.id for r in runs]
    conds = [Defect.testcase_id == tcid]
    if run_ids:
        conds.append(Defect.run_id.in_(run_ids))
    defects = list(
        db.execute(
            select(Defect).where(or_(*conds)).order_by(Defect.created_at.desc())
        ).scalars()
    )
    defect_list = [{
        "id": d.id,
        "title": d.title,
        "severity": d.severity,
        "priority": d.priority,
        "status": d.status,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    } for d in defects]

    # 关联的需求
    from ..models import requirement_testcases
    req_ids = [
        row.requirement_id
        for row in db.execute(
            select(requirement_testcases.c.requirement_id).where(requirement_testcases.c.testcase_id == tcid)
        ).all()
    ]
    from ..models import Requirement
    requirements = []
    for rid in req_ids:
        req = db.get(Requirement, rid)
        if req:
            requirements.append({
                "id": req.id,
                "req_no": req.req_no,
                "title": req.title,
                "priority": req.priority,
                "status": req.status,
            })

    return {
        "testcase_id": tcid,
        "testcase_title": tc.title,
        "runs": runs_with_plan,
        "defects": defect_list,
        "requirements": requirements,
    }
