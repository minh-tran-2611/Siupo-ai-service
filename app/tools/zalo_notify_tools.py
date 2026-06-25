import os
import json
from loguru import logger
from app.service.zalo_service import send_text_message

ZALO_ADMIN_CHAT_ID = os.getenv("ZALO_ADMIN_CHAT_ID", "")


async def send_zalo_notification(message: str) -> str:
    """Send a proactive Zalo message to the admin chat. Called by orchestrator via function calling.

    Args:
        message: Text to send (markdown will be stripped automatically)

    Returns:
        JSON string with result
    """
    logger.info(f"Zalo tool: Sending notification ({len(message)} chars)")

    if not ZALO_ADMIN_CHAT_ID:
        logger.warning("Zalo tool: ZALO_ADMIN_CHAT_ID not configured")
        return json.dumps({"ok": False, "error": "ZALO_ADMIN_CHAT_ID not configured"})

    results = await send_text_message(ZALO_ADMIN_CHAT_ID, message)
    ok = all(r.get("ok") for r in results)
    return json.dumps({"ok": ok, "chunks_sent": len(results)}, ensure_ascii=False)
