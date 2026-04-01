import os
import httpx
from loguru import logger
from app.tools.token_cache import set_token, get_token, clear_token, ADMIN_EMAIL, ADMIN_PASSWORD

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def login(email: str = None, password: str = None) -> dict:
    """
    Login to the system and store access token.
    If no credentials provided, uses default admin credentials.
    Returns login response with access token.
    """
    # Use provided credentials or default admin
    email = email or ADMIN_EMAIL
    password = password or ADMIN_PASSWORD
    
    logger.info(f"Tool: login({email})")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BE_BASE_URL}/api/auth/login",
            json={"email": email, "password": password}
        )
        response.raise_for_status()
        data = response.json()
        
        # Store token in cache
        if data.get("success") and data.get("data", {}).get("accessToken"):
            access_token = data["data"]["accessToken"]
            set_token(access_token)
            logger.info("Tool: login successful, token cached")
        
        return data


async def ensure_authenticated() -> str:
    """
    Ensure we have a valid access token.
    If not, auto-login with admin credentials.
    Returns the access token.
    """
    token = get_token()
    if token:
        return token
    
    # Auto-login with admin credentials
    logger.info("Token missing or expired, auto-login with admin...")
    result = await login()
    
    token = get_token()
    if not token:
        raise Exception("Failed to authenticate: no token received")
    
    return token


def get_auth_headers() -> dict:
    """Get authorization headers with current token."""
    token = get_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def logout() -> dict:
    """Logout and clear token cache."""
    logger.info("Tool: logout")
    clear_token()
    return {"status": "logged_out", "message": "Token cleared"}
