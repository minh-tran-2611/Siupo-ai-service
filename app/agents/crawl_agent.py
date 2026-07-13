"""Incremental, deduplicated web crawl with a complete daily digest."""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup
from google.genai import types
from loguru import logger

from app.memory.crawl_state import get_crawl_state, save_crawl_state
from app.rag.retriever import (
    REGULATORY_DOMAINS,
    canonicalize_url,
    get_document_state,
    stable_document_id,
)
from app.service.crawl_config import get_crawl_urls
from app.service.rag_service import add_document
from app.utils.llm_utils import call_llm_with_retry, get_gemini_client


CRAWL_TIMEOUT = int(os.getenv("CRAWL_TIMEOUT_SECONDS", "20"))
CRAWL_CONCURRENCY = max(1, int(os.getenv("CRAWL_CONCURRENCY", "3")))
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Bangkok")

CRAWL_EXTRACT_PROMPT = """Bạn là chuyên gia phân tích thông tin cho nhà hàng SiuPo.

Đọc kỹ toàn bộ nội dung được cung cấp và chỉ giữ dữ kiện có thể kiểm chứng, có giá trị cho vận hành nhà hàng:
- quy định pháp luật, thuế, hóa đơn, an toàn thực phẩm;
- cảnh báo, rủi ro, thay đổi chính sách;
- giá nguyên liệu, xu hướng thị trường, đối thủ và hành vi khách hàng;
- hành động cụ thể SiuPo nên cân nhắc.

Yêu cầu:
1. Viết 200-450 từ tiếng Việt, nêu rõ dữ kiện, ngày/thời điểm nếu có và URL nguồn.
2. Phân biệt dữ kiện từ nguồn với suy luận; không bịa nội dung ngoài trang.
3. Nếu trang chỉ là điều hướng/quảng cáo hoặc không có thông tin liên quan, trả đúng chuỗi SKIP.
4. Không bỏ qua cảnh báo pháp lý/an toàn dù nội dung ngắn."""

DAILY_DIGEST_PROMPT = """Bạn là Daily Intelligence Agent của nhà hàng SiuPo.

Bạn nhận toàn bộ bản trích xuất từ các nguồn crawl trong ngày. Phải đọc TẤT CẢ các khối [SOURCE], không được chỉ chọn vài nguồn đầu.

Tạo bản tổng hợp có cấu trúc:
1. COVERAGE: liệt kê đủ từng nguồn đã đọc và kết luận một dòng (quan trọng / theo dõi / không có thay đổi đáng kể).
2. CRITICAL: pháp lý, ATTP, thuế, cảnh báo hoặc rủi ro cần hành động ngay.
3. IMPORTANT: biến động thị trường, nguyên liệu, hành vi khách, cơ hội đáng chú ý.
4. MONITOR: thông tin chưa đủ chắc chắn hoặc cần theo dõi thêm.
5. ACTIONS: hành động đề xuất, mức ưu tiên P0/P1/P2, người phụ trách gợi ý và thời hạn.
6. CONFLICTS/GAPS: nguồn mâu thuẫn, thiếu ngày xuất bản, hoặc dữ kiện cần xác minh.

Không bịa. Giữ URL cạnh từng phát hiện. Nếu không có phát hiện quan trọng, vẫn phải báo đã đọc đủ bao nhiêu nguồn."""


def _local_now() -> datetime:
    try:
        return datetime.now(ZoneInfo(APP_TIMEZONE))
    except Exception:
        return datetime.now(timezone.utc)


def _strip_html(raw: str) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()


def _raw_hash(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()


def _source_profile(url: str) -> dict:
    domain = urlsplit(url).netloc.lower()
    path = urlsplit(url).path.lower()
    regulatory = domain in REGULATORY_DOMAINS
    topic = "market"
    if any(term in domain + path for term in ("vfa", "sattp", "nafiq", "thuy", "an-toan", "antoan")):
        topic = "food_safety"
    elif any(term in domain + path for term in ("gdt", "thue", "hoa-don")):
        topic = "tax_invoice"
    elif any(term in domain + path for term in ("vanban", "vbpl", "phap-luat", "docid")):
        topic = "regulation"
    elif any(term in domain + path for term in ("dms", "congthuong")):
        topic = "trade_regulation"
    elif any(term in domain for term in ("ipos", "brandsvietnam", "vietcetera")):
        topic = "industry_trend"
    return {
        "source_type": "regulatory" if regulatory else "market",
        "topic": topic,
        "authority_level": 5 if regulatory else 3,
    }


async def _fetch_page(client: httpx.AsyncClient, url: str, state: dict | None) -> dict:
    headers = {}
    if state and state.get("etag"):
        headers["If-None-Match"] = state["etag"]
    if state and state.get("last_modified"):
        headers["If-Modified-Since"] = state["last_modified"]
    try:
        response = await client.get(url, timeout=CRAWL_TIMEOUT, follow_redirects=True, headers=headers)
        if response.status_code == 304:
            return {"status": "not_modified", "etag": state.get("etag"), "last_modified": state.get("last_modified")}
        response.raise_for_status()
        return {
            "status": "ok",
            "text": response.text,
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
            "final_url": str(response.url),
        }
    except Exception as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}


async def _process_source(client: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        canonical_url = canonicalize_url(url)
        profile = _source_profile(canonical_url)
        document_id = stable_document_id(profile["source_type"], canonical_url)
        state = await get_crawl_state(canonical_url)
        fetched = await _fetch_page(client, canonical_url, state)

        if fetched["status"] == "failed":
            await save_crawl_state(
                canonical_url=canonical_url, document_id=document_id,
                raw_hash=state.get("raw_hash") if state else None,
                etag=state.get("etag") if state else None,
                last_modified=state.get("last_modified") if state else None,
                status="failed", error=fetched["error"],
            )
            return {"url": canonical_url, "status": "failed", "error": fetched["error"], **profile}

        if fetched["status"] == "not_modified":
            document_state = await get_document_state(document_id)
            if not document_state:
                # Crawl state can outlive a rebuilt Qdrant collection. Re-fetch
                # without validators so a 304 can never create a silent gap.
                fetched = await _fetch_page(client, canonical_url, None)
            else:
                summary = str(document_state.get("daily_summary", ""))
                await save_crawl_state(
                    canonical_url=canonical_url, document_id=document_id,
                    raw_hash=state.get("raw_hash") if state else None,
                    etag=fetched.get("etag"), last_modified=fetched.get("last_modified"),
                    status="unchanged",
                )
                return {"url": canonical_url, "status": "unchanged", "summary": summary, "document_id": document_id, **profile}

        if fetched["status"] == "failed":
            await save_crawl_state(
                canonical_url=canonical_url, document_id=document_id,
                raw_hash=state.get("raw_hash") if state else None,
                etag=state.get("etag") if state else None,
                last_modified=state.get("last_modified") if state else None,
                status="failed", error=fetched["error"],
            )
            return {"url": canonical_url, "status": "failed", "error": fetched["error"], **profile}

        visible_text = _strip_html(fetched.get("text", ""))
        if len(visible_text) < 200:
            await save_crawl_state(
                canonical_url=canonical_url, document_id=document_id,
                raw_hash=_raw_hash(visible_text), etag=fetched.get("etag"),
                last_modified=fetched.get("last_modified"), status="irrelevant",
            )
            return {"url": canonical_url, "status": "irrelevant", "summary": "", **profile}

        # Keep the full cleaned page (within a generous safety ceiling) in RAG.
        # The LLM produces only the cheap daily relevance summary; user queries
        # can still retrieve precise passages that the summary did not mention.
        page_content = visible_text[: int(os.getenv("CRAWL_MAX_CONTENT_CHARS", "150000"))]
        digest = _raw_hash(page_content)
        if state and state.get("raw_hash") == digest:
            document_state = await get_document_state(document_id)
            if document_state:
                summary = str(document_state.get("daily_summary", ""))
                await save_crawl_state(
                    canonical_url=canonical_url, document_id=document_id, raw_hash=digest,
                    etag=fetched.get("etag"), last_modified=fetched.get("last_modified"),
                    status="unchanged",
                )
                return {"url": canonical_url, "status": "unchanged", "summary": summary, "document_id": document_id, **profile}

        gemini = get_gemini_client()
        try:
            response = await call_llm_with_retry(
                lambda: gemini.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"URL: {canonical_url}\n\nNội dung đầy đủ của trang:\n{page_content}",
                    config=types.GenerateContentConfig(system_instruction=CRAWL_EXTRACT_PROMPT, temperature=0.1),
                )
            )
            extracted = response.text.strip() if response.text else ""
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            await save_crawl_state(
                canonical_url=canonical_url, document_id=document_id,
                raw_hash=state.get("raw_hash") if state else None,
                etag=fetched.get("etag"), last_modified=fetched.get("last_modified"),
                status="failed", error=error,
            )
            return {"url": canonical_url, "status": "failed", "error": error, **profile}

        daily_summary = "" if not extracted or extracted.upper() == "SKIP" else extracted

        now = _local_now()
        domain = urlsplit(canonical_url).netloc
        title = f"{domain} · {profile['topic']}"
        indexable = (
            f"Nguồn: {canonical_url}\nNgày thu thập: {now.date().isoformat()}\n"
            f"Loại nguồn: {profile['source_type']}\nChủ đề: {profile['topic']}\n\n"
            f"{page_content}"
        )
        stored = await add_document(
            title=title,
            content=indexable,
            source_type=profile["source_type"],
            document_id=document_id,
            canonical_url=canonical_url,
            topic=profile["topic"],
            authority_level=profile["authority_level"],
            crawled_at=now.astimezone(timezone.utc).isoformat(),
            # URL documents are stable upserts, so they retain only the latest
            # version and do not need time-based deletion.
            expires_at=None,
            raw_hash=digest,
            metadata={"daily_summary": daily_summary},
        )
        await save_crawl_state(
            canonical_url=canonical_url, document_id=document_id, raw_hash=digest,
            etag=fetched.get("etag"), last_modified=fetched.get("last_modified"),
            status=stored["status"], changed=True,
        )
        return {
            "url": canonical_url,
            "status": stored["status"] if daily_summary else "irrelevant",
            "storage_status": stored["status"],
            "summary": daily_summary,
            "document_id": document_id, "chunks": stored["chunks"], **profile,
        }


async def _create_daily_digest(results: list[dict], today: str) -> dict:
    reviewed = [row for row in results if row.get("summary")]
    failures = [row for row in results if row.get("status") == "failed"]
    blocks = []
    for index, row in enumerate(results, 1):
        content = row.get("summary") or row.get("error") or "Không có nội dung liên quan đọc được từ URL này."
        blocks.append(
            f"[SOURCE {index}/{len(results)}]\nURL: {row['url']}\n"
            f"TYPE: {row['source_type']}\nTOPIC: {row['topic']}\nSTATUS: {row['status']}\n"
            f"CONTENT:\n{content}"
        )

    if not blocks:
        digest_text = f"DAILY DIGEST {today}\nKhông có nguồn nào cung cấp nội dung đọc được. Lỗi nguồn: {len(failures)}."
    else:
        client = get_gemini_client()
        response = await call_llm_with_retry(
            lambda: client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Ngày đánh giá: {today}\nSố nguồn cấu hình: {len(results)}\nSố nguồn có nội dung: {len(reviewed)}\n\n" + "\n\n".join(blocks),
                config=types.GenerateContentConfig(system_instruction=DAILY_DIGEST_PROMPT, temperature=0.15),
            )
        )
        digest_text = response.text.strip() if response.text else ""

    # Preserve every source extraction alongside the synthesized overview.
    # The scheduled reviewer therefore reads the complete daily evidence set,
    # while Qdrant still retains the much larger raw page text for user queries.
    source_appendix = "\n\n".join(blocks)
    full_digest = digest_text
    if source_appendix:
        full_digest += "\n\n---\nFULL SOURCE APPENDIX\n\n" + source_appendix

    document_id = stable_document_id("daily_digest", today)
    expires_at = (_local_now().astimezone(timezone.utc) + timedelta(days=180)).isoformat()
    stored = await add_document(
        title=f"Daily Intelligence Digest {today}",
        content=full_digest,
        source_type="daily_digest",
        document_id=document_id,
        topic="daily_review",
        authority_level=4,
        expires_at=expires_at,
        metadata={
            "source_count": len(results),
            "content_source_count": len(reviewed),
            "configured_source_count": len(results),
            "failed_source_count": len(failures),
        },
    )
    return {**stored, "content": full_digest, "source_count": len(results), "failed_sources": len(failures)}


async def run_crawl_agent() -> dict:
    now = _local_now()
    today = now.date().isoformat()
    urls = get_crawl_urls()
    logger.info(f"Crawl Agent: incremental crawl {today} sources={len(urls)} concurrency={CRAWL_CONCURRENCY}")
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SiuPoKnowledgeBot/2.0; +https://siupo.pro.vn)",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    }
    semaphore = asyncio.Semaphore(CRAWL_CONCURRENCY)
    async with httpx.AsyncClient(headers=headers) as client:
        results = await asyncio.gather(*(_process_source(client, url, semaphore) for url in urls))

    digest = await _create_daily_digest(results, today)
    changed = sum(row.get("storage_status", row.get("status")) in {"created", "updated"} for row in results)
    unchanged = sum(row.get("status") == "unchanged" for row in results)
    failed = sum(row.get("status") == "failed" for row in results)
    chunks = sum(int(row.get("chunks", 0) or 0) for row in results) + int(digest.get("chunks", 0) or 0)
    logger.info(f"Crawl Agent: done changed={changed} unchanged={unchanged} failed={failed} digest_sources={digest['source_count']}")
    return {
        "pages_crawled": len(results) - failed,
        "chunks_indexed": chunks,
        "sources_configured": len(urls),
        "sources_changed": changed,
        "sources_unchanged": unchanged,
        "sources_failed": failed,
        "digest_document_id": digest["document_id"],
        "digest_source_count": digest["source_count"],
    }
