"""
Review tools — read-only access to customer reviews.

NOTE: The BE currently exposes reviews per order/order-item only
(no admin-wide list endpoint). For full sentiment analysis, the agent
must first fetch orders via get_all_orders_admin, then iterate through
order ids to retrieve their reviews.
"""
import os
import httpx
from loguru import logger
from app.tools.auth_tools import ensure_authenticated, get_auth_headers

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def get_reviews_by_order(order_id: int) -> dict:
    """Get all reviews for a given order. Requires authentication."""
    logger.info(f"Tool: get_reviews_by_order({order_id})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/reviews/orders/{order_id}",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_review_by_order_item(order_item_id: int) -> dict:
    """Get the review of a specific order item. Requires authentication."""
    logger.info(f"Tool: get_review_by_order_item({order_item_id})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/reviews/order-items/{order_item_id}",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()
