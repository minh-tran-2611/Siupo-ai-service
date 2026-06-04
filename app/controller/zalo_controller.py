"""
Zalo Bot Webhook Controller — Receives events from Zalo Platform.

Flow:
1. Zalo sends POST /webhook/zalo with JSON body + X-Bot-Api-Secret-Token header
2. We verify the secret token
3. Parse event_name to determine message type
4. For text/image messages: call chat_service.chat() with mapped user_id
5. Send response back via zalo_service.send_text_message()
6. Return 200 immediately to Zalo (async processing)

User IDs are prefixed with "zalo_" to namespace them separately from admin users.
"""
import os
import asyncio
import traceback
from fastapi import APIRouter, Request, HTTPException
from loguru import logger

from app.request.zalo_request import ZaloWebhookEvent
from app.service.chat_service import chat
from app.service.zalo_service import (
    send_text_message,
    send_chat_action,
    download_image,
    set_webhook,
    delete_webhook,
    get_webhook_info,
    get_me,
)

router = APIRouter()

ZALO_WEBHOOK_SECRET = os.getenv("ZALO_WEBHOOK_SECRET", "")

# Supported message events
TEXT_EVENT = "message.text.received"
IMAGE_EVENT = "message.image.received"
STICKER_EVENT = "message.sticker.received"
UNSUPPORTED_EVENT = "message.unsupported.received"


def _map_user_id(zalo_user_id: str) -> str:
    """Map Zalo user ID to internal user ID with prefix."""
    return f"zalo_{zalo_user_id}"


async def _process_zalo_message(event: ZaloWebhookEvent):
    """Background task to process a Zalo message and send reply.

    Runs asynchronously so the webhook endpoint can return 200 immediately
    (Zalo has a timeout on webhook responses).
    """
    message = event.message

    if not message:
        logger.warning("Zalo webhook: No message in event")
        return

    user_id = _map_user_id(message.from_user.id)
    chat_id = message.chat.id
    display_name = message.from_user.display_name

    logger.info(
        f"Zalo: Processing {event.event_name} from "
        f"{display_name} (user_id={user_id}, chat_id={chat_id})"
    )

    try:
        # ── Handle text messages ──────────────────────────────────────
        if event.event_name == TEXT_EVENT:
            if not message.text:
                logger.warning("Zalo: Text event but no text content")
                return

            # Show typing indicator while processing
            await send_chat_action(chat_id, "typing")

            result = await chat(user_id, message.text)
            reply = result["reply"] if isinstance(result, dict) else result
            await send_text_message(chat_id, reply)

        # ── Handle image messages ─────────────────────────────────────
        elif event.event_name == IMAGE_EVENT:
            await send_chat_action(chat_id, "typing")

            images = []
            if message.photo:
                img_data = await download_image(message.photo)
                if img_data:
                    images.append(img_data)

            text = message.caption or "Hãy mô tả và phân tích hình ảnh này."
            result = await chat(user_id, text, images=images)
            reply = result["reply"] if isinstance(result, dict) else result
            await send_text_message(chat_id, reply)

        # ── Handle sticker messages ───────────────────────────────────
        elif event.event_name == STICKER_EVENT:
            await send_text_message(
                chat_id,
                "Tôi nhận được sticker của bạn! 😊 Bạn cần hỗ trợ gì không?"
            )

        # ── Unsupported messages ──────────────────────────────────────
        elif event.event_name == UNSUPPORTED_EVENT:
            await send_text_message(
                chat_id,
                "Xin lỗi, tôi chưa hỗ trợ loại tin nhắn này. "
                "Bạn có thể gửi tin nhắn văn bản hoặc hình ảnh nhé!"
            )

        else:
            logger.info(f"Zalo: Unhandled event: {event.event_name}")

    except Exception as e:
        logger.error(
            f"Zalo: Error processing message from {display_name}: {e}\n"
            f"{traceback.format_exc()}"
        )
        try:
            await send_text_message(
                chat_id,
                "Xin lỗi, đã có lỗi xảy ra khi xử lý tin nhắn. "
                "Vui lòng thử lại sau."
            )
        except Exception:
            logger.error("Zalo: Failed to send error message back to user")


@router.post("/webhook/zalo")
async def zalo_webhook(request: Request):
    """Receive webhook events from Zalo Platform."""
    # ── Verify secret token ───────────────────────────────────────────
    secret_token = request.headers.get("x-bot-api-secret-token", "")
    if ZALO_WEBHOOK_SECRET and secret_token != ZALO_WEBHOOK_SECRET:
        logger.warning(f"Zalo webhook: Invalid secret token: {secret_token[:8]}...")
        raise HTTPException(status_code=403, detail="Unauthorized")

    # ── Parse event ───────────────────────────────────────────────────
    try:
        body = await request.json()
        logger.info(f"Zalo webhook raw payload: {body}")
        event = ZaloWebhookEvent(**body)
    except Exception as e:
        logger.error(f"Zalo webhook: Failed to parse payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    logger.info(f"Zalo webhook: event={event.event_name}")

    # ── Process asynchronously — return 200 immediately ───────────────
    asyncio.create_task(_process_zalo_message(event))

    return {"message": "Success"}


# ── Admin endpoints for webhook management ────────────────────────────────────

@router.get("/zalo/me")
async def zalo_get_me():
    """Verify bot token and get bot info."""
    return await get_me()


@router.post("/zalo/setup-webhook")
async def setup_zalo_webhook(request: Request):
    """Register webhook URL with Zalo Bot Platform.

    Body: {"url": "https://xxx.ngrok-free.dev/api/webhook/zalo"}
    """
    body = await request.json()
    url = body.get("url")
    secret = body.get("secret_token", ZALO_WEBHOOK_SECRET)

    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    if not secret or len(secret) < 8:
        raise HTTPException(status_code=400, detail="secret_token must be 8-256 chars")

    result = await set_webhook(url, secret)
    return result


@router.delete("/zalo/webhook")
async def remove_zalo_webhook():
    """Remove the current Zalo webhook."""
    return await delete_webhook()


@router.get("/zalo/webhook")
async def get_zalo_webhook():
    """Get current Zalo webhook info."""
    return await get_webhook_info()