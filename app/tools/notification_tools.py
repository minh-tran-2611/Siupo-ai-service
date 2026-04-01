import os
import httpx
from loguru import logger
from app.tools.auth_tools import ensure_authenticated, get_auth_headers

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def get_all_notifications_admin() -> dict:
    """Get all notifications (admin view). Requires authentication."""
    logger.info("Tool: get_all_notifications_admin")
    
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/notifications/admin",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def create_notification(title: str, content: str, user_id: int = None, send_to_all: bool = False) -> dict:
    """
    Create a new notification (admin only). Requires authentication.
    - title: notification title (required)
    - content: notification content (required)
    - user_id: specific user ID to send to (optional)
    - send_to_all: if True, send to all users (default: False)
    """
    logger.info(f"Tool: create_notification(title={title}, user_id={user_id}, send_to_all={send_to_all})")
    
    await ensure_authenticated()
    
    data = {
        "title": title,
        "content": content,
        "sendToAll": send_to_all
    }
    if user_id is not None:
        data["userId"] = user_id

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BE_BASE_URL}/api/notifications/admin",
            json=data,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_my_notifications() -> dict:
    """Get notifications for the current user. Requires authentication."""
    logger.info("Tool: get_my_notifications")
    
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/notifications/customer",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()
