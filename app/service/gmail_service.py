"""
Gmail Service — Send email notifications to admin via SMTP.

Uses aiosmtplib for async SMTP to avoid blocking the FastAPI event loop.
Designed for the restaurant AI agent to send important notifications
(reports, alerts, summaries) to the admin.

Configuration via .env:
- GMAIL_SENDER_EMAIL: The Gmail address used to send emails
- GMAIL_APP_PASSWORD: Google App Password (16 chars, requires 2FA enabled)
- GMAIL_ADMIN_EMAIL: Default recipient (admin email)
"""
import os
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from loguru import logger

GMAIL_SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
GMAIL_ADMIN_EMAIL = os.getenv("GMAIL_ADMIN_EMAIL", "")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _build_html_email(subject: str, body: str, priority: str = "normal") -> str:
    """Build a styled HTML email with Siupo restaurant branding.

    Args:
        subject: Email subject
        body: Email body content (plain text — will be formatted into HTML)
        priority: 'normal' or 'urgent'
    """
    priority_color = "#e74c3c" if priority == "urgent" else "#00B14F"
    priority_badge = (
        '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:4px;'
        'font-size:12px;font-weight:600;">⚠ URGENT</span>'
        if priority == "urgent" else ""
    )

    # Convert newlines to <br> for body text
    body_html = body.replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <!-- Header -->
    <tr>
      <td style="background:linear-gradient(135deg,{priority_color},#2c3e50);padding:24px 32px;">
        <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700;">
          🍜 Siupo Restaurant
        </h1>
        <p style="margin:4px 0 0;color:rgba(255,255,255,0.8);font-size:13px;">AI Assistant Notification</p>
      </td>
    </tr>
    <!-- Body -->
    <tr>
      <td style="padding:24px 32px;">
        <div style="margin-bottom:16px;">
          {priority_badge}
          <h2 style="margin:8px 0 0;color:#2c3e50;font-size:18px;">{subject}</h2>
        </div>
        <div style="color:#555;font-size:14px;line-height:1.7;">
          {body_html}
        </div>
      </td>
    </tr>
    <!-- Footer -->
    <tr>
      <td style="padding:16px 32px;background:#f9f9f9;border-top:1px solid #eee;">
        <p style="margin:0;color:#999;font-size:12px;">
          Email này được gửi tự động bởi Siupo AI Assistant.<br>
          Vui lòng không trả lời email này.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>"""


async def send_email(
    to_email: str | None = None,
    subject: str = "",
    body: str = "",
    priority: str = "normal",
) -> dict:
    """Send an HTML email via Gmail SMTP.

    Args:
        to_email: Recipient email (defaults to GMAIL_ADMIN_EMAIL)
        subject: Email subject line
        body: Email body content (plain text, will be HTML-formatted)
        priority: 'normal' or 'urgent' (affects styling)

    Returns:
        dict with 'ok' and 'message' keys
    """
    recipient = to_email or GMAIL_ADMIN_EMAIL

    if not GMAIL_SENDER_EMAIL or not GMAIL_APP_PASSWORD:
        logger.warning("Gmail: Not configured (missing GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD)")
        return {
            "ok": False,
            "message": "Gmail chưa được cấu hình. Cần GMAIL_SENDER_EMAIL và GMAIL_APP_PASSWORD trong .env"
        }

    if not recipient:
        return {"ok": False, "message": "Không có email người nhận"}

    try:
        # Build MIME message
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Siupo AI Assistant <{GMAIL_SENDER_EMAIL}>"
        msg["To"] = recipient
        msg["Subject"] = subject

        # Add priority header for urgent emails
        if priority == "urgent":
            msg["X-Priority"] = "1"
            msg["Importance"] = "High"

        # Plain text fallback
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # HTML version
        html_body = _build_html_email(subject, body, priority)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # Send via SMTP
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            start_tls=True,
            username=GMAIL_SENDER_EMAIL,
            password=GMAIL_APP_PASSWORD,
        )

        logger.info(f"Gmail: Email sent to {recipient} — subject='{subject}'")
        return {
            "ok": True,
            "message": f"Đã gửi email thành công đến {recipient}",
            "to": recipient,
            "subject": subject,
        }

    except aiosmtplib.SMTPAuthenticationError as e:
        logger.error(f"Gmail: Authentication failed: {e}")
        return {
            "ok": False,
            "message": "Xác thực Gmail thất bại. Kiểm tra GMAIL_SENDER_EMAIL và GMAIL_APP_PASSWORD."
        }
    except Exception as e:
        logger.error(f"Gmail: Send failed: {e}")
        return {"ok": False, "message": f"Gửi email thất bại: {str(e)}"}
