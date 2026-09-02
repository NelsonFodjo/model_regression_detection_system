"""Send classified email summaries through SMTP."""

import os
import smtplib
from email.message import EmailMessage


def format_email(details: dict, result: dict) -> tuple[str, str]:
    """Return the subject and plain-text body for a summary email."""
    subject = f"[{result['category']}] {details['subject']}"
    body = (
        "EMAIL SUMMARY\n"
        f"Category: {result['category']}\n\n"
        "SUMMARY\n"
        f"{result['summary']}\n\n"
        "EMAIL DETAILS\n"
        f"From: {details['sender']}\n"
        f"Subject: {details['subject']}"
    )
    return subject, body


def send_email_summary(details: dict, result: dict) -> None:
    """Send one summary email using the configured SMTP server."""
    settings = {
        "SMTP_HOST": os.environ.get("SMTP_HOST"),
        "SMTP_USERNAME": os.environ.get("SMTP_USERNAME"),
        "SMTP_PASSWORD": os.environ.get("SMTP_PASSWORD"),
        "EMAIL_FROM": os.environ.get("EMAIL_FROM"),
        "EMAIL_TO": os.environ.get("EMAIL_TO"),
    }
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise RuntimeError(f"Set email configuration in .env: {', '.join(missing)}")

    port = int(os.environ.get("SMTP_PORT", "587"))
    use_ssl = os.environ.get("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"}
    subject, body = format_email(details, result)

    message = EmailMessage()
    message["From"] = settings["EMAIL_FROM"]
    message["To"] = settings["EMAIL_TO"]
    message["Subject"] = subject
    message.set_content(body)

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_class(settings["SMTP_HOST"], port, timeout=20) as smtp:
        if not use_ssl:
            smtp.starttls()
        smtp.login(settings["SMTP_USERNAME"], settings["SMTP_PASSWORD"])
        smtp.send_message(message)