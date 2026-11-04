"""外部工具集成路由: Jira/禅道/CI/CD/通知/自动化测试

所有外部通道凭据只来自 .env 或 Nacos,未配置的通道接口返回 503 并列出缺失的变量名,
远端返回失败或不可达返回 502。本文件不再提供任何模拟成功。
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_admin, require_project_access
from ..integrations import cicd, issue_sync, notify, probe
from ..integrations.errors import IntegrationError, NotConfigured
from ..logger import log_op
from ..models import (
    Defect,
    DefectExternal,
    Project,
    TestCase,
    TestPlan,
    TestRun,
    User,
    WebhookEvent,
)
from ..scope import in_scope

router = APIRouter(prefix="/api/integrations", tags=["外部集成"])

VALID_RUN_STATUS = {"通过", "失败", "阻塞"}

# 外部缺陷状态 -> 本平台状态
EXTERNAL_STATUS_MAP = {
    "open": "新建", "active": "新建", "reopened": "重新打开", "todo": "新建",
    "in progress": "处理中", "doing": "处理中", "assign": "处理中",
    "resolved": "已修复", "fixed": "已修复", "verify": "已验证",
    "closed": "关闭", "done": "关闭", "verified": "已验证",
}


# ===================== 数据模型 =====================
class WebhookPayload(BaseModel):
    """通用 Webhook 接收数据"""
    source: str  # jenkins/gitlab/github/jira/zentao
    event_type: str  # build_complete/bug_created/test_result/...
    project_key: Optional[str] = None
    project_id: Optional[int] = None
    data: dict


class DefectSyncRequest(BaseModel):
    """外部缺陷同步请求(外部 -> 本平台)"""
    external_system: str  # jira/zentao
    external_id: str
    title: str
    project_id: int
    description: Optional[str] = None
    severity: Optional[str] = "一般"
    priority: Optional[str] = "P2"
    status: Optional[str] = "新建"
    assignee: Optional[str] = None  # 本平台用户名或姓名
    testcase_id: Optional[int] = None


class NotificationRequest(BaseModel):
    """通知发送请求"""
    channel: str  # dingtalk/wecom/feishu/email
    title: str
    content: str
    receivers: list[str] = []  # 邮件用邮箱;机器人通道可留空
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
    parameters: Optional[dict] = None


class SelfTestRequest(BaseModel):
    target: str


# ===================== 公共辅助 =====================
def _raise_http(exc: IntegrationError) -> None:
    """未配置 -> 503,远端失败 -> 502;detail 为纯文本便于前端直接展示"""
    status_code = 503 if isinstance(exc, NotConfigured) else 502
    raise HTTPException(status_code=status_code, detail=str(exc))


def _resolve_project(payload_project_id: Optional[int], project_key: Optional[str], db: Session) -> Optional[Project]:
    if payload_project_id:
        return db.get(Project, payload_project_id)
    if project_key:
        return db.execute(
            select(Project).where(Project.project_no == project_key)
        ).scalars().first()
    return None


def _resolve_user(name: Optional[str], db: Session) -> Optional[int]:
    if not name:
        return None
    user = db.execute(select(User).where(User.username == name)).scalars().first()
    if user:
        return user.id
    user = db.execute(select(User).where(User.name == name)).scalars().first()
    return user.id if user else None


def _map_status(raw: Optional[str]) -> str:
    if not raw:
        return "新建"
    return EXTERNAL_STATUS_MAP.get(str(raw).strip().lower(), "新建")


def _reporter_id(db: Session, current: Optional[User]) -> Optional[int]:
    """回调凭 secret 进来时没有登录用户,退到第一个管理员作为报缺陷人"""
    if current:
        return current.id
    admin = db.execute(
        select(User).where(User.role == "admin").order_by(User.id).limit(1)
    ).scalars().first()
    return admin.id if admin else None


# ===================== Webhook 接收 =====================
def webhook_or_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    回调端点鉴权:
    - 外部系统不持有平台账号,凭 backend/.env 里的 webhook_secret 以 X-Webhook-Token(或 ?token=)调用;
    - 未配置 webhook_secret 时只接受平台登录令牌。
    两条路都不满足则 401,不存在匿名可写的回调入口。
    """
    secret = settings.webhook_secret
    token = request.headers.get("X-Webhook-Token") or request.query_params.get("token")
    if secret and token and token == secret:
        return None

    from ..security import decode_access_token

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        user_id = decode_access_token(auth_header[7:])
        if user_id:
            user = db.get(User, int(user_id))
            if user and user.is_active:
                return user
    raise HTTPException(
        status_code=401,
        detail="回调需要 X-Webhook-Token(在 .env 配置 webhook_secret 后启用)或平台登录令牌",
    )


@router.post("/webhook")
def receive_webhook(
    payload: WebhookPayload,
    db: Session = Depends(get_db),
    current: Optional[User] = Depends(webhook_or_user),
):
    """
    通用 Webhook 接收端点
    原始事件先落库再处理,处理失败也不丢事件。
    """
    external_key = str(
        payload.data.get("key")
        or payload.data.get("id")
        or payload.data.get("build_number")
        or payload.data.get("external_id")
        or ""
    )

    event = WebhookEvent(
        source=payload.source,
        event_type=payload.event_type,
        external_key=external_key[:128],
        payload=json.dumps(payload.data, ensure_ascii=False)[:60000],
        received_by=current.id if current else None,
    )
    db.add(event)
    db.flush()

    # 同一来源+事件+外部主键重复推送才算幂等冲突;created 之后跟 updated 是正常流程
    if external_key:
        dup = db.execute(
            select(WebhookEvent).where(
                WebhookEvent.source == payload.source,
                WebhookEvent.event_type == payload.event_type,
                WebhookEvent.external_key == external_key,
                WebhookEvent.id != event.id,
            ).limit(1)
        ).scalars().first()
        if dup:
            event.handle_result = "已忽略"
            event.handle_note = f"重复事件,已存在记录 #{dup.id}"
            db.commit()
            return {"status": "duplicate", "event_id": event.id, "message": event.handle_note}

    try:
        result = _dispatch_webhook(payload, db, current)
    except HTTPException as e:
        event.handle_result = "处理失败"
        event.handle_note = str(e.detail)[:2000]
        db.commit()
        raise
    except Exception as e:  # 外部数据不可控,任何异常都要留在事件里
        event.handle_result = "处理失败"
        event.handle_note = str(e)[:2000]
        db.commit()
        raise HTTPException(status_code=502, detail=f"事件处理失败: {e}")

    event.handle_result = result["handle_result"]
    event.handle_note = result.get("note", "")[:2000]
    db.commit()
    log_op(db, current, "接收Webhook", target=payload.source,
           detail=f"事件:{payload.event_type} -> {event.handle_result}")
    return {"status": "processed", "event_id": event.id, **result}


def _dispatch_webhook(payload: WebhookPayload, db: Session, current: Optional[User]) -> dict:
    key = f"{payload.source}:{payload.event_type}"
    if key == "jenkins:build_complete":
        return _handle_jenkins_build(payload, db)
    if key in ("jira:issue_created", "jira:issue_updated"):
        return _handle_issue_created(payload, db, current, "jira")
    if key in ("zentao:bug_created", "zentao:bug_updated"):
        return _handle_issue_created(payload, db, current, "zentao")
    if key in ("gitlab:test_result", "github:test_result", "jenkins:test_result"):
        return _handle_ci_test_result(payload, db, current)
    return {"handle_result": "未识别", "note": f"暂无 {key} 的处理逻辑,事件已存档", "message": f"已存档未识别事件 {key}"}


def _handle_jenkins_build(payload: WebhookPayload, db: Session) -> dict:
    build = payload.data
    url = build.get("url") or build.get("build_url") or ""
    return {
        "handle_result": "已接收",
        "note": f"构建 {build.get('build_number')} 状态 {build.get('result')}",
        "message": f"Jenkins 构建 {build.get('build_number')} 已记录",
        "build_url": url,
    }


def _handle_issue_created(payload: WebhookPayload, db: Session, current: Optional[User], system: str) -> dict:
    """Jira/禅道 工单事件 -> 本地缺陷 upsert,并写入外部映射"""
    issue = payload.data
    fields = issue.get("fields", issue)  # Jira webhook 把业务字段放在 fields 下
    ext_id = str(fields.get("key") or fields.get("id") or issue.get("key") or issue.get("id") or issue.get("bugid") or "")
    title = str(fields.get("summary") or fields.get("title") or issue.get("summary") or issue.get("title") or "").strip()
    if not ext_id or not title:
        return {"handle_result": "未识别", "note": "事件缺少外部ID或标题,未建缺陷"}

    project = _resolve_project(payload.project_id, payload.project_key, db)
    if not project:
        return {"handle_result": "未识别", "note": f"未匹配到项目(project_key={payload.project_key}, project_id={payload.project_id})"}

    link = db.execute(
        select(DefectExternal).where(DefectExternal.system == system, DefectExternal.external_id == ext_id)
    ).scalars().first()

    assignee_name = ""
    if system == "jira":
        assignee_name = (fields.get("assignee") or {}).get("displayName", "") if isinstance(fields.get("assignee"), dict) else ""
    else:
        assignee_name = fields.get("assignedTo", "") or fields.get("assigned_to", "")
    desc = fields.get("description") or fields.get("steps") or ""
    severity_raw = fields.get("severity") or fields.get("priority") or ""
    severity = severity_raw if severity_raw in {"致命", "严重", "中", "一般", "提示"} else "一般"
    status = _map_status(fields.get("status") if not isinstance(fields.get("status"), dict) else (fields.get("status") or {}).get("name"))

    if link and link.defect_id:
        defect = db.get(Defect, link.defect_id)
        if defect:
            defect.status = status
            defect.severity = severity
            link.synced_status = status
            link.synced_at = datetime.now()
            db.commit()
            return {"handle_result": "已更新", "note": f"缺陷#{defect.id} <- {system}#{ext_id}",
                    "defect_id": defect.id, "external_id": ext_id}

    reporter_id = _reporter_id(db, current)
    if not reporter_id:
        return {"handle_result": "未识别", "note": "系统中没有可用账号,无法建立缺陷归属"}

    base_url = (getattr(settings, f"{system}_base_url", "") or "").rstrip("/")
    if system == "jira":
        external_url = f"{base_url}/browse/{ext_id}" if base_url else ""
    elif base_url:
        external_url = f"{base_url}/bug-view-{ext_id}.html"
    else:
        external_url = ""

    defect = Defect(
        title=title[:255],
        description=str(desc)[:60000],
        severity=severity,
        priority="P2",
        status=status,
        project_id=project.id,
        reporter_id=reporter_id,
        assignee_id=_resolve_user(assignee_name, db),
    )
    db.add(defect)
    db.flush()
    db.add(DefectExternal(
        defect_id=defect.id, system=system, external_id=ext_id,
        external_url=external_url, synced_status=status, created_by=reporter_id,
    ))
    db.commit()
    return {"handle_result": "已建缺陷", "note": f"{system}#{ext_id} -> 缺陷#{defect.id}",
            "defect_id": defect.id, "external_id": ext_id}


def _handle_ci_test_result(payload: WebhookPayload, db: Session, current: Optional[User]) -> dict:
    """CI 测试结果 -> 执行记录"""
    results = payload.data.get("results") or payload.data.get("tests") or []
    plan_id = payload.data.get("plan_id")
    plan = db.get(TestPlan, plan_id) if plan_id else None
    if not plan:
        return {"handle_result": "未识别", "note": "事件未携带有效 plan_id,未写入执行记录"}
    if not isinstance(results, list) or not results:
        return {"handle_result": "未识别", "note": "事件中没有测试结果明细"}

    stage = payload.data.get("stage") or plan.current_stage
    executor_id = _reporter_id(db, current)
    if not executor_id:
        return {"handle_result": "未识别", "note": "系统中没有可用账号,执行记录无法归属"}
    written, skipped = 0, []
    for item in results:
        tc_id = item.get("testcase_id")
        status = item.get("status")
        tc = db.get(TestCase, tc_id) if tc_id else None
        if not tc or tc.project_id != plan.project_id:
            skipped.append(f"用例#{tc_id}不存在或不属于本项目")
            continue
        if status not in VALID_RUN_STATUS:
            skipped.append(f"用例#{tc_id}状态[{status}]无效")
            continue
        if not in_scope(db, plan, tc.id):
            skipped.append(f"用例#{tc_id}未纳入计划范围")
            continue
        db.add(TestRun(
            testcase_id=tc.id, plan_id=plan.id, stage=stage, status=status,
            remark=item.get("message") or f"{payload.source} 回传",
            screenshot=item.get("screenshot_url") or "",
            executed_by=executor_id,
            duration_seconds=item.get("duration_seconds"),
        ))
        written += 1
    db.commit()
    return {"handle_result": "已写入执行", "note": f"写入 {written} 条,跳过 {len(skipped)} 条",
            "written": written, "skipped": skipped[:20]}


@router.get("/webhook-events")
def list_webhook_events(
    limit: int = Query(50, ge=1, le=200),
    source: Optional[str] = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """最近接收到的外部回调,便于排查事件是否送达、处理结果如何"""
    q = select(WebhookEvent).order_by(WebhookEvent.id.desc()).limit(limit)
    if source:
        q = q.where(WebhookEvent.source == source)
    rows = db.execute(q).scalars().all()
    return [
        {
            "id": e.id,
            "source": e.source,
            "event_type": e.event_type,
            "external_key": e.external_key,
            "handle_result": e.handle_result,
            "handle_note": e.handle_note,
            "received_at": e.received_at,
        }
        for e in rows
    ]


# ===================== 缺陷同步 =====================
@router.post("/defect/sync")
def sync_defect(
    req: DefectSyncRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    把外部系统(Jira/禅道)的缺陷同步进本平台。
    以 外部系统 + 外部ID 为唯一键做 upsert,首次同步创建本地缺陷。
    """
    if req.external_system not in issue_sync.CREATORS:
        raise HTTPException(status_code=400, detail=f"外部系统只能是 {'/'.join(sorted(issue_sync.CREATORS))}")
    project = db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    require_project_access(project.id, db, current)

    link = db.execute(
        select(DefectExternal).where(
            DefectExternal.system == req.external_system,
            DefectExternal.external_id == str(req.external_id),
        )
    ).scalars().first()

    severity = req.severity if req.severity in {"致命", "严重", "中", "一般", "提示"} else "一般"
    status = _map_status(req.status)
    assignee_id = _resolve_user(req.assignee, db)

    if link and link.defect_id:
        defect = db.get(Defect, link.defect_id)
        if not defect:
            link.defect_id = None
            defect = None
    else:
        defect = None

    if defect:
        defect.title = req.title[:255]
        defect.severity = severity
        defect.priority = req.priority or defect.priority
        defect.status = status
        if req.description:
            defect.description = req.description
        if assignee_id:
            defect.assignee_id = assignee_id
        link.synced_status = status
        link.synced_at = datetime.now()
        action = "updated"
        db.flush()
    else:
        defect = Defect(
            title=req.title[:255],
            description=req.description or "",
            severity=severity,
            priority=req.priority or "P2",
            status=status,
            testcase_id=req.testcase_id,
            project_id=project.id,
            reporter_id=current.id,
            assignee_id=assignee_id,
        )
        db.add(defect)
        db.flush()
        db.add(DefectExternal(
            defect_id=defect.id, system=req.external_system, external_id=str(req.external_id),
            synced_status=status, created_by=current.id,
        ))
        action = "created"

    db.commit()
    db.refresh(defect)
    log_op(db, current, "同步缺陷", target=f"{req.external_system}#{req.external_id}",
           detail=f"{action} -> 缺陷#{defect.id}")
    return {
        "status": "synced",
        "action": action,
        "defect_id": defect.id,
        "external_system": req.external_system,
        "external_id": req.external_id,
        "defect_status": defect.status,
    }


@router.post("/defect/{defect_id}/push")
def push_defect(
    defect_id: int,
    target_system: str = Query(..., description="目标系统: jira/zentao"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """把本平台缺陷推送到 Jira/禅道 建工单;已有映射则直接返回,避免重复创建"""
    defect = db.get(Defect, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="缺陷不存在")
    require_project_access(defect.project_id, db, current)

    existed = db.execute(
        select(DefectExternal).where(DefectExternal.defect_id == defect_id, DefectExternal.system == target_system)
    ).scalars().first()
    if existed:
        return {
            "status": "already_pushed",
            "defect_id": defect_id,
            "target_system": target_system,
            "external_id": existed.external_id,
            "external_url": existed.external_url,
            "message": f"该缺陷已推送到 {target_system},未重复创建",
        }

    try:
        result = issue_sync.create(
            target_system, defect.title, defect.description or "",
            defect.severity or "中", defect.priority or "P2",
        )
    except IntegrationError as e:
        _raise_http(e)

    link = DefectExternal(
        defect_id=defect_id,
        system=target_system,
        external_id=str(result.get("external_id") or ""),
        external_url=str(result.get("external_url") or ""),
        synced_status=defect.status,
        created_by=current.id,
    )
    db.add(link)
    db.commit()
    log_op(db, current, "推送缺陷", target=f"缺陷#{defect_id}",
           detail=f"推送到 {target_system},外部单号 {link.external_id}")
    return {
        "status": "pushed",
        "defect_id": defect_id,
        "target_system": target_system,
        "external_id": link.external_id,
        "external_url": link.external_url,
        "message": f"缺陷已在 {target_system} 创建工单 {link.external_id}",
    }


@router.get("/defect/{defect_id}/links")
def list_defect_links(
    defect_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """缺陷关联的外部工单"""
    defect = db.get(Defect, defect_id)
    if not defect:
        raise HTTPException(status_code=404, detail="缺陷不存在")
    require_project_access(defect.project_id, db, current)
    rows = db.execute(
        select(DefectExternal).where(DefectExternal.defect_id == defect_id)
    ).scalars().all()
    return [
        {"id": r.id, "system": r.system, "external_id": r.external_id,
         "external_url": r.external_url, "synced_status": r.synced_status, "synced_at": r.synced_at}
        for r in rows
    ]


# ===================== 通知发送 =====================
@router.post("/notify")
def send_notification(
    req: NotificationRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """真实发送到 钉钉/企微/飞书/邮件;未配置凭据返回 503,远端失败返回 502"""
    link = req.link or (f"{settings.platform_base_url.rstrip('/')}/#/plans" if settings.platform_base_url else None)
    try:
        result = notify.send(req.channel, req.title, req.content, req.receivers, link)
    except IntegrationError as e:
        _raise_http(e)

    log_op(db, current, "发送通知", target=req.channel,
           detail=f"标题:{req.title}, 送达:{result.get('delivered')}")
    return {"status": "sent", **result, "message": f"通知已通过 {req.channel} 送达"}


# ===================== 自动化测试结果 =====================
@router.post("/automation/result")
def report_automation_result(
    req: AutomationResultRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """上报单条自动化测试执行结果(Selenium/Playwright/Cypress/JMeter 等)"""
    plan = db.get(TestPlan, req.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="测试计划不存在")
    tc = db.get(TestCase, req.testcase_id)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    if tc.project_id != plan.project_id:
        raise HTTPException(status_code=400, detail="用例不属于该计划所在项目")
    require_project_access(plan.project_id, db, current)
    if req.status not in VALID_RUN_STATUS:
        raise HTTPException(status_code=400, detail=f"执行状态只能是 {'/'.join(sorted(VALID_RUN_STATUS))}")
    if not in_scope(db, plan, tc.id):
        raise HTTPException(status_code=400, detail=f"用例#{tc.id} 未纳入计划#{plan.id}的用例范围,请先圈选后再回写")

    remark = req.error_message or f"自动化测试({req.framework})"
    if req.log_url:
        remark = f"{remark}\n日志: {req.log_url}"

    run = TestRun(
        testcase_id=req.testcase_id,
        plan_id=req.plan_id,
        stage=plan.current_stage,
        status=req.status,
        remark=remark,
        screenshot=req.screenshot_url or "",
        executed_by=current.id,
        executed_at=req.executed_at or datetime.now(),
        duration_seconds=int(req.duration_ms / 1000) if req.duration_ms is not None else None,
    )
    db.add(run)
    db.commit()
    log_op(db, current, "自动化测试结果", target=f"用例#{req.testcase_id}",
           detail=f"框架:{req.framework}, 状态:{req.status}")
    return {
        "status": "recorded",
        "run_id": run.id,
        "framework": req.framework,
        "testcase_id": req.testcase_id,
        "result": req.status,
        "duration_seconds": run.duration_seconds,
    }


# ===================== CI/CD 触发 =====================
@router.post("/cicd/trigger")
def trigger_cicd_pipeline(
    req: CICDTriggerRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """真实触发 Jenkins / GitLab CI / GitHub Actions 流水线"""
    try:
        result = cicd.trigger(req.pipeline_type, req.pipeline_name, req.branch, req.parameters)
    except IntegrationError as e:
        _raise_http(e)

    log_op(db, current, "触发CI/CD", target=req.pipeline_type,
           detail=f"流水线:{req.pipeline_name}, 分支:{req.branch}")
    return {"status": "triggered", **result, "message": f"流水线 {req.pipeline_name} 已触发"}


# ===================== 通道状态与自检 =====================
LABELS = {
    "email": "邮件 (SMTP)",
    "dingtalk": "钉钉机器人",
    "wecom": "企业微信机器人",
    "feishu": "飞书机器人",
    "jenkins": "Jenkins",
    "gitlab_ci": "GitLab CI",
    "github_actions": "GitHub Actions",
    "jira": "Jira",
    "zentao": "禅道",
}


def _group(kind: str, source: str, name: str, info: dict) -> dict:
    return {
        "name": name,
        "label": LABELS.get(name, name),
        "kind": kind,
        "configured": info["configured"],
        "missing_keys": info["missing_keys"],
        "has_probe": source in probe.PROBES,
    }


@router.get("/status")
def integration_status(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """各通道是否已配置凭据(只报变量名,不回显任何取值)"""
    items = []
    for name, info in notify.channel_status().items():
        items.append(_group("notification", name, name, info))
    for name, info in cicd.source_status().items():
        items.append(_group("cicd", name, name, info))
    for name, info in issue_sync.source_status().items():
        items.append(_group("issue", name, name, info))

    return {
        "channels": items,
        "webhook_secret_configured": bool(settings.webhook_secret),
        "platform_base_url_configured": bool(settings.platform_base_url),
        "config_source": "nacos" if settings.nacos_server else "env",
        "hint": "凭据请在 backend/.env 或 Nacos 配置(testmanage)中填写,保存后重启后端生效",
    }


@router.post("/self-test")
def self_test(
    req: SelfTestRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    """
    连通性自检。
    邮件/CI/缺陷系统只做只读探测;钉钉/企微/飞书没有只读接口,自检会真实推送一条测试消息。
    """
    try:
        result = probe.probe(req.target)
    except IntegrationError as e:
        _raise_http(e)

    log_op(db, current, "集成自检", target=req.target, detail="通过")
    return {"status": "ok", **result, "message": result.get("detail") or "连通性校验通过"}
