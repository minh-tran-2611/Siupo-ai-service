from google.genai import types
from loguru import logger

from app.utils.llm_utils import get_gemini_client, call_llm_with_retry


DESCRIBE_PROMPT = """Bạn là agent mô tả ảnh.
Nhiệm vụ: mô tả ngắn gọn nội dung ảnh bằng tiếng Việt, factual, ~30-60 từ.

Yêu cầu:
- Liệt kê đối tượng chính (người, vật, món ăn, văn bản nếu có)
- Mô tả hành động hoặc trạng thái nổi bật
- Nếu là menu/hoá đơn/biểu đồ: ghi lại các con số / tên món chính
- KHÔNG đoán cảm xúc, ý đồ, hay diễn giải xa rời ảnh
- KHÔNG mở đầu bằng "Đây là...", "Trong ảnh có..." — đi thẳng vào nội dung

Chỉ output mô tả, không thêm tiêu đề hay markdown."""


async def describe_image(image_bytes: bytes, mime_type: str, hint: str | None = None) -> str:
    """Generate a short Vietnamese description of an image.

    Args:
        image_bytes: raw image bytes
        mime_type: e.g. "image/png", "image/jpeg"
        hint: optional user message for context (helps focus the description)

    Returns:
        A single-line description string. Returns empty string on failure.
    """
    try:
        parts: list = [types.Part.from_bytes(data=image_bytes, mime_type=mime_type)]
        if hint:
            parts.append(types.Part.from_text(text=f"Ngữ cảnh người dùng hỏi: {hint[:200]}"))

        client = get_gemini_client()
        response = await call_llm_with_retry(
            lambda: client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    system_instruction=DESCRIBE_PROMPT,
                    temperature=0.2,
                    max_output_tokens=200,
                ),
            )
        )
        text = (response.text or "").strip()
        if not text:
            logger.warning("ImageDescriber: empty response from Gemini")
            return ""
        # Normalize: collapse newlines into spaces so it fits one line in cache
        text = " ".join(text.split())
        logger.info(f"ImageDescriber: described image ({len(image_bytes)} bytes) → {text[:80]}...")
        return text
    except Exception as e:
        logger.error(f"ImageDescriber: failed to describe image: {e}")
        return ""
