import os
import httpx
from loguru import logger
from app.tools.auth_tools import ensure_authenticated, get_auth_headers

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def get_search_products(name: str = None, category_ids: list = None, min_price: float = None, max_price: float = None) -> dict:
    """Search for products by name, category, or price range."""
    logger.info(f"Tool: get_search_products(name={name}, category_ids={category_ids}, min_price={min_price}, max_price={max_price})")
    params = {}
    if name:
        params["name"] = name
    if category_ids:
        params["categoryIds"] = category_ids
    if min_price is not None:
        params["minPrice"] = min_price
    if max_price is not None:
        params["maxPrice"] = max_price

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BE_BASE_URL}/api/products/search", params=params)
        response.raise_for_status()
        return response.json()


async def create_product(name: str, price: float, category_id: int, description: str = None, image_urls: list = None, tags: list = None) -> dict:
    """
    Create a new product. Requires authentication.
    - name: product name (required)
    - price: product price (required)
    - category_id: category ID (required)
    - description: product description (optional)
    - image_urls: list of image URLs (optional)
    - tags: list of tag names (optional)
    """
    logger.info(f"Tool: create_product(name={name}, price={price}, category_id={category_id})")
    
    await ensure_authenticated()
    
    data = {
        "name": name,
        "price": price,
        "categoryId": category_id
    }
    if description:
        data["description"] = description
    if image_urls:
        data["imageUrls"] = image_urls
    if tags:
        data["tags"] = tags

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BE_BASE_URL}/api/products",
            json=data,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def update_product(product_id: str, name: str = None, price: float = None, category_id: int = None, description: str = None, image_urls: list = None, tags: list = None) -> dict:
    """Update an existing product. Requires authentication."""
    logger.info(f"Tool: update_product({product_id})")
    
    await ensure_authenticated()
    
    data = {}
    if name:
        data["name"] = name
    if price is not None:
        data["price"] = price
    if category_id is not None:
        data["categoryId"] = category_id
    if description:
        data["description"] = description
    if image_urls:
        data["imageUrls"] = image_urls
    if tags:
        data["tags"] = tags

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.put(
            f"{BE_BASE_URL}/api/products/{product_id}",
            json=data,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def delete_product(product_id: str) -> dict:
    """Delete a product. Requires authentication."""
    logger.info(f"Tool: delete_product({product_id})")
    
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.delete(
            f"{BE_BASE_URL}/api/products/{product_id}",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return {"status": "deleted", "id": product_id}


async def toggle_product_status(product_id: str) -> dict:
    """Toggle the status of a product (active/inactive). Requires authentication."""
    logger.info(f"Tool: toggle_product_status({product_id})")
    
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.put(
            f"{BE_BASE_URL}/api/products/{product_id}/status",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()
