"""
Tool Declarations — Gemini FunctionDeclaration objects grouped by agent.

Extracted from chat_service.py monolith into per-agent groups.
Each agent uses its own declaration set so LLM only sees relevant tools.
"""
from google.genai import types


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MANAGEMENT AGENT — Restaurant CRUD operations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MANAGEMENT_DECLARATIONS = [
    types.Tool(function_declarations=[
        # ── Banner ──
        types.FunctionDeclaration(
            name="get_all_banners",
            description="""Retrieve all banners from the restaurant system.
        USE WHEN: list/view banners, verify positions, find banner id.
        DEFAULT POSITIONS: Home1, Home2, Menu1-4, AboutUs1-5, PlaceTable1
        RULES: Always call before creating/deleting a banner.""",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="get_banner_by_id",
            description="""Get a specific banner by ID.
        RULES: If user provides position not id, call get_all_banners first.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"banner_id": types.Schema(type=types.Type.STRING, description="Banner ID")},
                required=["banner_id"]
            )
        ),
        types.FunctionDeclaration(
            name="create_banner",
            description="""Create a new banner.
        AUTONOMOUS RULES:
        1. Call get_all_banners first to check occupied positions.
        2. If url missing → search_internet for image.
        3. If position missing → select first unoccupied.
        4. Never create on occupied position.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "url": types.Schema(type=types.Type.STRING, description="Image URL"),
                    "position": types.Schema(type=types.Type.STRING, description="Banner position")
                },
                required=["url", "position"]
            )
        ),
        types.FunctionDeclaration(
            name="update_banner",
            description="""Update an existing banner by ID.
        RULES: If id missing → resolve via get_all_banners.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "banner_id": types.Schema(type=types.Type.STRING, description="Banner ID"),
                    "url": types.Schema(type=types.Type.STRING, description="New image URL"),
                    "position": types.Schema(type=types.Type.STRING, description="New position")
                },
                required=["banner_id", "url", "position"]
            )
        ),
        types.FunctionDeclaration(
            name="delete_banner",
            description="""Delete a banner. If user gives position → resolve id via get_all_banners.
        BULK DELETE: get_all_banners → iterate → delete each.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"banner_id": types.Schema(type=types.Type.STRING, description="Banner ID")},
                required=["banner_id"]
            )
        ),

        # ── Category ──
        types.FunctionDeclaration(
            name="get_categories",
            description="Retrieve all categories. Call before create/update/delete to check duplicates or resolve id.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="create_category",
            description="""Create a new category.
        RULES: Check duplicates via get_categories first. If image missing → search_internet.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Category name"),
                    "image_url": types.Schema(type=types.Type.STRING, description="Image URL (optional)")
                },
                required=["name"]
            )
        ),
        types.FunctionDeclaration(
            name="update_category",
            description="Update a category. Resolve id via get_categories if needed.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "category_id": types.Schema(type=types.Type.STRING, description="Category ID"),
                    "name": types.Schema(type=types.Type.STRING, description="New name"),
                    "image_url": types.Schema(type=types.Type.STRING, description="New image URL")
                },
                required=["category_id"]
            )
        ),
        types.FunctionDeclaration(
            name="delete_category",
            description="Delete a category. Resolve id via get_categories if user gives name.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"category_id": types.Schema(type=types.Type.STRING, description="Category ID")},
                required=["category_id"]
            )
        ),

        # ── Combo ──
        types.FunctionDeclaration(
            name="get_all_combos",
            description="Retrieve all combos. Call before update/delete to resolve id.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="get_combo_by_id",
            description="Get a specific combo by ID.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"combo_id": types.Schema(type=types.Type.STRING, description="Combo ID")},
                required=["combo_id"]
            )
        ),
        types.FunctionDeclaration(
            name="create_combo",
            description="""Create a new combo.
        PARAMS: name (required), base_price (required), items [{productId, quantity, displayOrder}] (required).
        RULES: Resolve productId via get_search_products. Image missing → search_internet.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Combo name"),
                    "base_price": types.Schema(type=types.Type.NUMBER, description="Base price >= 0"),
                    "items": types.Schema(type=types.Type.ARRAY, description="[{productId, quantity, displayOrder}]"),
                    "description": types.Schema(type=types.Type.STRING, description="Description (optional)"),
                    "image_urls": types.Schema(type=types.Type.ARRAY, description="Image URLs (optional)")
                },
                required=["name", "base_price", "items"]
            )
        ),
        types.FunctionDeclaration(
            name="update_combo",
            description="Update a combo. Resolve id via get_all_combos if needed.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "combo_id": types.Schema(type=types.Type.STRING, description="Combo ID"),
                    "name": types.Schema(type=types.Type.STRING, description="New name"),
                    "base_price": types.Schema(type=types.Type.NUMBER, description="New price"),
                    "items": types.Schema(type=types.Type.ARRAY, description="New items"),
                    "description": types.Schema(type=types.Type.STRING, description="New description"),
                    "image_urls": types.Schema(type=types.Type.ARRAY, description="New image URLs")
                },
                required=["combo_id"]
            )
        ),
        types.FunctionDeclaration(
            name="delete_combo",
            description="Delete a combo. Resolve id via get_all_combos if user gives name.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"combo_id": types.Schema(type=types.Type.STRING, description="Combo ID")},
                required=["combo_id"]
            )
        ),
        types.FunctionDeclaration(
            name="toggle_combo_status",
            description="Toggle combo AVAILABLE/UNAVAILABLE. Resolve id via get_all_combos.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"combo_id": types.Schema(type=types.Type.STRING, description="Combo ID")},
                required=["combo_id"]
            )
        ),

        # ── Notification ──
        types.FunctionDeclaration(
            name="get_all_notifications_admin",
            description="Get all notifications (admin view).",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="create_notification",
            description="""Send notification. title + content required.
        user_id → specific user. send_to_all=true → broadcast.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title": types.Schema(type=types.Type.STRING, description="Title"),
                    "content": types.Schema(type=types.Type.STRING, description="Content"),
                    "user_id": types.Schema(type=types.Type.INTEGER, description="User ID (optional)"),
                    "send_to_all": types.Schema(type=types.Type.BOOLEAN, description="Broadcast (default: false)")
                },
                required=["title", "content"]
            )
        ),
        types.FunctionDeclaration(
            name="get_my_notifications",
            description="Get current user's notifications.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),

        # ── Product ──
        types.FunctionDeclaration(
            name="get_search_products",
            description="""Search products by name, category, or price range.
        RULES: Call get_categories first if user gives category name not id.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Product name"),
                    "category_ids": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.INTEGER), description="Category IDs"),
                    "min_price": types.Schema(type=types.Type.NUMBER, description="Min price"),
                    "max_price": types.Schema(type=types.Type.NUMBER, description="Max price")
                }
            )
        ),
        types.FunctionDeclaration(
            name="create_product",
            description="""Create a product. name + price + category_id required.
        RULES: Resolve category_id via get_categories. Image missing → search_internet.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Name (2-100 chars)"),
                    "price": types.Schema(type=types.Type.NUMBER, description="Price > 0"),
                    "category_id": types.Schema(type=types.Type.INTEGER, description="Category ID"),
                    "description": types.Schema(type=types.Type.STRING, description="Description (optional)"),
                    "image_urls": types.Schema(type=types.Type.ARRAY, description="Image URLs (optional)"),
                    "tags": types.Schema(type=types.Type.ARRAY, description="Tags (optional)")
                },
                required=["name", "price", "category_id"]
            )
        ),
        types.FunctionDeclaration(
            name="update_product",
            description="Update a product. Resolve id via get_search_products if needed.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "product_id": types.Schema(type=types.Type.STRING, description="Product ID"),
                    "name": types.Schema(type=types.Type.STRING, description="New name"),
                    "price": types.Schema(type=types.Type.NUMBER, description="New price"),
                    "category_id": types.Schema(type=types.Type.INTEGER, description="New category ID"),
                    "description": types.Schema(type=types.Type.STRING, description="New description"),
                    "image_urls": types.Schema(type=types.Type.ARRAY, description="New image URLs"),
                    "tags": types.Schema(type=types.Type.ARRAY, description="New tags")
                },
                required=["product_id"]
            )
        ),
        types.FunctionDeclaration(
            name="delete_product",
            description="Delete a product. Resolve id via get_search_products. Status becomes DELETED (permanent).",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"product_id": types.Schema(type=types.Type.STRING, description="Product ID")},
                required=["product_id"]
            )
        ),
        types.FunctionDeclaration(
            name="toggle_product_status",
            description="Toggle product AVAILABLE/UNAVAILABLE. Cannot toggle DELETED status.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"product_id": types.Schema(type=types.Type.STRING, description="Product ID")},
                required=["product_id"]
            )
        ),

        # ── User ──
        types.FunctionDeclaration(
            name="get_all_customers",
            description="Get all customers (admin). Resolve user_id from name/email.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="update_customer_status",
            description="Update customer status: ACTIVE, INACTIVE, or SUSPENDED.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "user_id": types.Schema(type=types.Type.STRING, description="User ID"),
                    "status": types.Schema(type=types.Type.STRING, description="ACTIVE, INACTIVE, or SUSPENDED")
                },
                required=["user_id", "status"]
            )
        ),

        # ── Auth ──
        types.FunctionDeclaration(
            name="login",
            description="Login to the system.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "email": types.Schema(type=types.Type.STRING, description="Email"),
                    "password": types.Schema(type=types.Type.STRING, description="Password")
                },
                required=["email", "password"]
            )
        ),

        # ── Utility ──
        types.FunctionDeclaration(
            name="search_internet",
            description="Search the internet for external information or images.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"query": types.Schema(type=types.Type.STRING, description="Search query")},
                required=["query"]
            )
        ),
    ])
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ANALYTICS AGENT — Business intelligence & insights
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ANALYTICS_DECLARATIONS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="get_analytics_summary",
            description="""Get comprehensive analytics summary (revenue, orders, products, customers, bookings, insights).
        RECOMMENDED for complete business overview.
        PERIOD: TODAY, YESTERDAY, LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH (default), LAST_MONTH, THIS_YEAR, CUSTOM.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "period": types.Schema(type=types.Type.STRING, description="Time period"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Start date (ISO 8601, for CUSTOM)"),
                    "end_date": types.Schema(type=types.Type.STRING, description="End date (ISO 8601, for CUSTOM)")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_revenue_analytics",
            description="Detailed revenue: total, today, yesterday, growth rate, average order value, trend.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "period": types.Schema(type=types.Type.STRING, description="Time period"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Start date"),
                    "end_date": types.Schema(type=types.Type.STRING, description="End date")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_order_analytics",
            description="Order stats: total, by status, cancel rate, peak hour, hourly distribution.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "period": types.Schema(type=types.Type.STRING, description="Time period"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Start date"),
                    "end_date": types.Schema(type=types.Type.STRING, description="End date")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_product_analytics",
            description="Product performance: top selling by quantity and revenue, total/unique products sold.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "limit": types.Schema(type=types.Type.INTEGER, description="Top N products (default: 10)"),
                    "period": types.Schema(type=types.Type.STRING, description="Time period"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Start date"),
                    "end_date": types.Schema(type=types.Type.STRING, description="End date")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_top_selling_products",
            description="Quick shortcut: top selling products with name and quantity only.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "limit": types.Schema(type=types.Type.INTEGER, description="Top N (default: 10)"),
                    "period": types.Schema(type=types.Type.STRING, description="Time period"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Start date"),
                    "end_date": types.Schema(type=types.Type.STRING, description="End date")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_customer_analytics",
            description="Customer metrics: total, new, active, avg orders/customer, retention rate.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "period": types.Schema(type=types.Type.STRING, description="Time period"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Start date"),
                    "end_date": types.Schema(type=types.Type.STRING, description="End date")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_booking_analytics",
            description="Booking stats: total, by status, today, no-show rate.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "period": types.Schema(type=types.Type.STRING, description="Time period"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Start date"),
                    "end_date": types.Schema(type=types.Type.STRING, description="End date")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_analytics_insights",
            description="AI-ready insights and recommendations. Returns typed insights (positive/negative/recommendation).",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),

        # ── Shared READ tools (for supplementary data) ──
        types.FunctionDeclaration(
            name="get_search_products",
            description="Search products to get product details for analysis.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Product name"),
                    "category_ids": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.INTEGER), description="Category IDs"),
                    "min_price": types.Schema(type=types.Type.NUMBER, description="Min price"),
                    "max_price": types.Schema(type=types.Type.NUMBER, description="Max price")
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_all_combos",
            description="Get all combos for combo performance analysis.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="get_categories",
            description="Get categories for category-level analysis.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="get_all_customers",
            description="Get customer list for customer analysis.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),
        types.FunctionDeclaration(
            name="search_internet",
            description="Search internet for benchmarks or industry data.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"query": types.Schema(type=types.Type.STRING, description="Search query")},
                required=["query"]
            )
        ),
    ])
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ORCHESTRATOR — Meta-tools to call sub-agents
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ORCHESTRATOR_DECLARATIONS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="call_management_agent",
            description="""Delegate a restaurant management task to the Management Agent.

        CALL THIS WHEN the user wants to:
        - Add, edit, delete, or view: products, categories, combos, banners, notifications, users
        - Search for products or categories
        - Toggle product/combo status
        - Manage customer accounts
        - Any CRUD operation on restaurant data

        IMPORTANT: Pass the COMPLETE user request as the task parameter.
        Include all details (names, prices, quantities, etc.) so the agent can work autonomously.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "task": types.Schema(type=types.Type.STRING,
                                         description="Complete task description with all details from user request")
                },
                required=["task"]
            )
        ),
        types.FunctionDeclaration(
            name="call_analytics_agent",
            description="""Delegate a business analytics task to the Analytics Agent.

        CALL THIS WHEN the user wants to:
        - View revenue, sales, or income data
        - Check order statistics or patterns
        - Analyze product performance or best sellers
        - Review customer metrics or retention
        - Check booking/reservation statistics
        - Get business insights or recommendations
        - Any analysis, reporting, or data-driven question

        IMPORTANT: Pass the COMPLETE user request as the task parameter.
        Include time period or specific metrics if mentioned.""",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "task": types.Schema(type=types.Type.STRING,
                                         description="Complete analytics task with time period and specific metrics")
                },
                required=["task"]
            )
        ),
        types.FunctionDeclaration(
            name="search_internet",
            description="Search the internet for external information.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"query": types.Schema(type=types.Type.STRING, description="Search query")},
                required=["query"]
            )
        ),
        types.FunctionDeclaration(
            name="search_documents",
            description="Search internal documents, policies, reports, and guides (RAG).",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"query": types.Schema(type=types.Type.STRING, description="Document search query")},
                required=["query"]
            )
        ),
    ])
]
