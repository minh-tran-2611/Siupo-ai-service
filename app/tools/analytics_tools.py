"""
Analytics tools for retrieving business intelligence data.
All endpoints require ADMIN authentication.
"""
import os
import httpx
from loguru import logger
from typing import Optional, List
from app.tools.auth_tools import ensure_authenticated, get_auth_headers

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")
TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)


async def get_analytics_summary(period: str = "THIS_MONTH", start_date: str = None, end_date: str = None) -> dict:
    """
    Get comprehensive analytics summary with all metrics in one call.
    This is the recommended endpoint for AI agents to get complete business intelligence.
    
    Args:
        period: Time period filter. Options: TODAY, YESTERDAY, LAST_7_DAYS, LAST_30_DAYS, 
                THIS_MONTH, LAST_MONTH, THIS_YEAR, CUSTOM
        start_date: Custom start date (ISO 8601 format, required if period=CUSTOM)
        end_date: Custom end date (ISO 8601 format, required if period=CUSTOM)
    
    Returns:
        Complete analytics summary including:
        - revenue: Revenue metrics and trends
        - orders: Order statistics and patterns
        - products: Top selling products
        - customers: Customer engagement metrics
        - bookings: Booking statistics
        - insights: AI-ready insights and recommendations
    """
    logger.info(f"Tool: get_analytics_summary(period={period}, start_date={start_date}, end_date={end_date})")
    
    await ensure_authenticated()
    
    params = {"period": period}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/analytics/summary",
            params=params,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_revenue_analytics(period: str = "THIS_MONTH", start_date: str = None, end_date: str = None) -> dict:
    """
    Get detailed revenue analytics and trends.
    
    Args:
        period: Time period filter (TODAY, YESTERDAY, LAST_7_DAYS, LAST_30_DAYS, 
                THIS_MONTH, LAST_MONTH, THIS_YEAR, CUSTOM)
        start_date: Custom start date (ISO 8601 format)
        end_date: Custom end date (ISO 8601 format)
    
    Returns:
        Revenue metrics including:
        - totalRevenue: Total revenue for the period (VND)
        - todayRevenue: Today's revenue (VND)
        - yesterdayRevenue: Yesterday's revenue (VND)
        - growthRate: Percentage change (today vs yesterday)
        - averageOrderValue: Average order value (VND)
        - trend: "increasing", "decreasing", or "stable"
        - weekRevenue: Weekly revenue (VND)
        - monthRevenue: Monthly revenue (VND)
        - yearRevenue: Yearly revenue (VND)
    """
    logger.info(f"Tool: get_revenue_analytics(period={period})")
    
    await ensure_authenticated()
    
    params = {"period": period}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/analytics/revenue",
            params=params,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_order_analytics(period: str = "THIS_MONTH", start_date: str = None, end_date: str = None) -> dict:
    """
    Get order statistics and patterns.
    
    Args:
        period: Time period filter
        start_date: Custom start date (ISO 8601 format)
        end_date: Custom end date (ISO 8601 format)
    
    Returns:
        Order analytics including:
        - totalOrders: Total number of orders
        - pendingOrders: Orders waiting to be processed
        - processingOrders: Orders being prepared
        - confirmedOrders: Confirmed orders
        - completedOrders: Successfully completed orders
        - cancelledOrders: Cancelled orders
        - cancelRate: Cancellation rate (%)
        - ordersByStatus: Breakdown by status
        - peakHour: Peak order time with hour, orderCount, revenue, timeRange
        - ordersByHour: Orders distribution by hour
    """
    logger.info(f"Tool: get_order_analytics(period={period})")
    
    await ensure_authenticated()
    
    params = {"period": period}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/analytics/orders",
            params=params,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_product_analytics(limit: int = 10, period: str = "THIS_MONTH", start_date: str = None, end_date: str = None) -> dict:
    """
    Get product performance analytics with top selling products.
    
    Args:
        limit: Number of top products to return (default: 10)
        period: Time period filter
        start_date: Custom start date (ISO 8601 format)
        end_date: Custom end date (ISO 8601 format)
    
    Returns:
        Product analytics including:
        - topSellingProducts: List of top selling products by quantity
          Each product contains: productId, productName, productImageUrl, 
          totalQuantitySold, totalRevenue, orderCount, averagePrice, rank
        - topRevenueProducts: List of top products by revenue
        - totalProductsSold: Total quantity of all products sold
        - uniqueProductsSold: Number of unique products sold
    """
    logger.info(f"Tool: get_product_analytics(limit={limit}, period={period})")
    
    await ensure_authenticated()
    
    params = {"limit": limit, "period": period}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/analytics/products",
            params=params,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_top_selling_products(limit: int = 10, period: str = "THIS_MONTH", start_date: str = None, end_date: str = None) -> dict:
    """
    Quickly get only the top selling products (shortcut endpoint).
    
    Args:
        limit: Number of top products to return (default: 10)
        period: Time period filter
        start_date: Custom start date (ISO 8601 format)
        end_date: Custom end date (ISO 8601 format)
    
    Returns:
        List of top selling products with productId, productName, totalQuantitySold, rank
    """
    logger.info(f"Tool: get_top_selling_products(limit={limit}, period={period})")
    
    await ensure_authenticated()
    
    params = {"limit": limit, "period": period}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/analytics/products/top-selling",
            params=params,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_customer_analytics(period: str = "THIS_MONTH", start_date: str = None, end_date: str = None) -> dict:
    """
    Get customer engagement and retention metrics.
    
    Args:
        period: Time period filter
        start_date: Custom start date (ISO 8601 format)
        end_date: Custom end date (ISO 8601 format)
    
    Returns:
        Customer analytics including:
        - totalCustomers: Total number of customers
        - newCustomers: New customers in period
        - activeCustomers: Active customers (made orders)
        - averageOrdersPerCustomer: Average orders per customer
        - retentionRate: Customer retention rate (%)
    """
    logger.info(f"Tool: get_customer_analytics(period={period})")
    
    await ensure_authenticated()
    
    params = {"period": period}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/analytics/customers",
            params=params,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_booking_analytics(period: str = "THIS_MONTH", start_date: str = None, end_date: str = None) -> dict:
    """
    Get table booking statistics.
    
    Args:
        period: Time period filter
        start_date: Custom start date (ISO 8601 format)
        end_date: Custom end date (ISO 8601 format)
    
    Returns:
        Booking analytics including:
        - totalBookings: Total number of bookings
        - customerBookings: Bookings by registered customers
        - guestBookings: Bookings by guests
        - todayBookings: Today's bookings count
        - pendingBookings: Bookings waiting for confirmation
        - confirmedBookings: Confirmed bookings
        - completedBookings: Completed bookings
        - deniedBookings: Denied bookings
        - noShowRate: No-show rate (%)
        - bookingsByStatus: Breakdown by status (PENDING, CONFIRMED, COMPLETED, DENIED)
    """
    logger.info(f"Tool: get_booking_analytics(period={period})")
    
    await ensure_authenticated()
    
    params = {"period": period}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/analytics/bookings",
            params=params,
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_analytics_insights() -> dict:
    """
    Get AI-ready insights and recommendations based on current analytics.
    This endpoint analyzes all metrics and generates natural language insights.
    
    Returns:
        List of insights, each containing:
        - type: "positive", "negative", "neutral", or "recommendation"
        - category: "revenue", "orders", "products", "customers", or "bookings"
        - message: Human-readable insight message (in Vietnamese)
        - value: Numeric value if applicable
        - unit: Unit of measurement (%, portions, VND, etc.)
    
    Example insights:
    - "Doanh thu hôm nay tăng 25.0% so với hôm qua"
    - "Sản phẩm bán chạy nhất: Phở Bò (250 phần)"
    - "Nên tăng cường marketing để duy trì momentum"
    """
    logger.info("Tool: get_analytics_insights()")
    
    await ensure_authenticated()
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BE_BASE_URL}/api/analytics/insights",
            headers=get_auth_headers()
        )
        response.raise_for_status()
        return response.json()
