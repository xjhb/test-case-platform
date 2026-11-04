"""站内之外的通知通道:邮件(SMTP)、钉钉、企业微信、飞书机器人"""
import base64
import hashlib
import hmac
import json
import smtplib
import time
import urllib.parse
from email.mime.text import MIMEText

import requests

from ..config import settings
from .errors import IntegrationError, NotConfigured

TIMEOUT = 10


def _require(channel: str, **values: str) -> None:
    missing = [k for k, v in values.items() if not v]
    if missing:
        raise NotConfigured(channel, missing)


def _sign_dingtalk(secret: str) -> tuple[str, str]:
    ts = str(round(time.time() * 1000))
    key = secret.encode()
    msg = f"{ts}\n{secret}".encode()
    sign = base64.b64encode(hmac.new(key, msg, hashlib.sha256).digest()).decode()
    return ts, urllib.parse.quote_plus(sign)


def send_email(title: str, content: str, receivers: list[str]) -> dict:
    _require("email", smtp_host=settings.smtp_host, smtp_user=settings.smtp_user, smtp_password=settings.smtp_password)
    targets = [r for r in receivers if "@" in r]
    if not targets:
        raise IntegrationError("email", "接收人中没有合法邮箱地址")
    sender = settings.smtp_from or settings.smtp_user
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = title
    msg["From"] = sender
    msg["To"] = ", ".join(targets)

    if settings.smtp_ssl:
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT)
        server.starttls()
    with server:
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(sender, targets, msg.as_string())
    return {"channel": "email", "delivered": len(targets), "targets": targets}


def _post_robot(channel: str, url: str, payload: dict) -> dict:
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise IntegrationError(channel, f"请求失败: {e}")
    if resp.status_code >= 400:
        raise IntegrationError(channel, f"HTTP {resp.status_code}: {resp.text[:200]}")
    body = {}
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:200]}
    # 三家机器人都用 errcode/code 表示业务结果,0 或成功码才算送达
    code = body.get("errcode", body.get("code", 0))
    if code not in (0, "0"):
        raise IntegrationError(channel, f"返回错误 {code}: {body.get('errmsg') or body.get('msg')}")
    return {"channel": channel, "delivered": 1, "response": body}


def send_dingtalk(title: str, content: str, link: str | None = None) -> dict:
    _require("dingtalk", dingtalk_webhook_url=settings.dingtalk_webhook_url)
    url = settings.dingtalk_webhook_url
    if settings.dingtalk_secret:
        ts, sign = _sign_dingtalk(settings.dingtalk_secret)
        url = f"{url}&timestamp={ts}&sign={sign}"
    text = f"### {title}\n{content}"
    if link:
        text += f"\n\n[查看详情]({link})"
    return _post_robot("dingtalk", url, {"msgtype": "markdown", "markdown": {"title": title, "text": text}})


def send_wecom(title: str, content: str, link: str | None = None) -> dict:
    _require("wecom", wecom_webhook_url=settings.wecom_webhook_url)
    text = f"**{title}**\n{content}"
    if link:
        text += f"\n\n[查看详情]({link})"
    return _post_robot("wecom", settings.wecom_webhook_url, {"msgtype": "markdown", "markdown": {"content": text[:4000]}})


def send_feishu(title: str, content: str, link: str | None = None) -> dict:
    _require("feishu", feishu_webhook_url=settings.feishu_webhook_url)
    lines = [title, content] + ([link] if link else [])
    return _post_robot("feishu", settings.feishu_webhook_url, {"msg_type": "text", "content": {"text": "\n".join(lines)}})


CHANNELS = {
    "email": send_email,
    "dingtalk": send_dingtalk,
    "wecom": send_wecom,
    "feishu": send_feishu,
}

# 每个通道判定"已配置"所需的凭据,供 /status 与前端置灰使用
REQUIRED_KEYS = {
    "email": ["smtp_host", "smtp_user", "smtp_password"],
    "dingtalk": ["dingtalk_webhook_url"],
    "wecom": ["wecom_webhook_url"],
    "feishu": ["feishu_webhook_url"],
}


def send(channel: str, title: str, content: str, receivers: list[str], link: str | None = None) -> dict:
    if channel not in CHANNELS:
        raise IntegrationError(channel, f"不支持的通道,可选: {'/'.join(sorted(CHANNELS))}")
    fn = CHANNELS[channel]
    if channel == "email":
        return fn(title, content, receivers)
    return fn(title, content, link)


def channel_status() -> dict:
    out = {}
    for name, keys in REQUIRED_KEYS.items():
        missing = [k for k in keys if not getattr(settings, k, "")]
        out[name] = {"configured": not missing, "missing_keys": missing}
    return out
