import os
import httpx
from loguru import logger
from app.tools.auth_tools import ensure_authenticated, get_auth_headers

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def get_all_tags() -> dict:
    """Get all tags from the restaurant system."""
    logger.info("Tool: get_all_tags")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BE_BASE_URL}/api/tags")
        response.raise_for_status()
        return response.json()


async def get_tag_by_id(tag_id: int) -> dict:
    """Get a specific tag by ID."""
    logger.info(f"Tool: get_tag_by_id({tag_id})")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BE_BASE_URL}/api/tags/{tag_id}")
        response.raise_for_status()
        return response.json()


async def create_tag(name: str) -> dict:
    """Create a new tag. Requires authentication."""
    logger.info(f"Tool: create_tag(name={name})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BE_BASE_URL}/api/tags",
            json={"name": name},
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def update_tag(tag_id: int, name: str) -> dict:
    """Update an existing tag. Requires authentication."""
    logger.info(f"Tool: update_tag({tag_id}, name={name})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.put(
            f"{BE_BASE_URL}/api/tags/{tag_id}",
            json={"name": name},
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def delete_tag(tag_id: int) -> dict:
    """Delete a tag. Requires authentication."""
    logger.info(f"Tool: delete_tag({tag_id})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.delete(
            f"{BE_BASE_URL}/api/tags/{tag_id}",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return {"status": "deleted", "id": tag_id}
