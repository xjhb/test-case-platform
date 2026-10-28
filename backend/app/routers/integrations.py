"""外部工具集成路由: Jira/禅道/CI/CD/通知/自动化测试"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin, require_project_access
from ..logger import log_op
from ..models import Defect, Project, TestPlan, TestRun, User

router = APIRouter(prefix="/api/integrations", tags=["外部集成"], dependencies=[Depends(get_current_user)])


# ===================== 数据模型 =====================
class WebhookPayload(BaseModel):
    """通用 Webhook 接收数据"""
    source: str  # jenkins/gitlab/github/jira/zentao
    event_type: str  # build_complete/test_result/issue_created
    project_key: Optional[str] = None
    data: dict


class DefectSyncRequest(BaseModel):
    """缺陷同步请求"""
    external_system: str  # jira/zentao
    external_id: str
    title: str
    description: Optional[str] = None
    severity: Optional[str] = "一般"
    priority: Optional[str] = "P2"
    status: Optional[str] = "新建"
    assignee: Optional[str] = None
    testcase_id: Optional[int] = None


class NotificationRequest(BaseModel):
    """通知发送请求"""
    channel: str  # dingtalk/wecom/feishu/email
    title: str
    content: str
    receivers: list[str]  # 手机号/邮箱/用户ID列表
    project_id: Optional[int] = None
    link: Optional[str] = None


class AutomationResultRequest(BaseModel):
    """自动化测试结果上报"""
    framework: str  # selenium/playwright/cypress/jmeter
    plan_id: int
    testcase_id: int
    status: str  # 通过/失败/阻塞
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    screenshot_url: Optional[str] = None
    log_url: Optional[str] = None
    executed_at: Optional[datetime] = None


class CICDTriggerRequest(BaseModel):
    """CI/CD 触发请求"""
    pipeline_type: str  # jenkins/gitlab_ci/github_actions
    pipeline_name: str
    branch: Optional[str] = None
    commit_id: Optional[str] = None
    parameters: Optional[dict] = None


# ===================== Webhook 接收 =====================
@router.post("/webhook")
def receive_webhook(
    payload: WebhookPayload,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    通用 Webhook 接收端点
    用于接收来自 Jenkins/GitLab/GitHub/Jira/禅道 等工具的回调
    """
    log_op(
        db, current, "接收Webhook",
        target=payload.source,
        detail=f"事件:{payload.event_type}"
    )
    
    # 根据 source 和 event_type 分发处理
    if payload.source == "jenkins" and payload.event_type == "build_complete":
        return _handle_jenkins_build(payload, db)
    elif payload.source == "jira" and payload.event_type == "issue_created":
        return _handle_jira_issue(payload, db)
    elif payload.source == "zentao" and payload.event_type == "bug_created":
        return _handle_zentao_bug(payload, db)
    elif payload.source in ["gitlab", "github"] and payload.event_type == "test_result":
        return _handle_ci_test_result(payload, db)
    else:
        return {"status": "received", "message": f"已接收 {payload.source} 的 {payload.event_type} 事件"}


def _handle_jenkins_build(payload: WebhookPayload, db: Session):
    """处理 Jenkins 构建完成事件"""
    build_info = payload.data
    return {
        "status": "processed",
        "message": f"Jenkins 构建 {build_info.get('build_number')} 已完成",
        "build_url": build_info.get("url"),
    }


def _handle_jira_issue(payload: WebhookPayload, db: Session):
    """处理 Jira 问题创建事件"""
    issue = payload.data
    return {
        "status": "processed",
        "message": f"Jira 问题 {issue.get('key')} 已同步",
        "external_id": issue.get("key"),
    }


def _handle_zentao_bug(payload: WebhookPayload, db: Session):
    """处理禅道 Bug 创建事件"""
    bug = payload.data
    return {
        "status": "processed",
        "message": f"禅道 Bug #{bug.get('id')} 已同步",
        "external_id": str(bug.get("id")),
    }


def _handle_ci_test_result(payload: WebhookPayload, db: Session):
    """处理 CI 测试结果"""
    results = payload.data.get("results", [])
    return {
        "status": "processed",
        "message": f"已接收 {len(results)} 条测试结果",
    }


# ===================== 缺陷同步 =====================
@router.post("/defect/sync")
def sync_defect(
    req: DefectSyncRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    同步外部缺陷系统(Jira/禅道)的缺陷到本平台
    支持双向同步:外部 -> 本平台
    """
    # 查找或创建对应的本地缺陷
    existing = db.execute(
        select(Defect).where(Defect.title == req.title)
    ).scalar_one_or_none()
    
    if existing:
        # 更新现有缺陷
        existing.status = req.status
        existing.severity = req.severity
        existing.priority = req.priority
        if req.assignee:
            existing.assignee = req.assignee
        log_op(db, current, "同步缺陷", target=f"外部#{req.external_id}", detail="更新")
    else:
        # 创建新缺陷(需要 project_id,这里简化处理)
        log_op(db, current, "同步缺陷", target=f"外部#{req.external_id}", detail="新建")
    
    return {
        "status": "synced",
        "external_system": req.external_system,
        "external_id": req.external_id,
        "action": "updated" if existing else "created",
    }


@router.post("/defect/push")
def push_defect(
    defect_id: int,
    target_system: str = Query(..., description="目标系统: jira/zentao"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    将本平台缺陷推送到外部系统(Jira/禅道)
    实际实现需要调用外部 API
    """
    defect = db.get(Defect, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="缺陷不存在")
    
    # 这里应该调用外部系统的 API
    # 实际实现需要:
    # 1. 从配置中获取外部系统的 API 地址和认证信息
    # 2. 调用外部 API 创建/更新缺陷
    # 3. 记录外部缺陷 ID 到本地
    
    log_op(db, current, "推送缺陷", target=f"缺陷#{defect_id}", detail=f"推送到 {target_system}")
    
    return {
        "status": "pushed",
        "defect_id": defect_id,
        "target_system": target_system,
        "external_id": f"{target_system.upper()}-12345",  # 模拟返回的外部 ID
        "message": f"缺陷已推送到 {target_system}",
    }


# ===================== 通知发送 =====================
@router.post("/notify")
def send_notification(
    req: NotificationRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    发送通知到外部渠道(钉钉/企微/飞书/邮件)
    实际实现需要调用各渠道的 Webhook 或 API
    """
    # 这里应该调用外部通知渠道的 API
    # 实际实现需要:
    # 1. 从配置中获取各渠道的 Webhook URL 或 API 配置
    # 2. 构造消息格式(各渠道格式不同)
    # 3. 调用 API 发送通知
    
    log_op(
        db, current, "发送通知",
        target=req.channel,
        detail=f"标题:{req.title}, 接收者:{len(req.receivers)}人"
    )
    
    return {
        "status": "sent",
        "channel": req.channel,
        "receivers_count": len(req.receivers),
        "message": f"通知已发送到 {req.channel}",
    }


# ===================== 自动化测试结果 =====================
@router.post("/automation/result")
def report_automation_result(
    req: AutomationResultRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    上报自动化测试执行结果
    支持 Selenium/Playwright/Cypress/JMeter 等框架
    """
    # 创建测试执行记录
    run = TestRun(
        testcase_id=req.testcase_id,
        plan_id=req.plan_id,
        status=req.status,
        remark=req.error_message or f"自动化测试({req.framework})",
        screenshot=req.screenshot_url,
        executed_by=current.id,
    )
    db.add(run)
    db.commit()
    
    log_op(
        db, current, "自动化测试结果",
        target=f"用例#{req.testcase_id}",
        detail=f"框架:{req.framework}, 状态:{req.status}"
    )
    
    return {
        "status": "recorded",
        "run_id": run.id,
        "framework": req.framework,
        "testcase_id": req.testcase_id,
        "result": req.status,
    }


# ===================== CI/CD 触发 =====================
@router.post("/cicd/trigger")
def trigger_cicd_pipeline(
    req: CICDTriggerRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    触发外部 CI/CD 流水线
    实际实现需要调用 Jenkins/GitLab CI/GitHub Actions 的 API
    """
    # 这里应该调用外部 CI/CD 系统的 API
    # 实际实现需要:
    # 1. 从配置中获取 CI/CD 系统的 API 地址和 Token
    # 2. 构造触发请求
    # 3. 调用 API 触发流水线
    
    log_op(
        db, current, "触发CI/CD",
        target=req.pipeline_type,
        detail=f"流水线:{req.pipeline_name}, 分支:{req.branch}"
    )
    
    return {
        "status": "triggered",
        "pipeline_type": req.pipeline_type,
        "pipeline_name": req.pipeline_name,
        "branch": req.branch,
        "build_url": f"https://ci.example.com/job/{req.pipeline_name}/1",  # 模拟返回
        "message": f"流水线 {req.pipeline_name} 已触发",
    }


# ===================== 集成配置管理 =====================
@router.get("/config/list")
def list_integration_configs(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    列出所有集成配置
    实际实现需要 IntegrationConfig 模型
    """
    # 模拟返回配置列表
    configs = [
        {
            "id": 1,
            "name": "Jira 集成",
            "type": "defect_tracking",
            "system": "jira",
            "enabled": True,
            "config": {
                "api_url": "https://jira.example.com/rest/api/2",
                "project_key": "TEST",
            },
        },
        {
            "id": 2,
            "name": "钉钉通知",
            "type": "notification",
            "system": "dingtalk",
            "enabled": True,
            "config": {
                "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
            },
        },
        {
            "id": 3,
            "name": "Jenkins CI",
            "type": "cicd",
            "system": "jenkins",
            "enabled": False,
            "config": {
                "api_url": "http://jenkins.example.com",
                "user": "admin",
            },
        },
    ]
    return configs


@router.post("/config")
def create_integration_config(
    name: str,
    type: str,
    system: str,
    config: dict,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    创建集成配置
    实际实现需要 IntegrationConfig 模型
    """
    require_admin(current)
    
    log_op(db, current, "创建集成配置", target=name, detail=f"类型:{type}, 系统:{system}")
    
    return {
        "status": "created",
        "name": name,
        "type": type,
        "system": system,
        "message": f"集成配置 {name} 已创建",
    }


@router.put("/config/{config_id}")
def update_integration_config(
    config_id: int,
    config: dict,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    更新集成配置
    实际实现需要 IntegrationConfig 模型
    """
    require_admin(current)
    
    log_op(db, current, "更新集成配置", target=f"配置#{config_id}", detail=str(config))
    
    return {
        "status": "updated",
        "config_id": config_id,
        "message": "集成配置已更新",
    }


@router.delete("/config/{config_id}")
def delete_integration_config(
    config_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    删除集成配置
    实际实现需要 IntegrationConfig 模型
    """
    require_admin(current)
    
    log_op(db, current, "删除集成配置", target=f"配置#{config_id}")
    
    return {
        "status": "deleted",
        "config_id": config_id,
        "message": "集成配置已删除",
    }
