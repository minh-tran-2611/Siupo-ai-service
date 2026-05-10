"""
In-memory conversation cache for short-term context.

Stores raw conversation history per session for LLM context.

Lifecycle (lazy-write strategy):
- Per-turn writes go ONLY to this cache (RAM). No Turso write.
- On TTL expiry OR explicit clear, the session's messages are flushed to Turso
  via a registered flush_callback (one row per message, raw text only).
- This guarantees memories table never overlaps with the active session,
  so retrieval can read cache + memories without de-dup logic.

Image handling:
- A user message can carry images=[{bytes, mime, hint}] in addition to content.
- Image bytes live in RAM only. After the orchestrator reply, a background
  image_describer call replaces bytes with a text description via
  replace_images_with_description(turn_id, desc). Bytes are then GC'd.
- On flush, only text (content + description) is persisted. Bytes never reach Turso.
"""
from datetime import datetime
from typing import Optional, Callable, Awaitable
from loguru import logger

# Format: {session_id: {
#   "user_id": str,
#   "messages": [{role, content, images?, turn_id?}],
#   "last_access": datetime,
#   "session_start": datetime,
# }}
_cache: dict[str, dict] = {}

# TTL in seconds (30 minutes)
CACHE_TTL = 1800

# Max messages per session (to limit token usage)
MAX_MESSAGES = 20

# Cleanup runs at most once every 5 minutes instead of on every cache access
_CLEANUP_INTERVAL = 300
_last_cleanup: datetime = datetime.min

# Monotonic counter for turn ids (used to target image replacement)
_turn_counter: int = 0

# Registered async flush callback: (user_id, raw_messages: list[str]) -> awaitable
FlushCallback = Callable[[str, list[str]], Awaitable[None]]
_flush_callback: Optional[FlushCallback] = None


def register_flush_callback(cb: FlushCallback) -> None:
    """Register the function to call when a session is evicted or cleared.

    Receives (user_id, list of formatted raw_message strings).
    """
    global _flush_callback
    _flush_callback = cb
    logger.info("ConversationCache: flush callback registered")


def _next_turn_id() -> int:
    global _turn_counter
    _turn_counter += 1
    return _turn_counter


def _format_message_for_flush(msg: dict) -> str:
    """Render a cache message as a single raw_message string for the memories table."""
    role = "User" if msg["role"] == "user" else "Assistant"
    text = msg.get("content", "")
    if msg.get("images"):
        # Bytes still in cache (no description yet) — fallback marker
        # so flushed row reflects that an image was present.
        text = f"{text}\n[Hình ảnh: chưa có mô tả]" if text else "[Hình ảnh: chưa có mô tả]"
    return f"{role}: {text}"


async def _flush_session(sid: str, session: dict) -> None:
    """Flush a session's messages via the callback, then clear them."""
    if _flush_callback is None:
        return
    msgs = session.get("messages", [])
    if not msgs:
        return
    user_id = session.get("user_id", "")
    raw_messages = [_format_message_for_flush(m) for m in msgs]
    try:
        await _flush_callback(user_id, raw_messages)
        logger.info(f"ConversationCache: Flushed {len(raw_messages)} messages for session {sid}")
    except Exception as e:
        logger.error(f"ConversationCache: Flush failed for session {sid}: {e}")


async def cleanup_expired_with_flush() -> int:
    """Remove expired sessions, flushing their messages first. Returns count flushed."""
    now = datetime.now()
    expired_sids = [
        sid for sid, data in _cache.items()
        if (now - data["last_access"]).total_seconds() > CACHE_TTL
    ]
    flushed = 0
    for sid in expired_sids:
        session = _cache.pop(sid, None)
        if session is None:
            continue
        await _flush_session(sid, session)
        flushed += 1
    if flushed:
        logger.info(f"ConversationCache: Evicted {flushed} expired session(s)")
    return flushed


def _cleanup_expired_no_flush():
    """Remove expired sessions WITHOUT flushing (sync fallback for in-band cleanup).

    Used by sync access paths to drop stale sessions cheaply. The proper flushing
    cleanup is the async cleanup_expired_with_flush() called by the scheduler.
    """
    now = datetime.now()
    expired = [
        sid for sid, data in _cache.items()
        if (now - data["last_access"]).total_seconds() > CACHE_TTL
    ]
    for sid in expired:
        del _cache[sid]
        logger.debug(f"ConversationCache: Expired session {sid} (no flush)")


def _maybe_cleanup():
    """Run cheap sync cleanup periodically. Real flush happens via scheduler."""
    global _last_cleanup
    now = datetime.now()
    if (now - _last_cleanup).total_seconds() >= _CLEANUP_INTERVAL:
        _cleanup_expired_no_flush()
        _last_cleanup = now


def get_session_id(user_id: str, session_id: Optional[str] = None) -> str:
    return session_id or f"user_{user_id}"


def get_session_start(user_id: str, session_id: Optional[str] = None) -> Optional[datetime]:
    """Return the start time of the active session, or None if no session exists."""
    sid = get_session_id(user_id, session_id)
    sess = _cache.get(sid)
    return sess["session_start"] if sess else None


def get_conversation(user_id: str, session_id: Optional[str] = None) -> list[dict]:
    """Get conversation history for a session.

    Returns a copy of the message list. Each message has {role, content, images?, turn_id?}.
    Callers (orchestrator) decide how to render images in LLM parts.
    """
    _maybe_cleanup()
    sid = get_session_id(user_id, session_id)
    if sid in _cache:
        _cache[sid]["last_access"] = datetime.now()
        return [m.copy() for m in _cache[sid]["messages"]]
    return []


def add_message(
    user_id: str,
    role: str,
    content: str,
    images: Optional[list[dict]] = None,
    session_id: Optional[str] = None,
) -> int:
    """Add a message to conversation history.

    Args:
        role: 'user' or 'assistant'
        content: Text content
        images: Optional list of {bytes, mime, hint} dicts. Bytes live in RAM only.

    Returns:
        turn_id of the inserted message (use for replace_images_with_description).
    """
    _maybe_cleanup()
    sid = get_session_id(user_id, session_id)
    now = datetime.now()
    if sid not in _cache:
        _cache[sid] = {
            "user_id": user_id,
            "messages": [],
            "last_access": now,
            "session_start": now,
        }
    turn_id = _next_turn_id()
    msg: dict = {"role": role, "content": content, "turn_id": turn_id}
    if images:
        msg["images"] = images
    _cache[sid]["messages"].append(msg)
    _cache[sid]["last_access"] = now

    # Trim to MAX_MESSAGES (keep newest)
    if len(_cache[sid]["messages"]) > MAX_MESSAGES:
        _cache[sid]["messages"] = _cache[sid]["messages"][-MAX_MESSAGES:]

    logger.debug(
        f"ConversationCache: Added {role} message to {sid}, "
        f"turn_id={turn_id}, total={len(_cache[sid]['messages'])}, has_images={bool(images)}"
    )
    return turn_id


def replace_images_with_description(
    user_id: str,
    turn_id: int,
    description: str,
    session_id: Optional[str] = None,
) -> bool:
    """Replace image bytes on a turn with a text description.

    Called by the background image_describer pipeline. Drops bytes (frees memory)
    and appends "[Hình ảnh: <description>]" to the message content so future
    turns in the same session retain visual context as text.

    Returns True if replaced, False if turn not found.
    """
    sid = get_session_id(user_id, session_id)
    sess = _cache.get(sid)
    if not sess:
        return False
    for msg in sess["messages"]:
        if msg.get("turn_id") == turn_id:
            existing = msg.get("content", "")
            suffix = f"[Hình ảnh: {description}]"
            msg["content"] = f"{existing}\n{suffix}" if existing else suffix
            msg.pop("images", None)
            logger.info(f"ConversationCache: Replaced images on turn {turn_id} with description")
            return True
    logger.warning(f"ConversationCache: turn_id {turn_id} not found in session {sid}")
    return False


async def clear_conversation(user_id: str, session_id: Optional[str] = None):
    """Clear conversation history, flushing to memories first."""
    sid = get_session_id(user_id, session_id)
    session = _cache.pop(sid, None)
    if session is None:
        return
    await _flush_session(sid, session)
    logger.info(f"ConversationCache: Cleared session {sid}")


def get_cache_stats() -> dict:
    """Get cache statistics for monitoring."""
    _maybe_cleanup()
    return {
        "active_sessions": len(_cache),
        "total_messages": sum(len(d["messages"]) for d in _cache.values())
    }
