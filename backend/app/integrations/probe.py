"""集成连通性自检:尽量用无副作用的接口验证凭据,机器人通道会真实发一条测试消息"""
import requests

from ..config import settings
from .errors import IntegrationError, NotConfigured
from . import issue_sync, notify

TIMEOUT = 12


def _probe_http(name: str, url: str, **kw) -> dict:
    try:
        resp = requests.get(url, timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        raise IntegrationError(name, f"无法连接: {e}")
    if resp.status_code >= 400:
        raise IntegrationError(name, f"HTTP {resp.status_code}: {resp.text[:160]}")
    return {"target": name, "reachable": True, "status_code": resp.status_code}


def probe_email() -> dict:
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
        raise NotConfigured("email", ["smtp_host", "smtp_user", "smtp_password"])
    import smtplib

    cls = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
    try:
        with cls(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT) as server:
            if not settings.smtp_ssl:
                server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
    except Exception as e:
        raise IntegrationError("email", f"SMTP 登录失败: {e}")
    return {"target": "email", "reachable": True, "detail": f"{settings.smtp_host}:{settings.smtp_port} 登录成功"}


def probe_robot(name: str) -> dict:
    # 机器人 Webhook 没有只读探测接口,自检会真的推送一条测试消息
    senders = {"dingtalk": notify.send_dingtalk, "wecom": notify.send_wecom, "feishu": notify.send_feishu}
    senders[name]("测管平台连通性自检", "这是一条来自测管平台的通道自检消息,收到即表示配置正确。")
    return {"target": name, "reachable": True, "detail": "已推送自检消息"}


def probe_jenkins() -> dict:
    if not (settings.jenkins_base_url and settings.jenkins_user and settings.jenkins_token):
        raise NotConfigured("jenkins", ["jenkins_base_url", "jenkins_user", "jenkins_token"])
    base = settings.jenkins_base_url.rstrip("/")
    return _probe_http("jenkins", f"{base}/api/json", auth=(settings.jenkins_user, settings.jenkins_token))


def probe_gitlab() -> dict:
    if not (settings.gitlab_base_url and settings.gitlab_token):
        raise NotConfigured("gitlab_ci", ["gitlab_base_url", "gitlab_token"])
    base = settings.gitlab_base_url.rstrip("/")
    return _probe_http("gitlab_ci", f"{base}/api/v4/projects?per_page=1", headers={"PRIVATE-TOKEN": settings.gitlab_token})


def probe_github() -> dict:
    if not settings.github_token:
        raise NotConfigured("github_actions", ["github_token"])
    return _probe_http("github_actions", "https://api.github.com/user", headers={"Authorization": f"Bearer {settings.github_token}"})


def probe_jira() -> dict:
    if not (settings.jira_base_url and settings.jira_user and settings.jira_token):
        raise NotConfigured("jira", ["jira_base_url", "jira_user", "jira_token"])
    base = settings.jira_base_url.rstrip("/")
    return _probe_http("jira", f"{base}/rest/api/2/serverInfo", auth=(settings.jira_user, settings.jira_token))


def probe_zentao() -> dict:
    token = issue_sync._zentao_token()
    return {"target": "zentao", "reachable": True, "detail": "禅道登录成功,已获取 token", "token_prefix": token[:6]}


PROBES = {
    "email": probe_email,
    "dingtalk": probe_robot,
    "wecom": probe_robot,
    "feishu": probe_robot,
    "jenkins": probe_jenkins,
    "gitlab_ci": probe_gitlab,
    "github_actions": probe_github,
    "jira": probe_jira,
    "zentao": probe_zentao,
}


def probe(name: str) -> dict:
    if name not in PROBES:
        raise IntegrationError(name, f"未知目标,可选: {'/'.join(sorted(PROBES))}")
    return PROBES[name]()
