import os
import httpx
from loguru import logger
from app.tools.auth_tools import ensure_authenticated, get_auth_headers

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def get_all_banners() -> dict:
    """Get all banners from the restaurant system."""
    logger.info("Tool: get_all_banners")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BE_BASE_URL}/api/banners")
        response.raise_for_status()
        return response.json()


async def get_banner_by_id(banner_id: str) -> dict:
    """Get a specific banner by ID."""
    logger.info(f"Tool: get_banner_by_id({banner_id})")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BE_BASE_URL}/api/banners/{banner_id}")
        response.raise_for_status()
        return response.json()


async def create_banner(url: str, position: str) -> dict:
    """Create a new banner. Requires authentication."""
    logger.info(f"Tool: create_banner(url={url}, position={position})")
    
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BE_BASE_URL}/api/banners",
            json={"url": url, "position": position},
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def update_banner(banner_id: str, url: str, position: str) -> dict:
    """Update an existing banner. Requires authentication."""
    logger.info(f"Tool: update_banner({banner_id}, url={url}, position={position})")
    
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.put(
            f"{BE_BASE_URL}/api/banners/{banner_id}",
            json={"url": url, "position": position},
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def delete_banner(banner_id: str) -> dict:
    """Delete a banner. Requires authentication."""
    logger.info(f"Tool: delete_banner({banner_id})")
    
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.delete(
            f"{BE_BASE_URL}/api/banners/{banner_id}",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return {"status": "deleted", "id": banner_id}
