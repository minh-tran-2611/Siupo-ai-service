"""
In-memory conversation cache for short-term context.
Stores raw conversation history per session for LLM context.
"""
from datetime import datetime
from typing import Optional
from loguru import logger

# Format: {session_id: {"messages": [...], "last_access": datetime}}
_cache: dict[str, dict] = {}

# TTL in seconds (30 minutes)
CACHE_TTL = 1800

# Max messages per session (to limit token usage)
MAX_MESSAGES = 20

# Cleanup runs at most once every 5 minutes instead of on every cache access
_CLEANUP_INTERVAL = 300
_last_cleanup: datetime = datetime.min


def _maybe_cleanup():
    """Remove expired sessions."""
    now = datetime.now()
    expired = [
        sid for sid, data in _cache.items()
        if (now - data["last_access"]).total_seconds() > CACHE_TTL
    ]
    for sid in expired:
        del _cache[sid]
        logger.debug(f"ConversationCache: Expired session {sid}")


def _maybe_cleanup():
    """Run cleanup only if enough time has passed since last run."""
    global _last_cleanup
    now = datetime.now()
    if (now - _last_cleanup).total_seconds() >= _CLEANUP_INTERVAL:
        _maybe_cleanup()
        _last_cleanup = now


def get_session_id(user_id: str, session_id: Optional[str] = None) -> str:
    """
    Get or generate session ID.
    If no session_id provided, use user_id (single session per user).
    """
    return session_id or f"user_{user_id}"


def get_conversation(user_id: str, session_id: Optional[str] = None) -> list[dict]:
    """
    Get conversation history for a session.
    Returns list of {"role": "user"|"assistant", "content": "..."}
    """
    _maybe_cleanup()
    sid = get_session_id(user_id, session_id)
    
    if sid in _cache:
        _cache[sid]["last_access"] = datetime.now()
        return _cache[sid]["messages"].copy()
    
    return []


def add_message(user_id: str, role: str, content: str, session_id: Optional[str] = None):
    """
    Add a message to conversation history.
    Role should be "user" or "assistant".
    """
    _maybe_cleanup()
    sid = get_session_id(user_id, session_id)
    
    if sid not in _cache:
        _cache[sid] = {"messages": [], "last_access": datetime.now()}
    
    _cache[sid]["messages"].append({"role": role, "content": content})
    _cache[sid]["last_access"] = datetime.now()
    
    # Trim to max messages (keep most recent)
    if len(_cache[sid]["messages"]) > MAX_MESSAGES:
        _cache[sid]["messages"] = _cache[sid]["messages"][-MAX_MESSAGES:]
    
    logger.debug(f"ConversationCache: Added {role} message to {sid}, total={len(_cache[sid]['messages'])}")


def clear_conversation(user_id: str, session_id: Optional[str] = None):
    """Clear conversation history for a session."""
    sid = get_session_id(user_id, session_id)
    if sid in _cache:
        del _cache[sid]
        logger.info(f"ConversationCache: Cleared session {sid}")


def get_cache_stats() -> dict:
    """Get cache statistics for monitoring."""
    _maybe_cleanup()
    return {
        "active_sessions": len(_cache),
        "total_messages": sum(len(d["messages"]) for d in _cache.values())
    }
