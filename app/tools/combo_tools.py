import os
import httpx
from loguru import logger
from app.tools.auth_tools import ensure_authenticated, get_auth_headers

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def get_all_combos() -> dict:
    """Get all combos from the restaurant system."""
    logger.info("Tool: get_all_combos")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BE_BASE_URL}/api/combos")
        response.raise_for_status()
        return response.json()


async def get_combo_by_id(combo_id: str) -> dict:
    """Get a specific combo by ID."""
    logger.info(f"Tool: get_combo_by_id({combo_id})")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BE_BASE_URL}/api/combos/{combo_id}")
        response.raise_for_status()
        return response.json()


async def create_combo(name: str, base_price: float, items: list, description: str = None, image_urls: list = None) -> dict:
    """
    Create a new combo. Requires authentication.
    - name: combo name (required)
    - base_price: combo price (required)
    - items: list of items, each with {productId, quantity, displayOrder} (required)
    - description: combo description (optional)
    - image_urls: list of image URLs (optional)
    """
    logger.info(f"Tool: create_combo(name={name}, base_price={base_price})")
    
    # Ensure authenticated
    await ensure_authenticated()
    
    data = {
        "name": name,
        "basePrice": base_price,
        "items": items
    }
    if description:
        data["description"] = description
    if image_urls:
        data["imageUrls"] = image_urls

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BE_BASE_URL}/api/combos",
            json=data,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def update_combo(combo_id: str, name: str = None, base_price: float = None, items: list = None, description: str = None, image_urls: list = None) -> dict:
    """Update an existing combo. Requires authentication."""
    logger.info(f"Tool: update_combo({combo_id})")
    
    # Ensure authenticated
    await ensure_authenticated()
    
    data = {}
    if name:
        data["name"] = name
    if base_price is not None:
        data["basePrice"] = base_price
    if items:
        data["items"] = items
    if description:
        data["description"] = description
    if image_urls:
        data["imageUrls"] = image_urls

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.put(
            f"{BE_BASE_URL}/api/combos/{combo_id}",
            json=data,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def delete_combo(combo_id: str) -> dict:
    """Delete a combo. Requires authentication."""
    logger.info(f"Tool: delete_combo({combo_id})")
    
    # Ensure authenticated
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.delete(
            f"{BE_BASE_URL}/api/combos/{combo_id}",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return {"status": "deleted", "id": combo_id}


async def toggle_combo_status(combo_id: str) -> dict:
    """Toggle the status of a combo (active/inactive). Requires authentication."""
    logger.info(f"Tool: toggle_combo_status({combo_id})")
    
    # Ensure authenticated
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.put(
            f"{BE_BASE_URL}/api/combos/{combo_id}/status",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()
