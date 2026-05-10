"""
Consolidation agent — runs every 24h via the scheduler.

Reads RAW conversation messages from the memories table (flushed there from the
conversation cache on session eviction), extracts structured information, and
produces multiple consolidated summaries per user. Source rows are deleted on
success — consolidated_memories becomes the long-term truth.

This agent now does both the extraction and the consolidation that ingest_agent
used to do per-turn. Per-turn extraction was over-engineered for typical
restaurant-manager queries (short, transactional).
"""
from datetime import datetime
from google.genai import types
from loguru import logger

from app.utils.llm_utils import get_gemini_client, call_llm_with_retry, extract_json_from_llm
from app.memory.sqlite_memory import (
    get_unconsolidated_memories,
    save_consolidated_memory,
    delete_memories_by_ids,
)


CONSOLIDATE_SYSTEM_PROMPT = """Bạn là agent tổng hợp bộ nhớ cho hệ thống quản lý nhà hàng.

Đầu vào: danh sách các tin nhắn raw (User/Assistant) trong khoảng thời gian gần đây của một người dùng.

Nhiệm vụ:
1. Tìm các sự kiện, quyết định, sở thích, khiếu nại, thông tin khách hàng/sản phẩm/đơn hàng quan trọng
2. Tạo NHIỀU summary riêng — mỗi entity / topic quan trọng tạo một summary
3. GIỮ NGUYÊN số liệu cụ thể: tên sản phẩm, giá, ngày, tên khách, mã đơn

QUY TẮC:
- BỎ QUA: lời chào, xác nhận đơn giản (ok, vâng), filler ("tốt", "ổn")
- GIỮ: hành động cụ thể, yêu cầu, phàn nàn, sở thích, danh tính, số liệu
- Mỗi summary 1-2 câu, có giá trị tham chiếu lại sau

Output là MỘT MẢNG JSON các object, mỗi object có:
- summary: string — 1-2 câu cụ thể
- entities: list — tên, số, ngày quan trọng
- topics: list — chọn từ ["product", "order", "policy", "complaint", "banner", "category", "combo", "notification", "user", "preference", "general"]
- importance: "high" / "medium" / "low"

Ví dụ output:
[
  {"summary": "Khách Nguyễn Văn A thường đặt Phở Bò vào sáng thứ Bảy", "entities": ["Nguyễn Văn A", "Phở Bò"], "topics": ["order", "user"], "importance": "high"},
  {"summary": "Combo Gia Đình bán 150 phần, combo Lãng Mạn chỉ 12 phần", "entities": ["combo Gia Đình", "150", "combo Lãng Mạn", "12"], "topics": ["combo", "order"], "importance": "high"}
]

Chỉ output mảng JSON, không thêm text.
"""


async def run_consolidate_agent():
    """Run consolidation across all users with unconsolidated memories.

    Triggered by the scheduler every 24h. Creates multiple consolidated
    summaries per user and deletes source rows.
    """
    logger.info("Consolidate Agent: Starting consolidation run")

    grouped_memories = await get_unconsolidated_memories()

    if not grouped_memories:
        logger.info("Consolidate Agent: No unconsolidated memories found")
        return

    today = datetime.now().strftime("%Y-%m-%d")

    for user_id, memories in grouped_memories.items():
        logger.info(f"Consolidate Agent: Processing {len(memories)} memories for user {user_id}")

        # Build raw conversation text from raw_message rows
        memory_ids = [m["id"] for m in memories]
        lines = []
        for m in memories:
            raw = m.get("raw_message") or m.get("summary") or ""
            if raw.strip():
                lines.append(raw.strip())

        if not lines:
            logger.info(f"Consolidate Agent: No content to consolidate for user {user_id}, skipping")
            await delete_memories_by_ids(memory_ids)
            continue

        memory_text = "Tin nhắn cần tổng hợp:\n" + "\n".join(lines)

        # Call LLM to extract + consolidate
        client = get_gemini_client()
        try:
            response = await call_llm_with_retry(
                lambda: client.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=memory_text,
                    config=types.GenerateContentConfig(
                        system_instruction=CONSOLIDATE_SYSTEM_PROMPT,
                        temperature=0.1,
                    ),
                )
            )
            parsed = extract_json_from_llm(response.text)
            consolidated_list = parsed if isinstance(parsed, list) else [parsed]
        except Exception as e:
            logger.error(f"Consolidate Agent: Extraction failed for user {user_id}: {e}")
            continue

        # Save consolidated entries (skip "low" importance when many)
        saved_count = 0
        for entry in consolidated_list:
            if len(consolidated_list) > 10 and entry.get("importance") == "low":
                continue
            try:
                await save_consolidated_memory(
                    user_id=user_id,
                    summary=entry.get("summary", ""),
                    entities=entry.get("entities", []),
                    topics=entry.get("topics", []),
                    period=today,
                )
                saved_count += 1
            except Exception as e:
                logger.error(f"Consolidate Agent: Failed to save entry for user {user_id}: {e}")

        # Delete source rows on success
        try:
            await delete_memories_by_ids(memory_ids)
            logger.info(
                f"Consolidate Agent: User {user_id} — created {saved_count} summaries "
                f"from {len(memory_ids)} memories"
            )
        except Exception as e:
            logger.error(f"Consolidate Agent: Failed to delete source memories for user {user_id}: {e}")

    logger.info("Consolidate Agent: Consolidation run completed")
