"""Dual-channel alerts: WeCom webhook (primary) + SMTP email (fallback).

Channels are independent by contract: one failing never blocks the other,
and alert failures never alter trading safety state.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.request
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _wecom_webhook() -> str:
    return os.environ.get("TRADING_WECOM_WEBHOOK", "").strip()


def send_wecom(text: str) -> bool:
    url = _wecom_webhook()
    if not url:
        logger.warning("wecom webhook not configured; alert dropped: %s", text)
        return False
    payload = json.dumps({"msgtype": "text", "text": {"content": text}}).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 - configured webhook URL
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            ok = resp.status == 200
    except Exception as exc:
        logger.error("wecom alert failed: %s", exc)
        return False
    if not ok:
        logger.error("wecom alert got non-200: %s", resp.status)
    return ok


def send_email(subject: str, body: str) -> bool:
    host = os.environ.get("TRADING_SMTP_HOST", "").strip()
    to = os.environ.get("TRADING_ALERT_EMAIL_TO", "").strip()
    if not host or not to:
        logger.warning("email alert not configured; alert dropped: %s", subject)
        return False
    port = int(os.environ.get("TRADING_SMTP_PORT", "465"))
    user = os.environ.get("TRADING_SMTP_USER", "").strip()
    password = os.environ.get("TRADING_SMTP_PASS", "").strip()
    sender = os.environ.get("TRADING_ALERT_EMAIL_FROM", user).strip() or user
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    try:
        with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
            if user and password:
                smtp.login(user, password)
            smtp.sendmail(sender, [to], msg.as_string())
        return True
    except Exception as exc:
        logger.error("email alert failed: %s", exc)
        return False


def alert(text: str) -> dict[str, bool]:
    """Send over every configured channel; returns per-channel results."""
    return {
        "wecom": send_wecom(text),
        "email": send_email("[trading-bot] alert", text),
    }
