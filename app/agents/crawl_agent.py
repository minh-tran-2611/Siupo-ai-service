import os
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from google.genai import types
from loguru import logger

from app.utils.llm_utils import get_gemini_client, call_llm_with_retry
from app.service.rag_service import add_document
from app.service.crawl_config import get_crawl_urls

CRAWL_TIMEOUT = int(os.getenv("CRAWL_TIMEOUT_SECONDS", "20"))

CRAWL_EXTRACT_PROMPT = """Bạn là chuyên gia phân tích nội dung cho nhà hàng Siupo.

Nhiệm vụ: Từ nội dung HTML/text dưới đây, hãy trích xuất các thông tin có giá trị thực tiễn liên quan đến:
- Món ăn, thực đơn, giá cả
- Xu hướng ẩm thực, món phổ biến
- Đánh giá nhà hàng, phản hồi khách hàng
- Tin tức ngành F&B Việt Nam

Yêu cầu:
- Viết tóm tắt 200-400 từ bằng tiếng Việt
- Chỉ giữ thông tin có giá trị cho hoạt động nhà hàng
- Bỏ qua quảng cáo, nội dung không liên quan, boilerplate
- Nếu nội dung không có thông tin liên quan, hãy trả về chuỗi rỗng"""


def _strip_html(raw: str) -> str:
    """Parse HTML with BeautifulSoup and return clean visible text.

    Drops non-content tags (script, style, nav, header, footer, etc.) and
    collapses whitespace. BeautifulSoup handles malformed HTML far more
    robustly than a regex pass.
    """
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await client.get(url, timeout=CRAWL_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning(f"Crawl Agent: Failed to fetch '{url}': {e}")
        return None


async def run_crawl_agent() -> dict:
    """Crawl configured URLs, extract relevant content via LLM, store in Qdrant.

    Returns:
        {"pages_crawled": int, "chunks_indexed": int}
    """
    today = datetime.now().strftime("%Y-%m-%d")
    crawl_urls = get_crawl_urls()
    logger.info(f"Crawl Agent: Starting crawl for {today} — {len(crawl_urls)} URLs")

    gemini = get_gemini_client()
    pages_crawled = 0
    chunks_total = 0

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    }

    async with httpx.AsyncClient(headers=headers) as client:
        for url in crawl_urls:
            html = await _fetch_page(client, url)
            if not html:
                continue

            raw_text = _strip_html(html)
            if len(raw_text) < 200:
                logger.debug(f"Crawl Agent: Skipping '{url}' — too little text after stripping")
                continue

            # Truncate to ~8k chars to stay within LLM context
            snippet = raw_text[:8000]

            try:
                response = await call_llm_with_retry(
                    lambda: gemini.aio.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=f"URL: {url}\n\nNội dung:\n{snippet}",
                        config=types.GenerateContentConfig(
                            system_instruction=CRAWL_EXTRACT_PROMPT,
                            temperature=0.1,
                        ),
                    )
                )
                extracted = response.text.strip() if response.text else ""
            except Exception as e:
                logger.error(f"Crawl Agent: LLM extraction failed for '{url}': {e}")
                continue

            if not extracted:
                logger.debug(f"Crawl Agent: No relevant content at '{url}', skipping store")
                continue

            title = f"Crawl {url.split('/')[2]} ngày {today}"
            result = await add_document(title=title, content=extracted)
            chunks = result.get("chunks", 0) if isinstance(result, dict) else 0
            chunks_total += chunks
            pages_crawled += 1
            logger.info(f"Crawl Agent: Stored '{title}' — {chunks} chunks")

    logger.info(
        f"Crawl Agent: Done — {pages_crawled}/{len(crawl_urls)} pages crawled, "
        f"{chunks_total} chunks indexed"
    )
    return {"pages_crawled": pages_crawled, "chunks_indexed": chunks_total}
