"""
Zalo Bot Service — Send messages and manage webhook via Zalo Bot HTTP API.

API base: https://bot-api.zaloplatforms.com/bot{TOKEN}/
Docs: https://bot.zapps.me/docs/

Key constraints:
- sendMessage text is limited to 2000 characters per message
- Webhook URL must be HTTPS
- secret_token for webhook verification: 8-256 characters
"""
import os
import re
import httpx
from loguru import logger

ZALO_BOT_TOKEN = os.getenv("ZALO_BOT_TOKEN", "")
ZALO_API_BASE = f"https://bot-api.zaloplatforms.com/bot{ZALO_BOT_TOKEN}"

MAX_TEXT_LENGTH = 2000


def _get_api_url(method: str) -> str:
    return f"{ZALO_API_BASE}/{method}"


def _strip_markdown(text: str) -> str:
    """Convert markdown to plain text for Zalo (which doesn't render markdown)."""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'(?<!\w)_(.*?)_(?!\w)', r'\1', text)
    text = re.sub(r'~~(.*?)~~', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'```[\w]*\n?(.*?)```', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'\1 (\2)', text)
    text = re.sub(r'!\[(.*?)\]\((.*?)\)', r'[Hình: \1]', text)
    text = re.sub(r'^[\s]*[-*+]\s', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^---+$', '―――', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _split_text(text: str, max_len: int = MAX_TEXT_LENGTH) -> list[str]:
    """Split text into chunks that fit Zalo's 2000-character limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        split_pos = remaining.rfind('\n\n', 0, max_len)
        if split_pos > max_len * 0.3:
            chunks.append(remaining[:split_pos].rstrip())
            remaining = remaining[split_pos:].lstrip()
            continue

        split_pos = remaining.rfind('\n', 0, max_len)
        if split_pos > max_len * 0.3:
            chunks.append(remaining[:split_pos].rstrip())
            remaining = remaining[split_pos:].lstrip()
            continue

        for sep in ['. ', '! ', '? ', '。']:
            split_pos = remaining.rfind(sep, 0, max_len)
            if split_pos > max_len * 0.3:
                chunks.append(remaining[:split_pos + 1].rstrip())
                remaining = remaining[split_pos + 1:].lstrip()
                break
        else:
            split_pos = remaining.rfind(' ', 0, max_len)
            if split_pos > 0:
                chunks.append(remaining[:split_pos].rstrip())
                remaining = remaining[split_pos:].lstrip()
            else:
                chunks.append(remaining[:max_len])
                remaining = remaining[max_len:]

    return [c for c in chunks if c.strip()]


async def send_chat_action(chat_id: str, action: str = "typing") -> dict:
    """Send a chat action (e.g. typing indicator) to a Zalo chat.

    Args:
        chat_id: The chat ID from webhook
        action: "typing" or "upload_photo"

    Returns:
        API response dict
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                _get_api_url("sendChatAction"),
                json={"chat_id": chat_id, "action": action},
            )
            return resp.json()
        except Exception as e:
            logger.warning(f"Zalo: sendChatAction failed: {e}")
            return {"ok": False}


async def send_text_message(chat_id: str, text: str) -> list[dict]:
    """Send a text message to a Zalo user/chat.

    Automatically strips markdown and splits long messages into ≤2000 char chunks.

    Args:
        chat_id: The chat ID from webhook (message.chat.id)
        text: The response text (may contain markdown, may exceed 2000 chars)

    Returns:
        List of API responses (one per chunk sent)
    """
    clean_text = _strip_markdown(text)
    chunks = _split_text(clean_text)

    results = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for i, chunk in enumerate(chunks):
            try:
                resp = await client.post(
                    _get_api_url("sendMessage"),
                    json={"chat_id": chat_id, "text": chunk},
                )
                data = resp.json()

                if data.get("ok"):
                    logger.info(
                        f"Zalo: Sent chunk {i+1}/{len(chunks)} "
                        f"to chat_id={chat_id}, "
                        f"msg_id={data.get('result', {}).get('message_id', 'N/A')}"
                    )
                else:
                    logger.warning(f"Zalo: sendMessage failed: {data}")

                results.append(data)
            except Exception as e:
                logger.error(f"Zalo: sendMessage error for chunk {i+1}: {e}")
                results.append({"ok": False, "error": str(e)})

    return results


async def send_photo(chat_id: str, photo_url: str, caption: str = "") -> dict:
    """Send a photo message to a Zalo user/chat.

    Args:
        chat_id: The chat ID from webhook
        photo_url: Public HTTPS URL of the image
        caption: Optional caption (max 2000 chars)

    Returns:
        API response dict
    """
    payload = {"chat_id": chat_id, "photo": photo_url}
    if caption:
        payload["caption"] = caption[:MAX_TEXT_LENGTH]

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(_get_api_url("sendPhoto"), json=payload)
            data = resp.json()
            if data.get("ok"):
                logger.info(f"Zalo: Photo sent to chat_id={chat_id}")
            else:
                logger.warning(f"Zalo: sendPhoto failed: {data}")
            return data
        except Exception as e:
            logger.error(f"Zalo: sendPhoto error: {e}")
            return {"ok": False, "error": str(e)}


async def get_me() -> dict:
    """Verify bot token and get basic bot info."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(_get_api_url("getMe"))
        return resp.json()


async def set_webhook(url: str, secret_token: str) -> dict:
    """Register a webhook URL with Zalo Bot Platform."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _get_api_url("setWebhook"),
            json={"url": url, "secret_token": secret_token},
        )
        data = resp.json()
        if data.get("ok"):
            logger.info(f"Zalo: Webhook set successfully → {url}")
        else:
            logger.error(f"Zalo: setWebhook failed: {data}")
        return data


async def delete_webhook() -> dict:
    """Remove the current webhook URL."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(_get_api_url("deleteWebhook"))
        data = resp.json()
        logger.info(f"Zalo: deleteWebhook result: {data}")
        return data


async def get_webhook_info() -> dict:
    """Get current webhook configuration."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(_get_api_url("getWebhookInfo"))
        return resp.json()


async def download_image(photo_url: str) -> dict | None:
    """Download an image from Zalo's photo URL.

    Returns dict with 'bytes' and 'mime' keys, or None if download fails.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(photo_url)
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "image/jpeg")
                mime = content_type.split(";")[0].strip()
                return {"bytes": resp.content, "mime": mime}
            else:
                logger.warning(f"Zalo: Image download failed, status={resp.status_code}")
                return None
    except Exception as e:
        logger.error(f"Zalo: Image download error: {e}")
        return None