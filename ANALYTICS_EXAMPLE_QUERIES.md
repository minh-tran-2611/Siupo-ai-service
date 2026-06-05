# Analytics Tool Example Queries

## 📊 Analytics Summary

### General Business Overview
```
User: "Cho tôi xem tình hình kinh doanh tháng này"
Tool: get_analytics_summary(period="THIS_MONTH")

User: "Nhà hàng hoạt động thế nào tuần qua?"
Tool: get_analytics_summary(period="LAST_7_DAYS")

User: "Báo cáo tổng quan hôm nay"
Tool: get_analytics_summary(period="TODAY")
```

## 💰 Revenue Queries

### Daily Revenue
```
User: "Doanh thu hôm nay là bao nhiêu?"
Tool: get_revenue_analytics(period="TODAY")

User: "Hôm nay kiếm được bao nhiêu tiền?"
Tool: get_revenue_analytics(period="TODAY")
```

### Revenue Comparison
```
User: "So sánh doanh thu hôm nay với hôm qua"
Tool: get_revenue_analytics(period="TODAY")
→ Returns growthRate comparing today vs yesterday

User: "Doanh thu có tăng không?"
Tool: get_revenue_analytics(period="THIS_MONTH")
→ Returns trend: "increasing", "decreasing", or "stable"
```

### Period Revenue
```
User: "Doanh thu tuần này?"
Tool: get_revenue_analytics(period="LAST_7_DAYS")

User: "Tháng trước kiếm được bao nhiêu?"
Tool: get_revenue_analytics(period="LAST_MONTH")

User: "Doanh thu năm nay"
Tool: get_revenue_analytics(period="THIS_YEAR")
```

### Custom Date Range
```
User: "Doanh thu từ 1/3 đến 15/3"
Tool: get_revenue_analytics(
    period="CUSTOM",
    start_date="2026-03-01T00:00:00",
    end_date="2026-03-15T23:59:59"
)
```

## 📦 Order Queries

### Order Counts
```
User: "Hôm nay có bao nhiêu đơn hàng?"
Tool: get_order_analytics(period="TODAY")

User: "Có bao nhiêu đơn đang chờ xử lý?"
Tool: get_order_analytics(period="TODAY")
→ Returns pendingOrders count
```

### Order Status
```
User: "Bao nhiêu đơn đã hoàn thành tháng này?"
Tool: get_order_analytics(period="THIS_MONTH")
→ Returns completedOrders

User: "Tỷ lệ hủy đơn thế nào?"
Tool: get_order_analytics(period="THIS_MONTH")
→ Returns cancelRate
```

### Peak Hours
```
User: "Giờ nào nhà hàng đông nhất?"
Tool: get_order_analytics(period="LAST_7_DAYS")
→ Returns peakHour with hour, orderCount, revenue

User: "Khung giờ nào có nhiều đơn nhất?"
Tool: get_order_analytics(period="THIS_MONTH")
→ Returns ordersByHour distribution
```

## 🍜 Product Queries

### Best Sellers
```
User: "Món nào bán chạy nhất?"
Tool: get_top_selling_products(limit=5, period="THIS_MONTH")

User: "Top 10 món ăn phổ biến nhất"
Tool: get_top_selling_products(limit=10, period="THIS_MONTH")

User: "Sản phẩm nào bán chạy tuần này?"
Tool: get_top_selling_products(limit=5, period="LAST_7_DAYS")
```

### Detailed Product Analytics
```
User: "Phân tích sản phẩm chi tiết"
Tool: get_product_analytics(limit=10, period="THIS_MONTH")
→ Returns topSellingProducts + topRevenueProducts

User: "Món nào mang lại doanh thu cao nhất?"
Tool: get_product_analytics(limit=5, period="THIS_MONTH")
→ Check topRevenueProducts
```

### Product Performance
```
User: "Phở Bò bán được bao nhiêu phần?"
Tool: get_product_analytics(limit=20, period="THIS_MONTH")
→ Find "Phở Bò" in results

User: "Có bao nhiêu món khác nhau được bán?"
Tool: get_product_analytics(period="THIS_MONTH")
→ Returns uniqueProductsSold
```

## 👥 Customer Queries

### Customer Base
```
User: "Có bao nhiêu khách hàng?"
Tool: get_customer_analytics(period="THIS_MONTH")
→ Returns totalCustomers

User: "Có bao nhiêu khách hàng mới tháng này?"
Tool: get_customer_analytics(period="THIS_MONTH")
→ Returns newCustomers
```

### Customer Engagement
```
User: "Tỷ lệ giữ chân khách hàng?"
Tool: get_customer_analytics(period="THIS_MONTH")
→ Returns retentionRate

User: "Trung bình mỗi khách đặt bao nhiêu đơn?"
Tool: get_customer_analytics(period="THIS_MONTH")
→ Returns averageOrdersPerCustomer
```

### Active Customers
```
User: "Có bao nhiêu khách hàng đang hoạt động?"
Tool: get_customer_analytics(period="LAST_30_DAYS")
→ Returns activeCustomers (customers who made orders)
```

## 📅 Booking Queries

### Booking Counts
```
User: "Hôm nay có bao nhiêu lượt đặt bàn?"
Tool: get_booking_analytics(period="TODAY")
→ Returns todayBookings

User: "Tổng số booking tháng này?"
Tool: get_booking_analytics(period="THIS_MONTH")
→ Returns totalBookings
```

### Booking Status
```
User: "Có bao nhiêu booking đang chờ xác nhận?"
Tool: get_booking_analytics(period="TODAY")
→ Returns pendingBookings

User: "Bao nhiêu booking đã hoàn thành?"
Tool: get_booking_analytics(period="THIS_MONTH")
→ Returns completedBookings
```

### Booking Types
```
User: "Khách hàng đăng ký đặt bàn nhiều hay khách vãng lai?"
Tool: get_booking_analytics(period="THIS_MONTH")
→ Compare customerBookings vs guestBookings

User: "Tỷ lệ no-show thế nào?"
Tool: get_booking_analytics(period="LAST_30_DAYS")
→ Returns noShowRate
```

## 💡 Insights Queries

### General Insights
```
User: "Có nhận xét gì về tình hình kinh doanh?"
Tool: get_analytics_insights()

User: "Cho tôi vài insights"
Tool: get_analytics_insights()

User: "Có gì đáng chú ý không?"
Tool: get_analytics_insights()
```

### Recommendations
```
User: "Có gợi ý gì để cải thiện kinh doanh?"
Tool: get_analytics_insights()
→ Filter insights by type="recommendation"

User: "Nên làm gì để tăng doanh thu?"
Tool: get_analytics_insights()
→ Focus on recommendation category
```

### Problem Detection
```
User: "Có vấn đề gì cần quan tâm?"
Tool: get_analytics_insights()
→ Filter insights by type="negative"

User: "Điểm tốt và điểm chưa tốt"
Tool: get_analytics_insights()
→ Show positive and negative insights
```

## 🔀 Combined Queries

### Multi-Metric Analysis
```
User: "Phân tích toàn diện doanh thu và đơn hàng"
Agent:
1. get_revenue_analytics(period="THIS_MONTH")
2. get_order_analytics(period="THIS_MONTH")
3. Synthesize response

User: "So sánh hiệu suất tuần này vs tuần trước"
Agent:
1. get_analytics_summary(period="LAST_7_DAYS") for this week
2. Compare with previous period data
```

### Business Health Check
```
User: "Kiểm tra sức khỏe kinh doanh"
Agent:
1. get_analytics_summary(period="THIS_MONTH")
2. get_analytics_insights()
3. Provide comprehensive health report
```

## 📅 Advanced Time Period Queries

### Today vs Yesterday
```
User: "So sánh hôm nay với hôm qua"
Agent:
1. get_revenue_analytics(period="TODAY")
→ Uses growthRate and yesterdayRevenue
```

### Week over Week
```
User: "Tuần này so với tuần trước thế nào?"
Agent:
1. get_analytics_summary(period="LAST_7_DAYS")
2. Compare metrics
```

### Month over Month
```
User: "Tháng này vs tháng trước"
Agent:
1. get_analytics_summary(period="THIS_MONTH")
2. get_analytics_summary(period="LAST_MONTH")
3. Compare results
```

### Custom Range
```
User: "Từ Tết đến giờ doanh thu bao nhiêu?"
Agent:
1. Convert "Tết" to date
2. get_revenue_analytics(
    period="CUSTOM",
    start_date="2026-01-29T00:00:00",
    end_date="2026-04-08T23:59:59"
)
```

## 🎯 Scenario-Based Queries

### Morning Check-in
```
User: "Chào buổi sáng, tình hình hôm qua thế nào?"
Agent:
1. get_analytics_summary(period="YESTERDAY")
2. get_analytics_insights()
```

### Weekly Review
```
User: "Tổng kết tuần"
Agent:
1. get_analytics_summary(period="LAST_7_DAYS")
2. get_product_analytics(limit=5, period="LAST_7_DAYS")
3. get_analytics_insights()
```

### Monthly Report
```
User: "Báo cáo cuối tháng"
Agent:
1. get_analytics_summary(period="THIS_MONTH")
2. get_product_analytics(limit=10, period="THIS_MONTH")
3. get_customer_analytics(period="THIS_MONTH")
4. get_analytics_insights()
```

### Quick Status Check
```
User: "Status?"
Agent:
1. get_order_analytics(period="TODAY")
→ Show pending/processing orders

User: "Có việc gì cần làm?"
Agent:
1. get_order_analytics(period="TODAY")
2. get_booking_analytics(period="TODAY")
→ Show pending items
```

## 💬 Natural Language Variations

The AI Agent understands many variations:

### Revenue Variations
- "Doanh thu", "Tiền", "Bán được bao nhiêu", "Kiếm được bao nhiêu"
- "Hôm nay", "Tuần này", "Tháng này", "Năm nay"
- "Bao nhiêu", "Là gì", "Thế nào"

### Product Variations
- "Món bán chạy", "Best seller", "Top món", "Phổ biến"
- "Món nào", "Sản phẩm nào", "Đồ ăn nào"

### Order Variations
- "Đơn hàng", "Order", "Đơn"
- "Bao nhiêu đơn", "Có mấy đơn", "Số lượng đơn"
- "Đang chờ", "Pending", "Chưa xử lý"

## 🔧 Troubleshooting Queries

### When Data Seems Wrong
```
User: "Tại sao doanh thu thấp?"
Agent:
1. get_revenue_analytics(period="TODAY")
2. Compare with averageOrderValue
3. Check if it's an unusual day

User: "Số liệu này đúng không?"
Agent:
1. Re-fetch analytics
2. Show timestamp of data
3. Explain caching (5 minutes)
```

---

## 📝 Query Tips

1. **Be Specific**: Include time period for better results
   - ✅ "Doanh thu hôm nay"
   - ❌ "Doanh thu" (agent will default to THIS_MONTH)

2. **Use Natural Language**: The agent understands Vietnamese naturally
   - "Cho tôi xem tình hình kinh doanh"
   - "Nhà hàng hoạt động thế nào?"

3. **Ask Follow-ups**: The agent remembers context
   - User: "Doanh thu tháng này?"
   - Agent: "50 triệu VND"
   - User: "Còn tháng trước?"
   - Agent: (knows you're still talking about revenue)

4. **Combine Requests**: Ask multiple things at once
   - "Cho tôi xem doanh thu, đơn hàng và món bán chạy"

---

**Last Updated**: 2026-04-08
