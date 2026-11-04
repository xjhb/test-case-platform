"""统一通知入口:站内信必写,外部通道尽力投递

外部通道(邮件/钉钉/企业微信/飞书)的凭据只来自 .env 或 Nacos。
投递在后台线程执行,任何失败只写进通知的 push_result 与后端日志,不影响业务事务。
"""
import logging
import threading
import time
from datetime import date, datetime, time as dtime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .integrations import notify as channels
from .integrations.errors import IntegrationError
from .models import Notification, Project, ProjectRole, SystemConfig, TestPlan, User

log = logging.getLogger("uvicorn.error")

ROBOT_CHANNELS = ("dingtalk", "wecom", "feishu")
# 只有明确标记 broadcast 的事件才推群机器人,避免每次指派都刷屏群聊
SCAN_INTERVAL_MINUTES = 360


def _full_link(link: str) -> str:
    """站内信存的是前端路由(/defects?focus=3),外部通道需要可点击的完整地址"""
    if not link:
        return ""
    if link.startswith("http"):
        return link
    base = (settings.platform_base_url or "").rstrip("/")
    return f"{base}/#{link.lstrip('/')}" if base else ""


def _external_body(content: str, link: str) -> str:
    lines = [content, f"详情: {link}" if link else "", f"来自 {settings.platform_base_url}" if settings.platform_base_url else ""]
    return "\n".join(x for x in lines if x)


def emit(
    db: Session,
    user_ids,
    ntype: str,
    title: str,
    content: str = "",
    link: str = "",
    broadcast: bool = False,
) -> int:
    """写入站内信(立即提交)并在后台投递到已配置的外部通道,返回收件人数

    站内信提交后才启动投递线程,保证线程能回写到已存在的行。
    """
    ids = sorted({int(i) for i in (user_ids or []) if i})
    if not ids:
        return 0
    recipients = list(
        db.execute(select(User).where(User.id.in_(ids), User.is_active == True)).scalars()  # noqa: E712
    )
    if not recipients:
        return 0
    rows = []
    for u in recipients:
        n = Notification(user_id=u.id, type=ntype, title=title[:255], content=content, link=link[:255])
        db.add(n)
        rows.append(n)
    db.commit()

    emails = [u.email.strip() for u in recipients if u.email and "@" in u.email]
    if not settings.notify_external_enabled:
        for n in rows:
            n.push_result = "外部投递已关闭(notify_external_enabled=false)"
        db.commit()
        return len(rows)
    threading.Thread(
        target=_deliver,
        args=([n.id for n in rows], title, content, emails, _full_link(link), broadcast),
        daemon=True,
    ).start()
    return len(rows)


def _deliver(notify_ids, title: str, content: str, emails, link: str, broadcast: bool) -> None:
    results = []
    try:
        status = channels.channel_status()
        body = _external_body(content, link)
        if emails:
            if status["email"]["configured"]:
                ok = 0
                for addr in emails:
                    try:
                        channels.send_email(title, body, [addr])
                        ok += 1
                    except IntegrationError as e:
                        log.warning("邮件投递失败 %s: %s", addr, e)
                        results.append(f"邮件{addr}失败")
                if ok:
                    results.append(f"邮件已投递{ok}人")
            else:
                results.append(f"邮件未配置(缺{','.join(status['email']['missing_keys'])})")
        if broadcast:
            for name in ROBOT_CHANNELS:
                if not status[name]["configured"]:
                    continue
                try:
                    channels.send(name, title, body, [], link)
                    results.append(f"{name}已推送")
                except IntegrationError as e:
                    log.warning("%s 群机器人推送失败: %s", name, e)
                    results.append(f"{name}推送失败")
    except Exception as e:  # 投递线程绝不能把异常抛回业务
        log.warning("外部通知投递异常: %s", e)
        results.append(f"投递异常:{str(e)[:60]}")

    text = ("; ".join(results))[:255] if results else "仅站内信(未走外部通道)"
    try:
        with SessionLocal() as s:
            for nid in notify_ids:
                n = s.get(Notification, nid)
                if n:
                    n.push_result = text
            s.commit()
    except Exception as e:
        log.warning("回写投递结果失败: %s", e)


def _plan_recipients(db: Session, plan: TestPlan) -> list[int]:
    """计划创建人 + 项目上的项目经理/测试负责人"""
    ids = {plan.created_by}
    roles = list(
        db.execute(
            select(ProjectRole).where(
                ProjectRole.project_id == plan.project_id,
                ProjectRole.role.in_(["manager", "test_lead"]),
            )
        ).scalars()
    )
    ids |= {r.user_id for r in roles}
    return [i for i in ids if i]


def scan_stage_expiring(db: Session) -> dict:
    """给 N 天内到期且仍在进行的阶段发提醒;同一天同一计划阶段只提醒一次"""
    cfg = db.execute(select(SystemConfig).limit(1)).scalar_one_or_none()
    remind_days = cfg.stage_remind_days if cfg else 3
    today = date.today()
    day_start = datetime.combine(today, dtime.min)
    plans = list(db.execute(select(TestPlan).where(TestPlan.status == "进行中")).scalars())
    created = skipped = 0
    for plan in plans:
        project = db.get(Project, plan.project_id)
        if not project:
            continue
        for stage, end in (("SIT", plan.sit_end), ("UAT", plan.uat_end), ("PRE", plan.pre_end)):
            if not end:
                continue
            remain = (end.date() - today).days
            if remain < 0 or remain > remind_days:
                continue
            link = f"/plans?project_id={plan.project_id}&focus={plan.id}&stage={stage}"
            dup = db.execute(
                select(Notification.id)
                .where(
                    Notification.type == "stage_expiring",
                    Notification.link == link,
                    Notification.created_at >= day_start,
                )
                .limit(1)
            ).scalar_one_or_none()
            if dup is not None:
                skipped += 1
                continue
            title = f"「{project.name} {plan.version}」{stage} 阶段还有 {remain} 天到期"
            content = f"截止时间 {end:%Y-%m-%d %H:%M}。请及时完成执行并生成阶段报告。"
            if emit(db, _plan_recipients(db, plan), "stage_expiring", title, content, link, broadcast=True):
                created += 1
    return {"remind_days": remind_days, "scanned_plans": len(plans), "created": created, "skipped": skipped}


def _scan_worker() -> None:
    deadline = datetime.min
    while True:
        now = datetime.now()
        if now >= deadline:
            deadline = now + timedelta(minutes=SCAN_INTERVAL_MINUTES)
            try:
                with SessionLocal() as db:
                    scan_stage_expiring(db)
            except Exception as e:
                log.warning("阶段到期扫描失败: %s", e)
        time.sleep(30)


_scheduler_started = False


def start_stage_scheduler() -> None:
    """启动时补发一次到期提醒,之后按 SCAN_INTERVAL_MINUTES 周期扫描"""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    threading.Thread(target=_scan_worker, daemon=True).start()
