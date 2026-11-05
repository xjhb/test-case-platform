import re
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_project_access
from ..junit import JUnitParseError, parse_junit
from ..logger import log_op
from ..models import TestCase, TestPlan, TestRun, User
from ..scope import in_scope
from .runs import resolve_env

router = APIRouter(prefix="/api/automation", tags=["自动化集成"], dependencies=[Depends(get_current_user)])

MAX_XML_FILES = 20
# CI 命名里常带平台用例号,如 [TC-1024] / case_1024 / #1024
_CASE_ID_RE = re.compile(r"(?:tc|case|#)[\s_-]*(\d+)", re.IGNORECASE)


class AutomationResultItem(BaseModel):
    testcase_id: int
    status: str  # 通过/失败/阻塞
    remark: str = ""
    screenshot: str = ""
    duration_seconds: int | None = None  # 执行时长(秒)
    executed_at: str | None = None  # ISO格式时间,不传则用当前时间


class AutomationBatchSubmit(BaseModel):
    plan_id: int
    stage: str = "SIT"  # SIT/UAT/PRE
    env_id: int | None = None  # 执行环境,须属于该计划所属项目
    results: list[AutomationResultItem] = Field(min_length=1)
    framework: str = ""  # 自动化框架名称,如 Selenium/Playwright/Cypress
    build_number: str = ""  # 构建号


class AutomationBatchResult(BaseModel):
    total: int
    success: int
    failed: int
    errors: list[str] = []


@router.post("/batch", response_model=AutomationBatchResult)
def batch_submit_results(
    payload: AutomationBatchSubmit,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    批量提交自动化测试结果

    用于自动化测试框架(API测试/UI自动化)回写执行结果。
    支持一次提交多个用例的执行结果。
    """
    plan = db.get(TestPlan, payload.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="测试计划不存在")
    env = resolve_env(db, plan, payload.env_id)

    valid_statuses = {"通过", "失败", "阻塞"}
    success_count = 0
    failed_count = 0
    errors = []

    for item in payload.results:
        try:
            if item.status not in valid_statuses:
                errors.append(f"用例#{item.testcase_id}: 状态无效[{item.status}]")
                failed_count += 1
                continue

            tc = db.get(TestCase, item.testcase_id)
            if not tc:
                errors.append(f"用例#{item.testcase_id}: 不存在")
                failed_count += 1
                continue

            if tc.project_id != plan.project_id:
                errors.append(f"用例#{item.testcase_id}: 不属于该计划的项目")
                failed_count += 1
                continue

            if not in_scope(db, plan, tc.id):
                errors.append(f"用例#{item.testcase_id}: 未纳入计划#{plan.id}的用例范围")
                failed_count += 1
                continue

            executed_at = datetime.now()
            if item.executed_at:
                try:
                    executed_at = datetime.fromisoformat(item.executed_at.replace("Z", "+00:00"))
                except Exception:
                    pass

            remark = item.remark
            if payload.framework:
                remark = f"[{payload.framework}] {remark}"
            if payload.build_number:
                remark = f"[Build#{payload.build_number}] {remark}"

            run = TestRun(
                testcase_id=item.testcase_id,
                plan_id=payload.plan_id,
                stage=payload.stage,
                status=item.status,
                remark=remark.strip(),
                screenshot=item.screenshot,
                executed_by=current.id,
                executed_at=executed_at,
                duration_seconds=item.duration_seconds,
                env_id=env.id if env else None,
            )
            db.add(run)
            success_count += 1
        except Exception as e:
            errors.append(f"用例#{item.testcase_id}: {str(e)}")
            failed_count += 1

    db.commit()
    log_op(
        db,
        current,
        "自动化提交",
        target=f"计划#{payload.plan_id}",
        detail=f"{payload.framework} Build#{payload.build_number}: 成功{success_count}条,失败{failed_count}条",
    )

    return AutomationBatchResult(
        total=len(payload.results),
        success=success_count,
        failed=failed_count,
        errors=errors[:20],
    )


def _match_case(name: str, by_title: dict, by_id: dict) -> tuple[TestCase | None, str]:
    """按标题精确匹配,匹配不到再尝试从名称里提取平台用例编号"""
    tc = by_title.get(name.strip().lower())
    if tc:
        return tc, ""
    m = _CASE_ID_RE.search(name)
    if m:
        tc = by_id.get(int(m.group(1)))
        if tc:
            return tc, ""
        return None, f"名称中的用例编号 #{m.group(1)} 在本项目不存在"
    return None, "按用例标题和编号均未匹配到平台用例"


@router.post("/import-xml")
async def import_junit_xml(
    files: list[UploadFile] = File(..., description="JUnit XML 结果文件,可多个"),
    plan_id: int = Form(...),
    stage: str = Form("SIT"),
    framework: str = Form("", description="自动化框架,如 Selenium/Playwright"),
    build_number: str = Form("", description="CI 构建号"),
    env_id: int | None = Form(None, description="执行环境ID,须属于该计划所属项目"),
    dry_run: bool = Form(False, description="只解析和匹配,不落库"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """解析 CI 产出的 JUnit XML,按用例标题/编号匹配后批量写入执行记录"""
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="测试计划不存在")
    require_project_access(plan.project_id, db, current)
    if stage not in {"SIT", "UAT", "PRE"}:
        raise HTTPException(status_code=400, detail="阶段只能是 SIT/UAT/PRE")
    env = resolve_env(db, plan, env_id)
    if len(files) > MAX_XML_FILES:
        raise HTTPException(status_code=400, detail=f"单次最多上传 {MAX_XML_FILES} 个 XML 文件")

    cases = list(db.execute(select(TestCase).where(TestCase.project_id == plan.project_id)).scalars())
    by_title: dict[str, TestCase] = {}
    for c in cases:
        by_title.setdefault(c.title.strip().lower(), c)
    by_id = {c.id: c for c in cases}

    parsed: list = []
    unmatched: list[dict] = []
    file_errors: list[dict] = []
    suites: list[dict] = []

    for f in files:
        data = await f.read()
        fname = f.filename or "unknown.xml"
        try:
            report = parse_junit(data, fname)
        except JUnitParseError as e:
            file_errors.append({"file": fname, "error": str(e)})
            continue
        suites.extend(report.suites)
        for case in report.cases:
            parsed.append(case)

    for case in parsed:
        tc, reason = _match_case(case.name, by_title, by_id)
        if tc is None:
            unmatched.append({
                "name": case.name, "classname": case.classname, "file": case.file_name,
                "status": case.status, "reason": reason or "用例标题未匹配",
            })
        elif not in_scope(db, plan, tc.id):
            unmatched.append({
                "name": case.name, "classname": case.classname, "file": case.file_name,
                "status": case.status, "testcase_id": tc.id,
                "reason": f"用例#{tc.id} 不属于计划#{plan.id}的用例范围",
            })
        else:
            case.testcase_id = tc.id  # type: ignore[attr-defined]

    by_status = {"通过": 0, "失败": 0, "阻塞": 0}
    for case in parsed:
        if case.testcase_id:
            by_status[case.status] = by_status.get(case.status, 0) + 1

    result = {
        "plan_id": plan.id,
        "stage": stage,
        "dry_run": dry_run,
        "files": [f.filename or "unknown.xml" for f in files],
        "total": len(parsed),
        "matched": sum(1 for c in parsed if c.testcase_id),
        "imported": 0,
        "by_status": by_status,
        "unmatched": unmatched[:100],
        "unmatched_total": len(unmatched),
        "file_errors": file_errors,
        "suites": suites[:50],
    }
    if not parsed:
        raise HTTPException(status_code=400, detail="未解析到任何 testcase,请检查 JUnit XML 内容")
    if dry_run:
        return result

    imported = 0
    last_status: dict[int, str] = {}
    for case in parsed:
        tc_id = case.testcase_id
        if not tc_id:
            continue
        tag = framework or "JUnit"
        parts = [f"[{tag}]"]
        if build_number:
            parts.append(f"[Build#{build_number}]")
        if case.suite:
            parts.append(f"suite={case.suite}")
        if case.classname and case.classname != case.suite:
            parts.append(f"class={case.classname}")
        if case.message:
            parts.append(case.message[:500])
        db.add(TestRun(
            testcase_id=tc_id,
            plan_id=plan.id,
            stage=stage,
            status=case.status,
            remark=" ".join(parts)[:2000],
            executed_by=current.id,
            duration_seconds=case.duration_seconds or None,
            env_id=env.id if env else None,
        ))
        last_status[tc_id] = case.status
        imported += 1

    # 用例当前状态跟随最近一次执行,和手工执行口径保持一致
    for tc_id, st in last_status.items():
        tc = by_id.get(tc_id)
        if tc:
            tc.status = st

    db.commit()
    log_op(
        db, current, "导入",
        target=f"计划#{plan.id} {stage}",
        detail=f"JUnit XML 导入 {len(result['files'])} 个文件: 匹配 {result['matched']}, 写入 {imported}, 未匹配 {len(unmatched)}",
    )
    result["imported"] = imported
    return result


@router.get("/guide")
def automation_guide():
    """
    返回自动化集成指南
    """
    return {
        "title": "自动化测试集成指南",
        "description": "通过API将自动化测试结果回写到测管平台",
        "api_endpoint": "/api/automation/batch",
        "method": "POST",
        "authentication": "Bearer Token (从登录接口获取)",
        "request_body": {
            "plan_id": "测试计划ID (整数)",
            "stage": "执行阶段: SIT/UAT/PRE (默认SIT)",
            "framework": "自动化框架名称 (可选,如 Selenium/Playwright)",
            "build_number": "构建号 (可选)",
            "results": [
                {
                    "testcase_id": "用例ID (整数)",
                    "status": "执行结果: 通过/失败/阻塞",
                    "remark": "备注 (可选)",
                    "screenshot": "截图URL (可选)",
                    "duration_seconds": "执行时长秒数 (可选)",
                    "executed_at": "执行时间ISO格式 (可选,默认当前时间)",
                }
            ],
        },
        "example": {
            "curl": """curl -X POST http://<your-server>:8000/api/automation/batch \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "plan_id": 1,
    "stage": "SIT",
    "framework": "Selenium",
    "build_number": "123",
    "results": [
      {
        "testcase_id": 10,
        "status": "通过",
        "remark": "自动化测试通过",
        "screenshot": "https://example.com/screenshot.png",
        "duration_seconds": 5
      }
    ]
  }'""",
            "python": """import requests

token = "YOUR_TOKEN"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

data = {
    "plan_id": 1,
    "stage": "SIT",
    "framework": "Selenium",
    "build_number": "123",
    "results": [
        {
            "testcase_id": 10,
            "status": "通过",
            "remark": "自动化测试通过",
            "duration_seconds": 5
        }
    ]
}

response = requests.post(
    "http://<your-server>:8000/api/automation/batch",
    headers=headers,
    json=data
)
print(response.json())""",
        },
        "notes": [
            "每次调用会创建新的执行记录,不会覆盖历史记录",
            "用例必须属于测试计划对应的项目",
            "状态只能是: 通过/失败/阻塞",
            "CI 产出的 JUnit XML 可直接上传: POST /api/automation/import-xml(multipart,页面「自动化集成」也有入口)",
            "建议在执行完成后立即回写结果,避免数据不一致",
        ],
    }
