import os
import json
import asyncio
import random
from google import genai
from google.genai import types
from loguru import logger

from app.agents.memory_orchestrator import ingest_memory
from app.memory.sqlite_memory import get_memories_by_user, get_consolidated_memories_by_user
from app.memory.conversation_cache import get_conversation, add_message, clear_conversation
from app.rag.retriever import retrieve_relevant_chunks
from app.utils.prompt_builder import build_prompt, get_system_prompt


def format_memory_context(memories: list[dict], consolidated: list[dict]) -> str:
    """Format memories into simple context string (no LLM needed)."""
    if not memories and not consolidated:
        return ""

    parts = []

    # Consolidated memories (important summaries)
    if consolidated:
        parts.append("Tóm tắt về người dùng:")
        for m in consolidated[:5]:  # Limit to 5
            parts.append(f"- {m['summary']}")

    # Recent memories
    if memories:
        parts.append("\nHội thoại gần đây:")
        for m in memories[:10]:  # Limit to 10 most recent
            parts.append(f"- {m['summary']}")

    return "\n".join(parts)


async def call_llm_with_retry(generate_coro_fn, max_retries: int = 3, base_delay: float = 1.0):
    """
    Call LLM with exponential backoff retry for rate limiting (429 errors).
    Now properly async - awaits the coroutine.
    """
    for attempt in range(max_retries):
        try:
            return await generate_coro_fn()  # Await the coroutine properly
        except Exception as e:
            error_str = str(e)
            # Check if it's a rate limit error
            if ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str) and attempt < max_retries - 1:
                # Exponential backoff with jitter
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Rate limited, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(delay)
            else:
                # Re-raise if not rate limit or max retries reached
                raise

# Import all tools
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
    get_product_analytics, get_top_selling_products, get_customer_analytics,
    get_booking_analytics, get_analytics_insights
)

# RAG as a tool function
async def search_documents(query: str) -> dict:
    """Search internal documents (reports, guides, policies)."""
    chunks = await retrieve_relevant_chunks(query, top_k=5)
    if not chunks:
        return {"results": [], "message": "Không tìm thấy tài liệu liên quan."}

    results = [
        {"title": chunk["title"], "content": chunk["content"]}
        for chunk in chunks
    ]
    return {"results": results}

PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
REGION = os.getenv("GOOGLE_REGION", "us-central1")

client = genai.Client(vertexai=True, project=PROJECT_ID, location=REGION)

# Define tool functions for Gemini
TOOL_FUNCTIONS = {
    "get_all_banners": get_all_banners,
    "get_banner_by_id": get_banner_by_id,
    "create_banner": create_banner,
    "update_banner": update_banner,
    "delete_banner": delete_banner,
    "get_categories": get_categories,
    "create_category": create_category,
    "update_category": update_category,
    "delete_category": delete_category,
    "get_all_combos": get_all_combos,
    "get_combo_by_id": get_combo_by_id,
    "create_combo": create_combo,
    "update_combo": update_combo,
    "delete_combo": delete_combo,
    "toggle_combo_status": toggle_combo_status,
    "get_all_notifications_admin": get_all_notifications_admin,
    "create_notification": create_notification,
    "get_my_notifications": get_my_notifications,
    "get_search_products": get_search_products,
    "create_product": create_product,
    "update_product": update_product,
    "delete_product": delete_product,
    "toggle_product_status": toggle_product_status,
    "get_all_customers": get_all_customers,
    "update_customer_status": update_customer_status,
    "login": login,
    "search_internet": search_internet,
    "search_documents": search_documents,
    "get_analytics_summary": get_analytics_summary,
    "get_revenue_analytics": get_revenue_analytics,
    "get_order_analytics": get_order_analytics,
    "get_product_analytics": get_product_analytics,
    "get_top_selling_products": get_top_selling_products,
    "get_customer_analytics": get_customer_analytics,
    "get_booking_analytics": get_booking_analytics,
    "get_analytics_insights": get_analytics_insights,
}

# Define tool declarations for Gemini
TOOL_DECLARATIONS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="get_all_banners",
            description="""Retrieve all banners from the restaurant system.

        USE THIS TOOL WHEN:
        - User asks to list or view all banners.
        - Need to verify which positions are occupied before creating a new one.
        - Need to find a banner id from a position name.

        DEFAULT POSITIONS:
        Home1, Home2, Menu1, Menu2, Menu3, Menu4,
        AboutUs1, AboutUs2, AboutUs3, AboutUs4, AboutUs5, PlaceTable1

        RESPONSE CONTAINS: id, url, position, createdAt, updatedAt

        RULES:
        - Always call this tool before creating or deleting a banner.
        - Do not call if banner data is not needed for the current task.""",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="get_banner_by_id",
            description="""Retrieve a specific banner by its ID.

        USE THIS TOOL WHEN:
        - User asks for details about a specific banner by id.
        - Need to verify a banner exists before updating or deleting it.

        RULES:
        - If user provides a position or description instead of an id,
          call get_all_banners first to resolve the correct id.
        - Never guess the id.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"banner_id": types.Schema(type=types.Type.STRING, description="Banner ID")},
                required=["banner_id"]
            )
        ),
        types.FunctionDeclaration(
            name="create_banner",
            description="""Create a new banner in the restaurant system.

        AUTONOMOUS RULES — follow in order:
        1. Call get_all_banners first to check which positions are already occupied.
        2. If url is missing → use search_internet to find a relevant image.
           Query format: "{position} restaurant banner image"
           Extract the first valid image URL and proceed immediately.
        3. If position is missing → select the first available unoccupied position automatically.
        4. Only ask the user if search_internet fails AND no fallback url is available,
           OR if all positions are occupied.
        5. Never guess the url. Never create a banner on an already occupied position.
        6. If both url and position are resolved → call this tool immediately without asking.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "url": types.Schema(type=types.Type.STRING, description="Image URL for the banner"),
                    "position": types.Schema(type=types.Type.STRING, description="Banner position (e.g., Home1, Menu1)")
                },
                required=["url", "position"]
            )
        ),
        types.FunctionDeclaration(
            name="update_banner",
            description="""Update an existing banner by its ID.

        AUTONOMOUS RULES:
        1. If id is missing → call get_all_banners to resolve it from position or description.
        2. If new url is missing → use search_internet to find a relevant image automatically.
        3. Ensure at least one field (url or position) is provided before calling this tool.
        4. Never ask the user for the id if it can be resolved via get_all_banners.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "banner_id": types.Schema(type=types.Type.STRING, description="Banner ID"),
                    "url": types.Schema(type=types.Type.STRING, description="New image URL for the banner"),
                    "position": types.Schema(type=types.Type.STRING, description="New banner position")
                },
                required=["banner_id", "url", "position"]
            )
        ),
        types.FunctionDeclaration(
            name="delete_banner",
            description="""Delete a banner from the restaurant system.

        AUTONOMOUS RULES:
        1. If user provides a position instead of an id →
           call get_all_banners first → match the position → extract the id → proceed.
        2. Never ask the user for the id if it can be resolved automatically.
        3. Never guess the id.

        BULK DELETE:
        - If user requests to delete multiple or all banners →
          call get_all_banners first → iterate through each id →
          call delete_banner once per id sequentially.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"banner_id": types.Schema(type=types.Type.STRING, description="Banner ID")},
                required=["banner_id"]
            )
        ),
        types.FunctionDeclaration(
            name="get_categories",
            description="""Retrieve all categories from the restaurant system.

        USE THIS TOOL WHEN:
        - User asks to list or view categories.
        - Need to check for duplicate names before creating a new category.
        - Need to resolve a category id from a name before updating or deleting.

        RULES:
        - Always call this tool before creating, updating, or deleting a category.""",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="create_category",
            description="""Create a new category in the restaurant system.

        AUTONOMOUS RULES — follow in order:
        1. Call get_categories first to check for duplicate names.
           If same name exists → report it and do not create a duplicate.
        2. If imageUrl is missing → use search_internet to find a relevant image.
           Query format: "{category name} restaurant food category image"
           Extract the first valid image URL and proceed.
        3. Only ask the user if name is missing — this is the only acceptable case.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Category name"),
                    "image_url": types.Schema(type=types.Type.STRING, description="Category image URL (optional)")
                },
                required=["name"]
            )
        ),
        types.FunctionDeclaration(
            name="update_category",
            description="""Update an existing category by its ID.

        AUTONOMOUS RULES:
        1. If user provides a name but not an id →
           call get_categories first → resolve the id → proceed immediately.
        2. Ensure at least one field (name or imageUrl) is provided for the update.
        3. If imageUrl is missing and user wants to update image →
           use search_internet to find a relevant image automatically.
        4. If no update fields are provided → ask the user what they want to change.
        5. Do not call this tool if the category does not exist.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "category_id": types.Schema(type=types.Type.STRING, description="Category ID"),
                    "name": types.Schema(type=types.Type.STRING, description="New category name"),
                    "image_url": types.Schema(type=types.Type.STRING, description="New category image URL")
                },
                required=["category_id"]
            )
        ),
        types.FunctionDeclaration(
            name="delete_category",
            description="""Delete a category from the restaurant system.

        AUTONOMOUS RULES:
        1. If user provides a name instead of an id →
           call get_categories first → match the name → extract the id → proceed.
        2. Never ask the user for the id if it can be resolved automatically.
        3. Never guess the id.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"category_id": types.Schema(type=types.Type.STRING, description="Category ID")},
                required=["category_id"]
            )
        ),
        types.FunctionDeclaration(
            name="get_all_combos",
            description="""Retrieve all combos from the restaurant system.

        USE THIS TOOL WHEN:
        - User asks to list or view all combos.
        - Need to verify combo exists before updating or deleting.
        - Need to resolve a combo id from a name or description.

        RESPONSE CONTAINS: id, name, description, basePrice, originalPrice,
        imageUrls, items, status, createdAt, updatedAt

        RULES:
        - Always call this tool before updating or deleting a combo if id is unknown.""",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="get_combo_by_id",
            description="""Retrieve a specific combo by its ID.

        USE THIS TOOL WHEN:
        - User asks for details about a specific combo by id.
        - Need to verify combo details before updating.

        RULES:
        - If user provides a name instead of id,
          call get_all_combos first to resolve the correct id.
        - Never guess the id.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"combo_id": types.Schema(type=types.Type.STRING, description="Combo ID")},
                required=["combo_id"]
            )
        ),
        types.FunctionDeclaration(
            name="create_combo",
            description="""Create a new combo in the restaurant system.

        PARAMETERS:
        - name (string, required): combo name.
        - base_price (number, required): combo price, must be >= 0.
        - items (array, required): list of {productId, quantity, displayOrder}.
          At least 1 item required.
        - description (string, optional): combo description.
        - image_urls (array, optional): list of image URLs.

        AUTONOMOUS RULES:
        1. Ensure name, base_price, and items are provided.
        2. If productId in items is unknown → call get_search_products to resolve it.
        3. If image_urls is missing → use search_internet to find relevant images.
           Query format: "{combo name} restaurant food combo image"
        4. Only ask user if name, base_price, or items cannot be resolved automatically.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Combo name"),
                    "base_price": types.Schema(type=types.Type.NUMBER, description="Combo base price, must be >= 0"),
                    "items": types.Schema(type=types.Type.ARRAY,
                                          description="List of combo items: [{productId, quantity, displayOrder}]"),
                    "description": types.Schema(type=types.Type.STRING, description="Combo description (optional)"),
                    "image_urls": types.Schema(type=types.Type.ARRAY, description="List of image URLs (optional)")
                },
                required=["name", "base_price", "items"]
            )
        ),
        types.FunctionDeclaration(
            name="update_combo",
            description="""Update an existing combo by its ID.

        AUTONOMOUS RULES:
        1. If id is missing → call get_all_combos to resolve it from name or description.
        2. Ensure at least one field is provided for the update.
        3. If productId in items is unknown → call get_search_products to resolve it.
        4. Never ask user for id if it can be resolved automatically.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "combo_id": types.Schema(type=types.Type.STRING, description="Combo ID"),
                    "name": types.Schema(type=types.Type.STRING, description="New combo name"),
                    "base_price": types.Schema(type=types.Type.NUMBER, description="New combo base price"),
                    "items": types.Schema(type=types.Type.ARRAY, description="New list of combo items"),
                    "description": types.Schema(type=types.Type.STRING, description="New description"),
                    "image_urls": types.Schema(type=types.Type.ARRAY, description="New image URLs")
                },
                required=["combo_id"]
            )
        ),
        types.FunctionDeclaration(
            name="delete_combo",
            description="""Delete a combo from the restaurant system.

        AUTONOMOUS RULES:
        1. If user provides a name instead of id →
           call get_all_combos first → match the name → extract the id → proceed.
        2. Never ask user for id if it can be resolved automatically.
        3. Never guess the id.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"combo_id": types.Schema(type=types.Type.STRING, description="Combo ID")},
                required=["combo_id"]
            )
        ),
        types.FunctionDeclaration(
            name="toggle_combo_status",
            description="""Toggle combo status between AVAILABLE and UNAVAILABLE.

        AUTONOMOUS RULES:
        1. If id is missing → call get_all_combos to resolve it from name.
        2. Never guess the id.

        STATUS REFERENCE:
        - AVAILABLE   → visible to customers.
        - UNAVAILABLE → hidden, not deleted.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"combo_id": types.Schema(type=types.Type.STRING, description="Combo ID")},
                required=["combo_id"]
            )
        ),
        types.FunctionDeclaration(
            name="get_all_notifications_admin",
            description="""Retrieve all notifications (admin view).

        USE THIS TOOL WHEN:
        - Admin asks to list or view all notifications.
        - Need to verify notification exists before deleting.

        RESPONSE CONTAINS: id, title, content, userId, sendToAll, createdAt""",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="create_notification",
            description="""Create and send a notification to a specific user or all users.

        PARAMETERS:
        - title (string, required): notification title, max 255 chars.
        - content (string, required): notification content, max 2000 chars.
        - user_id (integer, optional): specific user ID to send to.
        - send_to_all (boolean, optional): if true, send to all users. Default: false.

        RULES:
        - If user_id is null and send_to_all is false → ask whether to send to a specific user or all users.
        - If user_id is provided → send only to that user.
        - If send_to_all is true → send to all users, ignore user_id.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title": types.Schema(type=types.Type.STRING, description="Notification title"),
                    "content": types.Schema(type=types.Type.STRING, description="Notification content"),
                    "user_id": types.Schema(type=types.Type.INTEGER, description="Specific user ID (optional)"),
                    "send_to_all": types.Schema(type=types.Type.BOOLEAN,
                                                description="Send to all users (default: false)")
                },
                required=["title", "content"]
            )
        ),
        types.FunctionDeclaration(
            name="get_my_notifications",
            description="Get notifications for current user",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="get_search_products",
            description="""Search and filter products in the restaurant system.

        USE THIS TOOL WHEN:
        - User asks to search or filter products by name, category, or price range.
        - Need to resolve a product id from a name before updating or deleting.
        - Need to find productId for combo items.

        PARAMETERS (all optional):
        - name: product name to search.
        - category_ids: list of category IDs to filter.
        - min_price / max_price: price range filter. min must be <= max.

        RULES:
        - Call get_categories first if user provides category name instead of id.
        - Do not pass empty array for category_ids — omit it entirely if not filtering by category.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Product name to search"),
                    "category_ids": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.INTEGER),
                                                 description="List of category IDs to filter"),
                    "min_price": types.Schema(type=types.Type.NUMBER, description="Minimum price"),
                    "max_price": types.Schema(type=types.Type.NUMBER, description="Maximum price")
                }
            )
        ),
        types.FunctionDeclaration(
            name="create_product",
            description="""Create a new product in the restaurant system.

        PARAMETERS:
        - name (string, required): 2-100 chars.
        - price (number, required): must be > 0.
        - category_id (integer, required): category ID.
        - description (string, optional): max 1000 chars.
        - image_urls (array, optional): list of image URLs.
        - tags (array, optional): list of tag names.

        AUTONOMOUS RULES:
        1. If category_id is unknown → call get_categories to resolve it from name.
        2. If image_urls is missing → use search_internet to find relevant images.
           Query format: "{product name} restaurant food image"
        3. Only ask user if name, price, or category cannot be resolved.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Product name (2-100 chars)"),
                    "price": types.Schema(type=types.Type.NUMBER, description="Product price, must be > 0"),
                    "category_id": types.Schema(type=types.Type.INTEGER, description="Category ID"),
                    "description": types.Schema(type=types.Type.STRING,
                                                description="Product description, max 1000 chars (optional)"),
                    "image_urls": types.Schema(type=types.Type.ARRAY, description="List of image URLs (optional)"),
                    "tags": types.Schema(type=types.Type.ARRAY, description="List of tag names (optional)")
                },
                required=["name", "price", "category_id"]
            )
        ),
        types.FunctionDeclaration(
            name="update_product",
            description="""Update an existing product by its ID.

        AUTONOMOUS RULES:
        1. If id is missing → call get_search_products to resolve it from name.
        2. If category_id is unknown → call get_categories to resolve from name.
        3. Ensure at least one field is provided for the update.
        4. Never ask user for id if it can be resolved automatically.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "product_id": types.Schema(type=types.Type.STRING, description="Product ID"),
                    "name": types.Schema(type=types.Type.STRING, description="New product name"),
                    "price": types.Schema(type=types.Type.NUMBER, description="New product price"),
                    "category_id": types.Schema(type=types.Type.INTEGER, description="New category ID"),
                    "description": types.Schema(type=types.Type.STRING, description="New product description"),
                    "image_urls": types.Schema(type=types.Type.ARRAY, description="New image URLs"),
                    "tags": types.Schema(type=types.Type.ARRAY, description="New tag names")
                },
                required=["product_id"]
            )
        ),
        types.FunctionDeclaration(
            name="delete_product",
            description="""Delete a product from the restaurant system.

        AUTONOMOUS RULES:
        1. If id is missing → call get_search_products to resolve it from name.
        2. Never ask user for id if it can be resolved automatically.
        3. Never guess the id.

        NOTE: Deleted products have status DELETED and cannot be toggled back.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"product_id": types.Schema(type=types.Type.STRING, description="Product ID")},
                required=["product_id"]
            )
        ),
        types.FunctionDeclaration(
            name="toggle_product_status",
            description="""Toggle product status between AVAILABLE and UNAVAILABLE.

        AUTONOMOUS RULES:
        1. If id is missing → call get_search_products to resolve it from name.
        2. Never guess the id.

        STATUS REFERENCE:
        - AVAILABLE   → active, visible to customers.
        - UNAVAILABLE → hidden, not deleted.
        - DELETED     → permanent, cannot be toggled back.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"product_id": types.Schema(type=types.Type.STRING, description="Product ID")},
                required=["product_id"]
            )
        ),
        types.FunctionDeclaration(
            name="get_all_customers",
            description="""Retrieve all customers from the restaurant system (admin only).

        USE THIS TOOL WHEN:
        - Admin asks to list or view all customers.
        - Need to resolve a user id before updating status.

        RESPONSE CONTAINS: id, fullName, email, phoneNumber, role,
        dateOfBirth, gender, status, avatar""",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="update_customer_status",
            description="""Update a customer's account status (admin only).

        PARAMETERS:
        - user_id (string, required): customer ID.
        - status (string, required): must be exactly ACTIVE, INACTIVE, or SUSPENDED.

        AUTONOMOUS RULES:
        1. If user_id is missing → call get_all_customers to resolve from name or email.
        2. Never guess the user_id.

        STATUS REFERENCE:
        - ACTIVE     → account fully operational.
        - INACTIVE   → account disabled, user cannot log in.
        - SUSPENDED  → account suspended due to policy violation.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "user_id": types.Schema(type=types.Type.STRING, description="User ID"),
                    "status": types.Schema(type=types.Type.STRING,
                                           description="New status: ACTIVE, INACTIVE, or SUSPENDED")
                },
                required=["user_id", "status"]
            )
        ),
        types.FunctionDeclaration(
            name="login",
            description="Login to the system",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "email": types.Schema(type=types.Type.STRING, description="Email"),
                    "password": types.Schema(type=types.Type.STRING, description="Password")
                },
                required=["email", "password"]
            )
        ),
        types.FunctionDeclaration(
            name="search_internet",
            description="""Search the internet for external information.

        USE THIS TOOL WHEN:
        - Need to find image URLs for banners, categories, or products.
        - User asks about external information not available in the system.
        - Do NOT use for internal system data — use the appropriate system tool instead.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"query": types.Schema(type=types.Type.STRING, description="Search query")},
                required=["query"]
            )
        ),
        types.FunctionDeclaration(
            name="search_documents",
            description="""Search internal documents (reports, guides, restaurant policies).

        USE THIS TOOL WHEN:
        - User asks about internal documents, reports, regulations, or policies.
        - Do NOT use for real-time system data like products, combos, or banners.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(type=types.Type.STRING, description="Search query for internal documents")},
                required=["query"]
            )
        ),
        # Analytics Tools
        types.FunctionDeclaration(
            name="get_analytics_summary",
            description="""Get comprehensive analytics summary with all business metrics in one call.
        This is the RECOMMENDED tool for AI agents to get complete business intelligence.

        USE THIS TOOL WHEN:
        - User asks for overall business performance or dashboard data
        - Need complete analytics including revenue, orders, products, customers, bookings
        - Want to understand business state at a glance
        - User asks "how is the business doing?" or "show me the analytics"

        RETURNS:
        - revenue: Revenue metrics and trends
        - orders: Order statistics and patterns  
        - products: Top selling products
        - customers: Customer engagement metrics
        - bookings: Booking statistics
        - insights: AI-ready insights and recommendations

        PERIOD OPTIONS: TODAY, YESTERDAY, LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH (default), LAST_MONTH, THIS_YEAR, CUSTOM
        For CUSTOM period, provide startDate and endDate in ISO 8601 format.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "period": types.Schema(type=types.Type.STRING, description="Time period (default: THIS_MONTH)"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Custom start date (ISO 8601 format, for CUSTOM period)"),
                    "end_date": types.Schema(type=types.Type.STRING, description="Custom end date (ISO 8601 format, for CUSTOM period)")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_revenue_analytics",
            description="""Get detailed revenue analytics and trends.

        USE THIS TOOL WHEN:
        - User specifically asks about revenue, sales, or income
        - Need detailed revenue breakdown (today, yesterday, week, month, year)
        - Want to analyze revenue growth and trends
        - User asks "how much money did we make?" or "what's the revenue?"

        RETURNS:
        - totalRevenue: Total revenue for period (VND)
        - todayRevenue, yesterdayRevenue: Daily revenue (VND)
        - growthRate: Percentage change (today vs yesterday)
        - averageOrderValue: Average order value (VND)
        - trend: "increasing", "decreasing", or "stable"
        - weekRevenue, monthRevenue, yearRevenue: Revenue breakdown""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "period": types.Schema(type=types.Type.STRING, description="Time period (default: THIS_MONTH)"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Custom start date (ISO 8601)"),
                    "end_date": types.Schema(type=types.Type.STRING, description="Custom end date (ISO 8601)")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_order_analytics",
            description="""Get order statistics and patterns.

        USE THIS TOOL WHEN:
        - User asks about orders, order status, or order volume
        - Need to analyze order patterns and peak times
        - Want to check pending/processing/completed orders
        - User asks "how many orders?" or "what's the busiest time?"

        RETURNS:
        - totalOrders, pendingOrders, processingOrders, confirmedOrders, completedOrders, cancelledOrders
        - cancelRate: Cancellation rate (%)
        - ordersByStatus: Breakdown by status
        - peakHour: Peak order time with hour, orderCount, revenue, timeRange
        - ordersByHour: Orders distribution by hour""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "period": types.Schema(type=types.Type.STRING, description="Time period (default: THIS_MONTH)"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Custom start date (ISO 8601)"),
                    "end_date": types.Schema(type=types.Type.STRING, description="Custom end date (ISO 8601)")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_product_analytics",
            description="""Get product performance analytics with top selling products.

        USE THIS TOOL WHEN:
        - User asks about product performance or best sellers
        - Need detailed product statistics (quantity sold, revenue, order count)
        - Want to see both top selling and top revenue products
        - User asks "what are the best sellers?" or "which products sell well?"

        RETURNS:
        - topSellingProducts: List by quantity sold (productId, name, imageUrl, quantity, revenue, orderCount, averagePrice, rank)
        - topRevenueProducts: List by total revenue
        - totalProductsSold: Total quantity sold
        - uniqueProductsSold: Number of unique products sold""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "limit": types.Schema(type=types.Type.INTEGER, description="Number of top products to return (default: 10)"),
                    "period": types.Schema(type=types.Type.STRING, description="Time period (default: THIS_MONTH)"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Custom start date (ISO 8601)"),
                    "end_date": types.Schema(type=types.Type.STRING, description="Custom end date (ISO 8601)")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_top_selling_products",
            description="""Quickly get only the top selling products (shortcut endpoint).

        USE THIS TOOL WHEN:
        - User only wants product names and quantities (simplified view)
        - Don't need detailed revenue/order statistics
        - Want faster response with minimal data

        RETURNS: List of top products with productId, productName, totalQuantitySold, rank only""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "limit": types.Schema(type=types.Type.INTEGER, description="Number of top products (default: 10)"),
                    "period": types.Schema(type=types.Type.STRING, description="Time period (default: THIS_MONTH)"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Custom start date (ISO 8601)"),
                    "end_date": types.Schema(type=types.Type.STRING, description="Custom end date (ISO 8601)")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_customer_analytics",
            description="""Get customer engagement and retention metrics.

        USE THIS TOOL WHEN:
        - User asks about customers, customer base, or user statistics
        - Need customer retention and engagement metrics
        - Want to analyze customer behavior
        - User asks "how many customers?" or "what's the retention rate?"

        RETURNS:
        - totalCustomers: Total number of customers
        - newCustomers: New customers in period
        - activeCustomers: Customers who made orders
        - averageOrdersPerCustomer: Average orders per customer
        - retentionRate: Customer retention rate (%)""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "period": types.Schema(type=types.Type.STRING, description="Time period (default: THIS_MONTH)"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Custom start date (ISO 8601)"),
                    "end_date": types.Schema(type=types.Type.STRING, description="Custom end date (ISO 8601)")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_booking_analytics",
            description="""Get table booking statistics.

        USE THIS TOOL WHEN:
        - User asks about bookings, reservations, or table status
        - Need booking statistics by status (pending, confirmed, completed, denied)
        - Want to check no-show rate
        - User asks "how many bookings?" or "what's the booking status?"

        RETURNS:
        - totalBookings, customerBookings, guestBookings, todayBookings
        - pendingBookings, confirmedBookings, completedBookings, deniedBookings
        - noShowRate: No-show rate (%)
        - bookingsByStatus: Breakdown by status""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "period": types.Schema(type=types.Type.STRING, description="Time period (default: THIS_MONTH)"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Custom start date (ISO 8601)"),
                    "end_date": types.Schema(type=types.Type.STRING, description="Custom end date (ISO 8601)")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_analytics_insights",
            description="""Get AI-ready insights and recommendations based on current analytics.
        This endpoint analyzes all metrics and generates natural language insights.

        USE THIS TOOL WHEN:
        - User asks for insights, recommendations, or analysis
        - Want AI-generated observations about business performance
        - Need to highlight key trends or issues
        - User asks "what should I know?" or "any recommendations?"

        RETURNS:
        List of insights with:
        - type: "positive" (good news), "negative" (warning), "neutral" (info), "recommendation" (suggestion)
        - category: "revenue", "orders", "products", "customers", "bookings"
        - message: Human-readable insight (in Vietnamese)
        - value: Numeric value if applicable
        - unit: Unit of measurement (%, portions, VND, etc.)

        EXAMPLES:
        - "Doanh thu hôm nay tăng 25.0% so với hôm qua"
        - "Sản phẩm bán chạy nhất: Phở Bò (250 phần)"
        - "Nên tăng cường marketing để duy trì momentum" """,
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
    ])
]


async def execute_tool(name: str, args: dict) -> str:
    """Execute a tool function and return JSON result."""
    logger.info(f"Executing tool: {name} with args: {args}")
    try:
        func = TOOL_FUNCTIONS.get(name)
        if not func:
            return json.dumps({"error": f"Unknown tool: {name}"})

        result = await func(**args)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return json.dumps({"error": str(e)})


async def chat(user_id: str, message: str) -> str:
    """
    Main chat function that orchestrates the entire flow.

    Flow:
    1. Fetch memories (long-term) and conversation history (short-term)
    2. Build prompt with all context
    3. Call LLM with tools (async, non-blocking)
    4. Handle function calls if any (with accumulated history)
    5. Return final response immediately
    6. Save to conversation cache + Ingest Agent (background)
    """
    logger.info(f"Chat: Processing message from user {user_id}")

    # Step 1: Fetch long-term memories
    memories, consolidated = await asyncio.gather(
        get_memories_by_user(user_id, limit=10),
        get_consolidated_memories_by_user(user_id, limit=5)
    )
    memory_context = format_memory_context(memories, consolidated)

    # Step 2: Get conversation history from cache (short-term context)
    conversation_history = get_conversation(user_id)
    
    # Step 3: Build contents with full conversation history
    contents = []
    
    # Add memory context as first system-like message if exists
    if memory_context:
        context_prompt = f"[MEMORY CONTEXT]\n{memory_context}\n\n[CONVERSATION START]"
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=context_prompt)]))
        contents.append(types.Content(role="model", parts=[types.Part.from_text(text="Tôi đã nhận được thông tin từ bộ nhớ. Hãy tiếp tục cuộc hội thoại.")]))
    
    # Add previous conversation history
    for msg in conversation_history:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
    
    # Add current user message
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
    
    # Save user message to cache immediately
    add_message(user_id, "user", message)
    
    logger.info(f"Chat: Built prompt with {len(conversation_history)} history messages")

    # LLM config (reused)
    llm_config = types.GenerateContentConfig(
        system_instruction=get_system_prompt(),
        temperature=0.7,
        tools=TOOL_DECLARATIONS
    )

    # Step 4: Call LLM with tools (async - non-blocking!)
    response = await call_llm_with_retry(
        lambda: client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=llm_config
        )
    )

    # Step 5: Handle function calls with accumulated history
    max_iterations = 5
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # Check if response has function calls
        function_calls = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    function_calls.append(part.function_call)

        if not function_calls:
            break

        # Append assistant response to history
        contents.append(response.candidates[0].content)

        # Execute function calls
        function_responses = []
        for fc in function_calls:
            result = await execute_tool(fc.name, dict(fc.args))
            function_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result}
                )
            )
            logger.info(f"Chat: Tool {fc.name} returned: {result[:200]}...")

        # Append tool results to history
        contents.append(types.Content(role="user", parts=function_responses))

        # Continue conversation with accumulated history (async)
        response = await call_llm_with_retry(
            lambda: client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=llm_config
            )
        )

    # Step 6: Extract final text response
    final_response = response.text if response.text else "Xin lỗi, tôi không thể xử lý yêu cầu này."
    logger.info(f"Chat: Final response length={len(final_response)}")

    # Step 7: Save assistant response to conversation cache
    add_message(user_id, "assistant", final_response)

    # Step 8: Ingest Agent - store conversation in background (non-blocking)
    asyncio.create_task(ingest_memory(user_id, message, final_response))
    logger.info(f"Chat: Ingest task scheduled in background")

    return final_response
