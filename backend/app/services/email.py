"""Get/set Gmail config + test send."""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.services.yaml_io import read_yaml, write_yaml


def get_email_config() -> dict[str, Any]:
    secrets = read_yaml("secrets.yaml")
    gmail = secrets.get("gmail", {}) or {}
    pwd = gmail.get("app_password", "") or ""
    return {
        "email": gmail.get("email", "") or "",
        "app_password_set": bool(pwd),
        "app_password_preview": "••••" + pwd[-4:] if len(pwd) >= 8 else "",
    }


def set_email_config(*, email: str, app_password: str | None = None) -> dict[str, Any]:
    secrets = read_yaml("secrets.yaml")
    gmail = secrets.setdefault("gmail", {})
    gmail["email"] = email.strip()
    if app_password is not None and app_password.strip():
        gmail["app_password"] = app_password.strip()
    secrets["gmail"] = gmail
    write_yaml("secrets.yaml", secrets)
    return get_email_config()


def send_test(*, to: str | None = None) -> dict[str, Any]:
    """Send a test email to verify Gmail credentials work."""
    cfg = read_yaml("secrets.yaml").get("gmail", {}) or {}
    user = cfg.get("email", "")
    pwd = cfg.get("app_password", "")
    if not user or not pwd:
        raise RuntimeError("Gmail email/app_password not configured")
    recipient = (to or user).strip() or user
    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = recipient
    msg["Subject"] = "Professor+ — test d'envoi"
    msg.attach(MIMEText(
        "Ceci est un test d'envoi depuis le nouveau dashboard Next.js.\n"
        "Si tu reçois ce mail, la configuration Gmail est OK.",
        "plain", "utf-8",
    ))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
        smtp.login(user, pwd)
        smtp.send_message(msg)
    return {"sent_to": recipient, "from": user}
