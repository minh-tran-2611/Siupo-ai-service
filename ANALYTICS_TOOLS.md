# Analytics Tools Documentation

## Overview
The Analytics Tools module provides comprehensive business intelligence capabilities for the AI Agent. These tools connect to the Backend API's analytics endpoints and enable the agent to retrieve and analyze restaurant performance metrics.

## Features

### 🎯 Complete Analytics Summary
- **`get_analytics_summary()`** - One-stop analytics endpoint (RECOMMENDED)
  - Returns all metrics: revenue, orders, products, customers, bookings, insights
  - Perfect for answering "How is the business doing?"
  - Cached for 5 minutes for optimal performance

### 💰 Revenue Analytics
- **`get_revenue_analytics()`** - Detailed revenue metrics
  - Total revenue, daily revenue, growth rate
  - Average order value (AOV)
  - Revenue trends (increasing/decreasing/stable)
  - Weekly, monthly, yearly breakdowns

### 📦 Order Analytics
- **`get_order_analytics()`** - Order statistics and patterns
  - Order counts by status (pending, processing, confirmed, completed, cancelled)
  - Cancellation rate
  - Peak hour analysis
  - Hourly order distribution

### 🍜 Product Analytics
- **`get_product_analytics()`** - Product performance metrics
  - Top selling products by quantity
  - Top revenue-generating products
  - Product details: quantity sold, revenue, order count, average price
  - Total and unique products sold

- **`get_top_selling_products()`** - Quick top sellers (shortcut)
  - Simplified response with just product names and quantities
  - Faster response time

### 👥 Customer Analytics
- **`get_customer_analytics()`** - Customer engagement metrics
  - Total customers, new customers, active customers
  - Average orders per customer
  - Customer retention rate

### 📅 Booking Analytics
- **`get_booking_analytics()`** - Table booking statistics
  - Bookings by type (customer vs guest)
  - Bookings by status (pending, confirmed, completed, denied)
  - No-show rate
  - Today's bookings count

### 💡 AI Insights
- **`get_analytics_insights()`** - Smart recommendations
  - AI-generated insights in Vietnamese
  - Categorized by type: positive, negative, neutral, recommendation
  - Based on real-time analytics data
  - Examples:
    - "Doanh thu hôm nay tăng 25.0% so với hôm qua"
    - "Sản phẩm bán chạy nhất: Phở Bò (250 phần)"
    - "Nên tăng cường marketing để duy trì momentum"

## Time Periods

All analytics tools support flexible time periods:

| Period | Description |
|--------|-------------|
| `TODAY` | Current day (00:00 - 23:59) |
| `YESTERDAY` | Previous day |
| `LAST_7_DAYS` | Last 7 days from now |
| `LAST_30_DAYS` | Last 30 days from now |
| `THIS_MONTH` | Current month (default) |
| `LAST_MONTH` | Previous month (full month) |
| `THIS_YEAR` | Current year (Jan 1 - today) |
| `CUSTOM` | Custom date range (requires `start_date` & `end_date` in ISO 8601 format) |

## Usage Examples

### Example 1: Get Complete Business Overview
```python
# Agent receives: "Cho tôi xem tình hình kinh doanh tháng này"
summary = await get_analytics_summary(period="THIS_MONTH")

# Response includes:
# - Revenue: 50,000,000 VND, growth 25%
# - Orders: 400 total, 10 cancelled (2.5% cancel rate)
# - Top products: Phở Bò (250 portions)
# - Customers: 5000 total, 150 new, 24% retention
# - Bookings: 200 total, 25 pending
# - Insights: ["Revenue increasing", "Best seller: Phở Bò", ...]
```

### Example 2: Analyze Revenue Trends
```python
# Agent receives: "Doanh thu hôm nay thế nào?"
revenue = await get_revenue_analytics(period="TODAY")

# Response:
# {
#   "totalRevenue": 2500000,
#   "yesterdayRevenue": 2000000,
#   "growthRate": 25.0,
#   "trend": "increasing",
#   "averageOrderValue": 125000
# }
```

### Example 3: Find Best Sellers
```python
# Agent receives: "Món nào bán chạy nhất tuần này?"
products = await get_top_selling_products(limit=5, period="LAST_7_DAYS")

# Response:
# [
#   {"rank": 1, "productName": "Phở Bò", "totalQuantitySold": 250},
#   {"rank": 2, "productName": "Bún Chả", "totalQuantitySold": 180},
#   ...
# ]
```

### Example 4: Custom Date Range
```python
# Agent receives: "Doanh thu từ 1/3 đến 15/3 là bao nhiêu?"
revenue = await get_revenue_analytics(
    period="CUSTOM",
    start_date="2026-03-01T00:00:00",
    end_date="2026-03-15T23:59:59"
)
```

### Example 5: Get Smart Insights
```python
# Agent receives: "Có nhận xét gì về tình hình kinh doanh không?"
insights = await get_analytics_insights()

# Response:
# [
#   {
#     "type": "positive",
#     "category": "revenue",
#     "message": "Doanh thu hôm nay tăng 25.0% so với hôm qua",
#     "value": 25.0,
#     "unit": "%"
#   },
#   {
#     "type": "recommendation",
#     "category": "marketing",
#     "message": "Nên tăng cường marketing để duy trì momentum"
#   }
# ]
```

## Authentication

All analytics endpoints require **ADMIN** role authentication. The tools automatically:
1. Check for valid access token
2. Auto-login with admin credentials if needed (from `.env`)
3. Attach JWT token to all requests
4. Handle token expiration and refresh

Configuration in `.env`:
```
ADMIN_EMAIL=admin@siupo.com
ADMIN_PASSWORD=Admin@123
```

## Performance

- **Caching**: All endpoints cached for 5 minutes
- **Average response time**: < 500ms (with caching)
- **Concurrent requests**: Supported
- **Timeout**: 60 seconds for all requests

## Error Handling

The tools handle common errors:
- **401 Unauthorized**: Auto-login and retry
- **403 Forbidden**: Report insufficient permissions
- **404 Not Found**: Return empty data
- **429 Rate Limit**: Exponential backoff (managed by chat service)
- **Network errors**: Timeout after 60 seconds

## Integration with AI Agent

The analytics tools are fully integrated into the AI Agent's conversation flow:

1. **Tool Discovery**: Agent automatically knows when to use analytics tools based on user queries
2. **Autonomous Execution**: Agent decides which analytics tool to call without asking
3. **Context-Aware**: Agent combines analytics data with memory and RAG for intelligent responses
4. **Natural Language Output**: Agent translates analytics data into conversational Vietnamese

### Example Conversation Flow

**User**: "Tình hình kinh doanh thế nào?"

**Agent Internal Flow**:
1. Recognizes analytics query
2. Calls `get_analytics_summary(period="THIS_MONTH")`
3. Receives all metrics
4. Calls `get_analytics_insights()` for recommendations
5. Synthesizes natural response

**Agent Response**: 
"Tháng này nhà hàng đang hoạt động rất tốt! 

📈 Doanh thu đạt 50 triệu VND, tăng 25% so với hôm qua
📦 Đã phục vụ 400 đơn hàng, tỷ lệ hủy chỉ 2.5%
🍜 Món bán chạy nhất là Phở Bò với 250 phần
👥 Có 150 khách hàng mới, tỷ lệ giữ chân khách 24%
📅 200 lượt đặt bàn, 25 đang chờ xác nhận

💡 Gợi ý: Nên tăng cường marketing để duy trì đà tăng trưởng này!"

## Backend API Integration

These tools connect to:
- **Base URL**: `http://host.docker.internal:8080` (configurable via `BE_BASE_URL` env var)
- **API Path**: `/api/analytics/*`
- **Documentation**: See `BE/ANALYTICS_API.md` for full API specs

## Testing

To test analytics tools:

```python
# Test in Python REPL
from app.tools.analytics_tools import *
import asyncio

# Test summary
summary = asyncio.run(get_analytics_summary(period="THIS_MONTH"))
print(summary)

# Test insights
insights = asyncio.run(get_analytics_insights())
print(insights)
```

## Future Enhancements

Potential improvements:
- [ ] Real-time WebSocket updates for live analytics
- [ ] Export analytics to PDF/Excel
- [ ] Predictive analytics (ML-based forecasting)
- [ ] Custom KPI tracking
- [ ] Email/notification alerts for key metrics
- [ ] Comparative analysis (period-over-period)

## Support

For issues or questions:
1. Check Backend logs: `BE/logs/`
2. Check Agent logs: `AiAgent-service/logs/`
3. Verify JWT token validity
4. Test API endpoints directly using Postman/curl
5. Review `ANALYTICS_API.md` for API specifications

---

**Created**: 2026-04-08  
**Last Updated**: 2026-04-08  
**Version**: 1.0.0
