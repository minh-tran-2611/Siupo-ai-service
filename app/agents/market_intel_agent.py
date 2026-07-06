from datetime import datetime
from google.genai import types
from loguru import logger

from app.utils.llm_utils import get_gemini_client, call_llm_with_retry
from app.tools.search_tools import search_internet
from app.service.rag_service import add_document


MARKET_INTEL_QUERIES = [
    "giá nguyên liệu thực phẩm thịt rau củ Việt Nam hôm nay",
    "xu hướng món ăn nhà hàng F&B Việt Nam tháng này",
    "tin tức ngành nhà hàng ẩm thực Việt Nam mới nhất",
]

MARKET_INTEL_SYSTEM_PROMPT = """Bạn là chuyên gia phân tích thị trường F&B Việt Nam.

Nhiệm vụ: Tổng hợp kết quả tìm kiếm thành tài liệu kiến thức súc tích cho nhà hàng.

Viết một tài liệu 300-500 từ bao gồm:
1. Biến động giá nguyên liệu quan trọng (nếu có)
2. Xu hướng thị trường đáng chú ý
3. Tin tức ngành ảnh hưởng đến hoạt động nhà hàng

Chỉ giữ thông tin có giá trị thực tiễn. Bỏ qua nội dung không liên quan.
Viết bằng tiếng Việt, tự nhiên, dễ đọc, không dùng bullet list quá dày đặc."""


async def run_market_intel_agent() -> str:
    """Crawl market data, synthesize via LLM, store in Qdrant.

    Returns the synthesized text (used by scheduler for logging).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Market Intel Agent: Starting daily crawl for {today}")

    raw_results = []
    for query in MARKET_INTEL_QUERIES:
        try:
            result = await search_internet(query)
            snippets = [r.get("snippet", "") for r in result.get("results", []) if r.get("snippet")]
            if snippets:
                raw_results.append(f"[Truy vấn: {query}]\n" + "\n".join(snippets))
                logger.info(f"Market Intel Agent: Got {len(snippets)} snippets for '{query}'")
        except Exception as e:
            logger.warning(f"Market Intel Agent: Search failed for '{query}': {e}")

    if not raw_results:
        logger.warning("Market Intel Agent: No search results, skipping Qdrant store")
        return ""

    raw_text = "\n\n".join(raw_results)

    client = get_gemini_client()
    try:
        response = await call_llm_with_retry(
            lambda: client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Kết quả tìm kiếm thị trường ngày {today}:\n\n{raw_text}",
                config=types.GenerateContentConfig(
                    system_instruction=MARKET_INTEL_SYSTEM_PROMPT,
                    temperature=0.2,
                ),
            )
        )
        synthesized = response.text.strip()
    except Exception as e:
        logger.error(f"Market Intel Agent: LLM synthesis failed: {e}")
        return ""

    title = f"Thị trường F&B ngày {today}"
    await add_document(title=title, content=synthesized)
    logger.info(f"Market Intel Agent: Stored '{title}' to Qdrant")

    return synthesized
