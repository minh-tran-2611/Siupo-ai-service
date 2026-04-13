import os
import httpx
from loguru import logger
from app.tools.auth_tools import ensure_authenticated, get_auth_headers

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def get_public_vouchers() -> dict:
    """Get all public vouchers (no auth required)."""
    logger.info("Tool: get_public_vouchers")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BE_BASE_URL}/api/vouchers")
        response.raise_for_status()
        return response.json()


async def get_all_vouchers_admin(page: int = 0, size: int = 50, sort_by: str = "id", sort_dir: str = "desc") -> dict:
    """Get all vouchers with pagination (admin). Requires authentication."""
    logger.info(f"Tool: get_all_vouchers_admin(page={page}, size={size})")

    await ensure_authenticated()

    params = {"page": page, "size": size, "sortBy": sort_by, "sortDir": sort_dir}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/vouchers/admin",
            params=params,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_voucher_by_id(voucher_id: int) -> dict:
    """Get voucher detail by id (admin). Requires authentication."""
    logger.info(f"Tool: get_voucher_by_id({voucher_id})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BE_BASE_URL}/api/vouchers/admin/{voucher_id}",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_voucher_by_code(code: str) -> dict:
    """Get voucher detail by code. Requires authentication."""
    logger.info(f"Tool: get_voucher_by_code({code})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/vouchers/code/{code}",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def create_voucher(
    code: str,
    name: str,
    type: str,
    discount_value: float,
    start_date: str,
    end_date: str,
    description: str = None,
    min_order_value: float = None,
    max_discount_amount: float = None,
    usage_limit: int = None,
    usage_limit_per_user: int = None,
    is_public: bool = True,
) -> dict:
    """
    Create a new voucher. Requires authentication.
    - code: unique voucher code (required)
    - name: display name (required)
    - type: PERCENTAGE | FIXED_AMOUNT | FREE_SHIPPING (required)
    - discount_value: percentage (0-100) or fixed amount (required)
    - start_date: ISO 8601 (required)
    - end_date: ISO 8601 (required)
    - min_order_value: minimum order value to apply (optional)
    - max_discount_amount: cap for percentage type (optional)
    - usage_limit: total usage cap (optional)
    - usage_limit_per_user: per-user cap (optional)
    - is_public: visible to all users (default: True)
    """
    logger.info(f"Tool: create_voucher(code={code}, type={type}, discount_value={discount_value})")

    await ensure_authenticated()

    data = {
        "code": code,
        "name": name,
        "type": type,
        "discountValue": discount_value,
        "startDate": start_date,
        "endDate": end_date,
        "isPublic": is_public,
    }
    if description:
        data["description"] = description
    if min_order_value is not None:
        data["minOrderValue"] = min_order_value
    if max_discount_amount is not None:
        data["maxDiscountAmount"] = max_discount_amount
    if usage_limit is not None:
        data["usageLimit"] = usage_limit
    if usage_limit_per_user is not None:
        data["usageLimitPerUser"] = usage_limit_per_user

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BE_BASE_URL}/api/vouchers",
            json=data,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def update_voucher(
    voucher_id: int,
    code: str = None,
    name: str = None,
    type: str = None,
    discount_value: float = None,
    start_date: str = None,
    end_date: str = None,
    description: str = None,
    min_order_value: float = None,
    max_discount_amount: float = None,
    usage_limit: int = None,
    usage_limit_per_user: int = None,
    is_public: bool = None,
) -> dict:
    """Update an existing voucher. Requires authentication."""
    logger.info(f"Tool: update_voucher({voucher_id})")

    await ensure_authenticated()

    data = {}
    if code:
        data["code"] = code
    if name:
        data["name"] = name
    if type:
        data["type"] = type
    if discount_value is not None:
        data["discountValue"] = discount_value
    if start_date:
        data["startDate"] = start_date
    if end_date:
        data["endDate"] = end_date
    if description:
        data["description"] = description
    if min_order_value is not None:
        data["minOrderValue"] = min_order_value
    if max_discount_amount is not None:
        data["maxDiscountAmount"] = max_discount_amount
    if usage_limit is not None:
        data["usageLimit"] = usage_limit
    if usage_limit_per_user is not None:
        data["usageLimitPerUser"] = usage_limit_per_user
    if is_public is not None:
        data["isPublic"] = is_public

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.put(
            f"{BE_BASE_URL}/api/vouchers/{voucher_id}",
            json=data,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def delete_voucher(voucher_id: int) -> dict:
    """Delete a voucher. Requires authentication."""
    logger.info(f"Tool: delete_voucher({voucher_id})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.delete(
            f"{BE_BASE_URL}/api/vouchers/{voucher_id}",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return {"status": "deleted", "id": voucher_id}


async def toggle_voucher_status(voucher_id: int) -> dict:
    """Toggle voucher status ACTIVE <-> INACTIVE. Requires authentication."""
    logger.info(f"Tool: toggle_voucher_status({voucher_id})")

    await ensure_authenticated()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.patch(
            f"{BE_BASE_URL}/api/vouchers/{voucher_id}/toggle-status",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()
