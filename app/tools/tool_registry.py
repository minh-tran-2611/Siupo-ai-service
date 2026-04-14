"""
Central Tool Registry — Maps tool names to functions, grouped by agent.

Each agent picks its own subset from this registry.
Tools can be shared across agents (e.g., READ tools).
"""
from app.tools.banner_tools import (
    get_all_banners, get_banner_by_id, create_banner, update_banner, delete_banner
)
from app.tools.category_tools import (
    get_categories, create_category, update_category, delete_category
)
from app.tools.combo_tools import (
    get_all_combos, get_combo_by_id, create_combo, update_combo, delete_combo, toggle_combo_status
)
from app.tools.notification_tools import (
    get_all_notifications_admin, create_notification, get_my_notifications
)
from app.tools.product_tools import (
    get_search_products, create_product, update_product, delete_product, toggle_product_status
)
from app.tools.user_tools import get_all_customers, update_customer_status
from app.tools.auth_tools import login
from app.tools.search_tools import search_internet
from app.tools.analytics_tools import (
    get_analytics_summary, get_revenue_analytics, get_order_analytics,
    get_product_analytics, get_customer_analytics,
    get_booking_analytics, get_analytics_insights
)
from app.tools.voucher_tools import (
    get_public_vouchers, get_all_vouchers_admin, get_voucher_by_id, get_voucher_by_code,
    create_voucher, update_voucher, delete_voucher, toggle_voucher_status
)
from app.tools.order_tools import (
    get_all_orders_admin, get_order_detail_admin, update_order_status,
    delete_order, get_order_reviews
)
from app.tools.tag_tools import (
    get_all_tags, get_tag_by_id, create_tag, update_tag, delete_tag
)
from app.tools.review_tools import (
    get_reviews_by_order, get_review_by_order_item
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Complete tool pool — ALL available tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALL_TOOL_FUNCTIONS = {
    # Banner
    "get_all_banners": get_all_banners,
    "get_banner_by_id": get_banner_by_id,
    "create_banner": create_banner,
    "update_banner": update_banner,
    "delete_banner": delete_banner,
    # Category
    "get_categories": get_categories,
    "create_category": create_category,
    "update_category": update_category,
    "delete_category": delete_category,
    # Combo
    "get_all_combos": get_all_combos,
    "get_combo_by_id": get_combo_by_id,
    "create_combo": create_combo,
    "update_combo": update_combo,
    "delete_combo": delete_combo,
    "toggle_combo_status": toggle_combo_status,
    # Notification
    "get_all_notifications_admin": get_all_notifications_admin,
    "create_notification": create_notification,
    "get_my_notifications": get_my_notifications,
    # Product
    "get_search_products": get_search_products,
    "create_product": create_product,
    "update_product": update_product,
    "delete_product": delete_product,
    "toggle_product_status": toggle_product_status,
    # User
    "get_all_customers": get_all_customers,
    "update_customer_status": update_customer_status,
    # Auth
    "login": login,
    # Search
    "search_internet": search_internet,
    # Analytics
    "get_analytics_summary": get_analytics_summary,
    "get_revenue_analytics": get_revenue_analytics,
    "get_order_analytics": get_order_analytics,
    "get_product_analytics": get_product_analytics,
    "get_customer_analytics": get_customer_analytics,
    "get_booking_analytics": get_booking_analytics,
    "get_analytics_insights": get_analytics_insights,
    # Voucher
    "get_public_vouchers": get_public_vouchers,
    "get_all_vouchers_admin": get_all_vouchers_admin,
    "get_voucher_by_id": get_voucher_by_id,
    "get_voucher_by_code": get_voucher_by_code,
    "create_voucher": create_voucher,
    "update_voucher": update_voucher,
    "delete_voucher": delete_voucher,
    "toggle_voucher_status": toggle_voucher_status,
    # Order
    "get_all_orders_admin": get_all_orders_admin,
    "get_order_detail_admin": get_order_detail_admin,
    "update_order_status": update_order_status,
    "delete_order": delete_order,
    "get_order_reviews": get_order_reviews,
    # Tag
    "get_all_tags": get_all_tags,
    "get_tag_by_id": get_tag_by_id,
    "create_tag": create_tag,
    "update_tag": update_tag,
    "delete_tag": delete_tag,
    # Review
    "get_reviews_by_order": get_reviews_by_order,
    "get_review_by_order_item": get_review_by_order_item,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Per-agent tool name lists
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MANAGEMENT_TOOL_NAMES = [
    # Banner CRUD
    "get_all_banners", "get_banner_by_id", "create_banner", "update_banner", "delete_banner",
    # Category CRUD
    "get_categories", "create_category", "update_category", "delete_category",
    # Combo CRUD
    "get_all_combos", "get_combo_by_id", "create_combo", "update_combo", "delete_combo", "toggle_combo_status",
    # Notification
    "get_all_notifications_admin", "create_notification", "get_my_notifications",
    # Product CRUD
    "get_search_products", "create_product", "update_product", "delete_product", "toggle_product_status",
    # User
    "get_all_customers", "update_customer_status",
    # Voucher CRUD
    "get_public_vouchers", "get_all_vouchers_admin", "get_voucher_by_id", "get_voucher_by_code",
    "create_voucher", "update_voucher", "delete_voucher", "toggle_voucher_status",
    # Order management
    "get_all_orders_admin", "get_order_detail_admin", "update_order_status",
    "delete_order", "get_order_reviews",
    # Tag CRUD
    "get_all_tags", "get_tag_by_id", "create_tag", "update_tag", "delete_tag",
    # Review (read-only)
    "get_reviews_by_order", "get_review_by_order_item",
    # Auth
    "login",
    # Utility
    "search_internet",
]

ANALYTICS_TOOL_NAMES = [
    # Analytics endpoints
    "get_analytics_summary", "get_revenue_analytics", "get_order_analytics",
    "get_product_analytics", "get_customer_analytics",
    "get_booking_analytics", "get_analytics_insights",
    # Shared READ tools (for supplementary data)
    "get_search_products", "get_all_combos", "get_categories", "get_all_customers",
    "get_all_tags",
    # Order data (for deeper order/revenue analysis)
    "get_all_orders_admin", "get_order_detail_admin",
    # Voucher data (for promotion effectiveness analysis)
    "get_all_vouchers_admin", "get_voucher_by_id",
    # Review data (for sentiment / quality analysis)
    "get_order_reviews", "get_reviews_by_order", "get_review_by_order_item",
    # Utility
    "search_internet",
]

# Orchestrator tools are meta-tools (call_management_agent, call_analytics_agent)
# defined directly in orchestrator.py, not here.
ORCHESTRATOR_TOOL_NAMES = [
    "search_internet",
    "search_documents",
]


def get_tool_functions(tool_names: list[str]) -> dict:
    """Get a subset of tool functions by name."""
    return {name: ALL_TOOL_FUNCTIONS[name] for name in tool_names if name in ALL_TOOL_FUNCTIONS}
