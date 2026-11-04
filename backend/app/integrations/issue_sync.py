"""缺陷系统对接:Jira / 禅道"""
from urllib.parse import quote

import requests

from ..config import settings
from .errors import IntegrationError, NotConfigured

TIMEOUT = 15

# 本平台严重度 -> Jira 优先级名称
JIRA_PRIORITY = {"致命": "Highest", "严重": "High", "中": "Medium", "一般": "Medium", "提示": "Low"}
# 本平台严重度 -> 禅道 severity(1 最严重, 4 最轻)
ZENTAO_SEVERITY = {"致命": 1, "严重": 2, "中": 3, "一般": 3, "提示": 4}


def _require(system: str, **values: str) -> None:
    missing = [k for k, v in values.items() if not v]
    if missing:
        raise NotConfigured(system, missing)


def create_jira_issue(title: str, description: str, severity: str, priority: str) -> dict:
    _require("jira", jira_base_url=settings.jira_base_url, jira_user=settings.jira_user, jira_token=settings.jira_token)
    project_key = settings.jira_project_key
    if not project_key:
        raise NotConfigured("jira", ["jira_project_key"])
    base = settings.jira_base_url.rstrip("/")
    url = f"{base}/rest/api/2/issue"
    payload = {
        "fields": {
            "project": {"key": project_key},
            "issuetype": {"name": "Bug"},
            "summary": title[:250],
            "description": description or "",
            "priority": {"name": JIRA_PRIORITY.get(severity or priority or "中", "Medium")},
        }
    }
    resp = requests.post(url, json=payload, auth=(settings.jira_user, settings.jira_token), timeout=TIMEOUT)
    if resp.status_code not in (200, 201):
        raise IntegrationError("jira", f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return {
        "system": "jira",
        "external_id": data.get("key"),
        "external_url": f"{base}/browse/{data.get('key')}",
        "raw": {"id": data.get("id")},
    }


def _zentao_token() -> str:
    _require(
        "zentao",
        zentao_base_url=settings.zentao_base_url,
        zentao_account=settings.zentao_account,
        zentao_password=settings.zentao_password,
    )
    base = settings.zentao_base_url.rstrip("/")
    resp = requests.post(f"{base}/api.php/v1/tokens", json={"account": settings.zentao_account, "password": settings.zentao_password}, timeout=TIMEOUT)
    if resp.status_code not in (200, 201):
        raise IntegrationError("zentao", f"登录失败 HTTP {resp.status_code}: {resp.text[:200]}")
    token = resp.json().get("token")
    if not token:
        raise IntegrationError("zentao", "未返回 token")
    return token


def create_zentao_bug(title: str, description: str, severity: str) -> dict:
    token = _zentao_token()
    product_id = settings.zentao_product_id
    if not product_id:
        raise NotConfigured("zentao", ["zentao_product_id"])
    base = settings.zentao_base_url.rstrip("/")
    url = f"{base}/api.php/v1/products/{quote(str(product_id))}/bugs"
    payload = {
        "title": title[:250],
        "severity": ZENTAO_SEVERITY.get(severity or "中", 3),
        "pri": 3,
        "steps": description or "",
        "openedBuild": ["trunk"],
    }
    resp = requests.post(url, json=payload, headers={"Token": token}, timeout=TIMEOUT)
    if resp.status_code not in (200, 201):
        raise IntegrationError("zentao", f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    ext_id = data.get("id")
    return {
        "system": "zentao",
        "external_id": str(ext_id) if ext_id is not None else None,
        "external_url": f"{base}/bug-view-{ext_id}.html",
        "raw": {},
    }


CREATORS = {"jira": create_jira_issue, "zentao": create_zentao_bug}

REQUIRED_KEYS = {
    "jira": ["jira_base_url", "jira_user", "jira_token", "jira_project_key"],
    "zentao": ["zentao_base_url", "zentao_account", "zentao_password", "zentao_product_id"],
}


def create(system: str, title: str, description: str, severity: str, priority: str) -> dict:
    if system not in CREATORS:
        raise IntegrationError(system, f"暂不支持,可选: {'/'.join(sorted(CREATORS))}")
    if system == "jira":
        return CREATORS[system](title, description, severity, priority)
    return CREATORS[system](title, description, severity)


def source_status() -> dict:
    out = {}
    for name, keys in REQUIRED_KEYS.items():
        missing = [k for k in keys if not getattr(settings, k, "")]
        out[name] = {"configured": not missing, "missing_keys": missing}
    return out
