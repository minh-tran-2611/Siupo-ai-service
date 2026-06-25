import os
import httpx
from loguru import logger
from app.tools.auth_tools import make_request

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

    params = {"page": page, "size": size, "sortBy": sort_by, "sortDir": sort_dir}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await make_request(client, "get", f"{BE_BASE_URL}/api/vouchers/admin", params=params)
        response.raise_for_status()
        return response.json()


async def get_voucher_by_id(voucher_id: int) -> dict:
    """Get voucher detail by id (admin). Requires authentication."""
    logger.info(f"Tool: get_voucher_by_id({voucher_id})")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await make_request(client, "post", f"{BE_BASE_URL}/api/vouchers/admin/{voucher_id}")
        response.raise_for_status()
        return response.json()


async def get_voucher_by_code(code: str) -> dict:
    """Get voucher detail by code. Requires authentication."""
    logger.info(f"Tool: get_voucher_by_code({code})")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await make_request(client, "get", f"{BE_BASE_URL}/api/vouchers/code/{code}")
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
        response = await make_request(client, "post", f"{BE_BASE_URL}/api/vouchers", json=data)
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
    """Update an existing voucher. Requires authentication.

    The BE update overwrites every field, so this tool first reads the current
    voucher and merges the provided arguments on top of it. Any field left as
    None keeps its existing value. Only pass the fields you want to change.
    """
    logger.info(f"Tool: update_voucher({voucher_id})")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Read the current voucher so unspecified fields keep their values
        current_resp = await make_request(client, "post", f"{BE_BASE_URL}/api/vouchers/admin/{voucher_id}")
        current_resp.raise_for_status()
        current = current_resp.json().get("data") or {}

        # Merge: provided value wins, otherwise fall back to the existing value
        data = {
            "code": code if code is not None else current.get("code"),
            "name": name if name is not None else current.get("name"),
            "description": description if description is not None else current.get("description"),
            "type": type if type is not None else current.get("type"),
            "discountValue": discount_value if discount_value is not None else current.get("discountValue"),
            "minOrderValue": min_order_value if min_order_value is not None else current.get("minOrderValue"),
            "maxDiscountAmount": max_discount_amount if max_discount_amount is not None else current.get("maxDiscountAmount"),
            "usageLimit": usage_limit if usage_limit is not None else current.get("usageLimit"),
            "usageLimitPerUser": usage_limit_per_user if usage_limit_per_user is not None else current.get("usageLimitPerUser"),
            "startDate": start_date if start_date is not None else current.get("startDate"),
            "endDate": end_date if end_date is not None else current.get("endDate"),
            "status": current.get("status"),
            "isPublic": is_public if is_public is not None else current.get("isPublic"),
        }

        response = await make_request(client, "put", f"{BE_BASE_URL}/api/vouchers/{voucher_id}", json=data)
        response.raise_for_status()
        return response.json()


async def delete_voucher(voucher_id: int) -> dict:
    """Delete a voucher. Requires authentication."""
    logger.info(f"Tool: delete_voucher({voucher_id})")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await make_request(client, "delete", f"{BE_BASE_URL}/api/vouchers/{voucher_id}")
        response.raise_for_status()
        return {"status": "deleted", "id": voucher_id}


async def toggle_voucher_status(voucher_id: int) -> dict:
    """Toggle voucher status ACTIVE <-> INACTIVE. Requires authentication."""
    logger.info(f"Tool: toggle_voucher_status({voucher_id})")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await make_request(client, "patch", f"{BE_BASE_URL}/api/vouchers/{voucher_id}/toggle-status")
        response.raise_for_status()
        return response.json()
