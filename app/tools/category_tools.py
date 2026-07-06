import os
import httpx
from loguru import logger
from app.tools.auth_tools import make_request

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def get_categories() -> dict:
    """Get all categories from the restaurant system."""
    logger.info("Tool: get_categories")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BE_BASE_URL}/api/categories")
        response.raise_for_status()
        return response.json()


async def create_category(name: str, image_url: str = None) -> dict:
    """Create a new category. Requires authentication."""
    logger.info(f"Tool: create_category(name={name}, image_url={image_url})")

    data = {"name": name}
    if image_url:
        data["imageUrl"] = image_url

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await make_request(client, "post", f"{BE_BASE_URL}/api/categories", json=data)
        response.raise_for_status()
        return response.json()


async def update_category(category_id: str, name: str = None, image_url: str = None) -> dict:
    """Update an existing category. Requires authentication."""
    logger.info(f"Tool: update_category({category_id}, name={name}, image_url={image_url})")

    data = {}
    if name:
        data["name"] = name
    if image_url:
        data["imageUrl"] = image_url

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await make_request(client, "put", f"{BE_BASE_URL}/api/categories/{category_id}", json=data)
        response.raise_for_status()
        return response.json()


async def delete_category(category_id: str) -> dict:
    """Delete a category. Requires authentication."""
    logger.info(f"Tool: delete_category({category_id})")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await make_request(client, "delete", f"{BE_BASE_URL}/api/categories/{category_id}")
        response.raise_for_status()
        return {"status": "deleted", "id": category_id}
