"""
Topic Classifier — small LLM that runs after a chat turn finishes to decide:
1. Is this user message a "task" worth showing in the Task Pipeline?
2. What topic does it belong to?

Output is used by chat_service to call task_log.finalize_classification(...).
"""
from google.genai import types
from loguru import logger

from app.utils.llm_utils import get_gemini_client, call_llm_with_retry, extract_json_from_llm


CLASSIFIER_PROMPT = """Bạn là bộ phân loại message cho hệ thống AI quản lý nhà hàng.
Nhiệm vụ: với mỗi cặp (user message, AI response), trả về JSON {is_task, topic}.

is_task = TRUE nếu user yêu cầu agent THỰC HIỆN một việc:
  - Truy vấn dữ liệu (xem doanh thu, tìm sản phẩm/khách hàng/đơn hàng, list voucher, ...)
  - Thay đổi dữ liệu (tạo, sửa, xóa, cập nhật bất kỳ thực thể nào)
  - Phân tích / báo cáo (thống kê, đề xuất, insight)
  - Tra cứu tài liệu nội bộ (chính sách, FAQ, hướng dẫn)

is_task = FALSE nếu là:
  - Chào hỏi, cảm ơn, xác nhận ngắn ("hi", "ok", "rồi", "cảm ơn", "chào em")
  - Câu hỏi meta về bot ("em là ai", "em làm được gì")
  - Smalltalk không liên quan công việc

topic — CHỌN ĐÚNG MỘT trong danh sách:
  revenue          - doanh thu, báo cáo tài chính
  product_mgmt     - sản phẩm, danh mục, combo
  order_mgmt       - đơn hàng, trạng thái đơn
  customer         - khách hàng, VIP, feedback
  voucher          - mã giảm giá, khuyến mãi
  banner_content   - banner, ảnh, nội dung trang
  analytics        - phân tích, insight tổng quát
  knowledge        - tài liệu nội bộ, chính sách (RAG)
  external         - tìm kiếm internet
  other            - không thuộc nhóm trên / không phải task

OUTPUT: chỉ JSON, không markdown, không giải thích.
{"is_task": true|false, "topic": "..."}

VÍ DỤ:

Input: "User: Cho anh xem doanh thu tháng 4\\nAI: Doanh thu tháng 4: 125.6M VNĐ..."
Output: {"is_task": true, "topic": "revenue"}

Input: "User: chào em\\nAI: Chào anh!"
Output: {"is_task": false, "topic": "other"}

Input: "User: Tạo voucher giảm 20% HOLIDAY20\\nAI: Đã tạo voucher..."
Output: {"is_task": true, "topic": "voucher"}

Input: "User: chính sách hoàn tiền là gì?\\nAI: Theo chính sách..."
Output: {"is_task": true, "topic": "knowledge"}

Input: "User: em làm được gì?\\nAI: Em có thể giúp anh quản lý..."
Output: {"is_task": false, "topic": "other"}
"""


async def classify_message(user_message: str, response: str) -> dict:
    """
    Classify a chat turn. Returns {"is_task": bool, "topic": str}.
    Defaults to {is_task: false, topic: "other"} on any error.
    """
    payload = f"User: {user_message}\nAI: {response}"
    logger.info(f"Classifier: Classifying message ({len(user_message)} chars)")

    try:
        client = get_gemini_client()
        llm_response = await call_llm_with_retry(
            lambda: client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=payload,
                config=types.GenerateContentConfig(
                    system_instruction=CLASSIFIER_PROMPT,
                    temperature=0.1
                )
            )
        )
        data = extract_json_from_llm(llm_response.text)
        is_task = bool(data.get("is_task", False))
        topic = data.get("topic", "other")
        # Sanity-check topic against allowed enum
        valid_topics = {
            "revenue", "product_mgmt", "order_mgmt", "customer", "voucher",
            "banner_content", "analytics", "knowledge", "external", "other"
        }
        if topic not in valid_topics:
            topic = "other"
        logger.info(f"Classifier: is_task={is_task} topic={topic}")
        return {"is_task": is_task, "topic": topic}
    except Exception as e:
        logger.error(f"Classifier: Failed: {e}")
        return {"is_task": False, "topic": "other"}
