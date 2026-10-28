from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..logger import log_op
from ..models import TestCase, TestPlan, TestRun, User

router = APIRouter(prefix="/api/automation", tags=["自动化集成"], dependencies=[Depends(get_current_user)])


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
            "建议在执行完成后立即回写结果,避免数据不一致",
        ],
    }
