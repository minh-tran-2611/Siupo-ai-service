import os
import httpx
from loguru import logger
from app.tools.auth_tools import ensure_authenticated, get_auth_headers

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def get_all_orders_admin(status: str = None, page: int = 0, size: int = 20) -> dict:
    """
    Get all orders with pagination (admin).
    - status: filter by EOrderStatus (WAITING_FOR_PAYMENT, PENDING, CONFIRMED, SHIPPING, DELIVERED, COMPLETED, CANCELED)
    - page: page index (default 0)
    - size: page size (default 20)
    Requires authentication.
    """
    logger.info(f"Tool: get_all_orders_admin(status={status}, page={page}, size={size})")

    await ensure_authenticated()

    params = {"page": page, "size": size}
    if status:
        params["status"] = status

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/orders/admin",
            params=params,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_order_detail_admin(order_id: int) -> dict:
    """Get full order details by id (admin). Requires authentication."""
    logger.info(f"Tool: get_order_detail_admin({order_id})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/orders/admin/{order_id}",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def update_order_status(order_id: int, status: str) -> dict:
    """
    Update order status. Requires authentication.
    - status: WAITING_FOR_PAYMENT | PENDING | CONFIRMED | SHIPPING | DELIVERED | COMPLETED | CANCELED
    """
    logger.info(f"Tool: update_order_status({order_id}, status={status})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.patch(
            f"{BE_BASE_URL}/api/orders/admin/{order_id}/status",
            params={"status": status},
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def delete_order(order_id: int) -> dict:
    """Delete an order (admin). Requires authentication."""
    logger.info(f"Tool: delete_order({order_id})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.delete(
            f"{BE_BASE_URL}/api/orders/admin/{order_id}",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return {"status": "deleted", "id": order_id}


async def get_order_reviews(order_id: int) -> dict:
    """Get all reviews for a specific order. Requires authentication."""
    logger.info(f"Tool: get_order_reviews({order_id})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/orders/{order_id}/reviews",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()
