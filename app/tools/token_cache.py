"""
Token cache for storing access tokens.
Auto-login with admin credentials when token is missing or expired.
"""
import os
from datetime import datetime, timedelta
from loguru import logger

# Admin credentials from environment or defaults
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@siupo.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@123")

# Token storage
_token_cache = {
    "access_token": None,
    "expires_at": None
}

# Token validity duration (assume 1 hour, refresh 5 mins before expiry)
TOKEN_VALIDITY_MINUTES = 55


def get_token() -> str | None:
    """Get current access token if valid."""
    if _token_cache["access_token"] and _token_cache["expires_at"]:
        if datetime.now() < _token_cache["expires_at"]:
            return _token_cache["access_token"]
    return None


def set_token(access_token: str):
    """Store access token with expiry time."""
    _token_cache["access_token"] = access_token
    _token_cache["expires_at"] = datetime.now() + timedelta(minutes=TOKEN_VALIDITY_MINUTES)
    logger.info(f"TokenCache: Token stored, expires at {_token_cache['expires_at']}")


def clear_token():
    """Clear stored token."""
    _token_cache["access_token"] = None
    _token_cache["expires_at"] = None
    logger.info("TokenCache: Token cleared")


def is_token_valid() -> bool:
    """Check if current token is still valid."""
    return get_token() is not None
