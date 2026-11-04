"""CI/CD 触发:Jenkins / GitLab CI / GitHub Actions"""
from urllib.parse import quote

import requests

from ..config import settings
from .errors import IntegrationError, NotConfigured

TIMEOUT = 15


def _require(pipeline_type: str, **values: str) -> None:
    missing = [k for k, v in values.items() if not v]
    if missing:
        raise NotConfigured(pipeline_type, missing)


def _fail_where(pipeline_type: str, resp: requests.Response) -> None:
    raise IntegrationError(
        pipeline_type, f"HTTP {resp.status_code}: {resp.text[:200]}"
    )


def trigger_jenkins(job_name: str, branch: str | None, parameters: dict | None) -> dict:
    _require("jenkins", jenkins_base_url=settings.jenkins_base_url, jenkins_user=settings.jenkins_user, jenkins_token=settings.jenkins_token)
    if not job_name:
        raise IntegrationError("jenkins", "缺少任务名")
    base = settings.jenkins_base_url.rstrip("/")
    path = "/".join(quote(seg) for seg in job_name.strip("/").split("/"))
    params = dict(parameters or {})
    if branch:
        params.setdefault("branch", branch)
    url = f"{base}/job/{path}/buildWithParameters"
    resp = requests.post(url, data=params, auth=(settings.jenkins_user, settings.jenkins_token), timeout=TIMEOUT)
    if resp.status_code not in (200, 201, 203):
        _fail_where("jenkins", resp)
    queue_url = resp.headers.get("Location")
    return {
        "pipeline_type": "jenkins",
        "pipeline_name": job_name,
        "queued": True,
        "queue_url": queue_url,
        "build_url": f"{base}/job/{path}",
    }


def trigger_gitlab(project: str, branch: str | None, parameters: dict | None) -> dict:
    _require("gitlab_ci", gitlab_base_url=settings.gitlab_base_url, gitlab_token=settings.gitlab_token)
    if not project:
        raise IntegrationError("gitlab_ci", "缺少项目路径(如 group/subgroup/repo)")
    base = settings.gitlab_base_url.rstrip("/")
    url = f"{base}/api/v4/projects/{quote(project, safe='')}/pipeline"
    payload = {"ref": branch or "main", "variables": [{"key": k, "value": str(v)} for k, v in (parameters or {}).items()]}
    resp = requests.post(url, json=payload, headers={"PRIVATE-TOKEN": settings.gitlab_token}, timeout=TIMEOUT)
    if resp.status_code not in (200, 201):
        _fail_where("gitlab_ci", resp)
    data = resp.json()
    return {
        "pipeline_type": "gitlab_ci",
        "pipeline_name": project,
        "queued": True,
        "external_id": data.get("id"),
        "build_url": data.get("web_url") or f"{base}/{project}/-/pipelines",
    }


def trigger_github(repo: str, branch: str | None, parameters: dict | None) -> dict:
    _require("github_actions", github_token=settings.github_token)
    if not repo or "/" not in repo:
        raise IntegrationError("github_actions", "仓库需形如 owner/repo")
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{quote(branch or 'ci.yml')}/dispatches"
    payload = {"ref": "main", "inputs": {k: str(v) for k, v in (parameters or {}).items()}}
    resp = requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {settings.github_token}", "Accept": "application/vnd.github+json"},
        timeout=TIMEOUT,
    )
    if resp.status_code not in (200, 204):
        _fail_where("github_actions", resp)
    return {
        "pipeline_type": "github_actions",
        "pipeline_name": repo,
        "queued": True,
        "build_url": f"https://github.com/{repo}/actions",
    }


TRIGGERS = {
    "jenkins": trigger_jenkins,
    "gitlab_ci": trigger_gitlab,
    "github_actions": trigger_github,
}

REQUIRED_KEYS = {
    "jenkins": ["jenkins_base_url", "jenkins_user", "jenkins_token"],
    "gitlab_ci": ["gitlab_base_url", "gitlab_token"],
    "github_actions": ["github_token"],
}


def trigger(pipeline_type: str, pipeline_name: str, branch: str | None, parameters: dict | None) -> dict:
    if pipeline_type not in TRIGGERS:
        raise IntegrationError(pipeline_type, f"暂不支持,可选: {'/'.join(sorted(TRIGGERS))}")
    return TRIGGERS[pipeline_type](pipeline_name, branch, parameters)


def source_status() -> dict:
    out = {}
    for name, keys in REQUIRED_KEYS.items():
        missing = [k for k in keys if not getattr(settings, k, "")]
        out[name] = {"configured": not missing, "missing_keys": missing}
    return out
