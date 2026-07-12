"""Email sending utilities with SMTP + console fallback."""

import logging
import secrets
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

import config

logger = logging.getLogger(__name__)


def generate_verification_code(length: int = 6) -> str:
    """Return a numeric verification code."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def send_email(to_email: str, subject: str, body_text: str, body_html: str = "") -> bool:
    """Send an email via SMTP if configured; otherwise log it."""
    if not all([config.SMTP_HOST, config.SMTP_USER, config.SMTP_PASSWORD]):
        logger.warning(
            "SMTP not configured; printing email instead. "
            "To: %s | Subject: %s",
            to_email,
            subject,
        )
        print("=" * 50)
        print(f"EMAIL TO: {to_email}")
        print(f"SUBJECT: {subject}")
        print(body_text)
        print("=" * 50)
        return True

    sender = config.EMAIL_FROM or config.SMTP_USER
    msg = MIMEText(body_html or body_text, "html" if body_html else "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("LinkedIn Auto-Poster", sender))
    msg["To"] = to_email

    try:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT)
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.sendmail(sender, [to_email], msg.as_string())
        server.quit()
        logger.info("Verification email sent to %s", to_email)
        return True
    except Exception as e:
        logger.exception("Failed to send email to %s: %s", to_email, e)
        return False


def send_verification_email(
    to_email: str,
    code: str,
    name: str = "",
    to_name: str = "",
    subject: str = "Your LinkedIn Auto-Poster verification code",
) -> bool:
    """Send the verification code email to a new user."""
    greeting_name = name or to_name or "there"
    greeting = f"Hi {greeting_name},"
    text_body = (
        f"{greeting}\n\n"
        f"Your verification code is: {code}\n\n"
        "Enter this code in the app to complete your signup.\n\n"
        "If you did not sign up, you can ignore this email."
    )
    html_body = f"""
    <html>
      <body style="font-family: Inter, Arial, sans-serif; color: #1e293b;">
        <p>{greeting}</p>
        <p>Your verification code is:</p>
        <p style="font-size: 24px; letter-spacing: 4px; font-weight: bold;">{code}</p>
        <p>Enter this code in the app to complete your signup.</p>
        <p style="color: #64748b;">If you did not sign up, you can ignore this email.</p>
      </body>
    </html>
    """
    return send_email(to_email, subject, text_body, html_body)
