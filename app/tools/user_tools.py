import os
import httpx
from loguru import logger
from app.tools.auth_tools import ensure_authenticated, get_auth_headers

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def get_all_customers() -> dict:
    """Get all customers/users from the system (admin only). Requires authentication."""
    logger.info("Tool: get_all_customers")
    
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/users/customers",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def update_customer_status(user_id: str, status: str) -> dict:
    """
    Update a customer's status. Requires authentication.
    Status must be one of: ACTIVE, INACTIVE, SUSPENDED
    """
    logger.info(f"Tool: update_customer_status({user_id}, {status})")
    
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.put(
            f"{BE_BASE_URL}/api/users/customers/{user_id}/status",
            json={"status": status},
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()
