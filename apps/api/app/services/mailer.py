"""Outgoing email. Without SMTP_HOST it logs and records in `outbox`; with it, sends through SMTP."""

import logging
import smtplib
from email.message import EmailMessage

from ..config import get_settings

log = logging.getLogger("vakeelsevak.mail")
outbox: list[dict] = []  # inspected by tests


def send(to: str, subject: str, body: str) -> None:
    outbox.append({"to": to, "subject": subject, "body": body})
    s = get_settings()
    if not s.smtp_host:
        log.info("MAIL to=%s subject=%s\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
