"""
Gmail Tools — Orchestrator-level tool for sending email notifications.

Registered as an orchestrator meta-tool so the AI agent can decide when
to send emails based on conversation context.
"""
import json
from loguru import logger
from app.service.gmail_service import send_email


async def send_email_notification(
    to_email: str = "",
    subject: str = "",
    body: str = "",
    priority: str = "normal",
) -> str:
    """Send an email notification. Called by orchestrator via function calling.

    Args:
        to_email: Recipient email (optional, defaults to admin email from .env)
        subject: Email subject
        body: Email body content
        priority: 'normal' or 'urgent'

    Returns:
        JSON string with result
    """
    logger.info(f"Gmail tool: Sending email — subject='{subject}', priority={priority}")

    result = await send_email(
        to_email=to_email or None,
        subject=subject,
        body=body,
        priority=priority,
    )

    return json.dumps(result, ensure_ascii=False)
