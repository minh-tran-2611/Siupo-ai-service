import json
from datetime import datetime
from google.genai import types
from loguru import logger

from app.utils.llm_utils import get_gemini_client, extract_json_from_llm
from app.memory.sqlite_memory import (
    get_unconsolidated_memories,
    save_consolidated_memory,
    delete_memories_by_ids
)


CONSOLIDATE_SYSTEM_PROMPT = """You are a memory consolidation agent for a restaurant management system.
Given a list of memory entries for a single user, your task is to:
1. Find patterns and recurring themes
2. Create MULTIPLE consolidated summaries - one for each important entity or topic
3. PRESERVE specific details like product names, prices, dates, and customer names

IMPORTANT RULES:
- Create SEPARATE summaries for important entities (product names, prices, dates, customer names)
- Group related memories by topic but KEEP specific values
- Each summary should be actionable and contain concrete information

Output a JSON ARRAY of memory objects. Each object has:
- summary: A specific summary (1-2 sentences) with concrete details
- entities: List of important entities mentioned (names, numbers, dates)
- topics: List of relevant topics from ["product", "order", "policy", "complaint", "banner", "category", "combo", "notification", "user", "general"]
- importance: "high" for specific entities/numbers, "medium" for patterns, "low" for general info

Example output:
[
  {"summary": "Khách Nguyễn Văn A thường đặt Phở Bò vào buổi sáng", "entities": ["Nguyễn Văn A", "Phở Bò"], "topics": ["order", "user"], "importance": "high"},
  {"summary": "Sản phẩm Cơm Gà được thêm với giá 45.000đ ngày 15/03", "entities": ["Cơm Gà", "45000", "15/03"], "topics": ["product"], "importance": "high"},
  {"summary": "Người dùng thường hỏi về chính sách đổi trả và hoàn tiền", "entities": [], "topics": ["policy"], "importance": "medium"}
]

Output ONLY the JSON array, no other text.
"""


async def run_consolidate_agent():
    """
    Run the consolidation process for all users with unconsolidated memories.
    This should be triggered by the scheduler every 24 hours.

    NEW BEHAVIOR:
    - Creates MULTIPLE consolidated summaries (preserving important entities)
    - DELETES original memories after consolidation (not just marking)
    """
    logger.info("Consolidate Agent: Starting consolidation run")

    grouped_memories = await get_unconsolidated_memories()

    if not grouped_memories:
        logger.info("Consolidate Agent: No unconsolidated memories found")
        return

    today = datetime.now().strftime("%Y-%m-%d")

    for user_id, memories in grouped_memories.items():
        logger.info(f"Consolidate Agent: Processing {len(memories)} memories for user {user_id}")

        # Format memories for LLM
        memory_text = "Memories to consolidate:\n"
        memory_ids = []
        for m in memories:
            memory_text += f"- {m['summary']} (entities: {m['entities']}, topics: {m['topics']})\n"
            memory_ids.append(m['id'])

        # Call LLM to consolidate (async)
        client = get_gemini_client()
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=memory_text,
            config=types.GenerateContentConfig(
                system_instruction=CONSOLIDATE_SYSTEM_PROMPT,
                temperature=0.1
            )
        )

        try:
            parsed = extract_json_from_llm(response.text)
            consolidated_list = parsed if isinstance(parsed, list) else [parsed]

            # Save MULTIPLE consolidated memories
            saved_count = 0
            for consolidated_data in consolidated_list:
                # Skip low importance if there are many summaries
                if len(consolidated_list) > 10 and consolidated_data.get("importance") == "low":
                    continue

                await save_consolidated_memory(
                    user_id=user_id,
                    summary=consolidated_data.get("summary", ""),
                    entities=consolidated_data.get("entities", []),
                    topics=consolidated_data.get("topics", []),
                    period=today
                )
                saved_count += 1

            # DELETE source memories (not just mark)
            await delete_memories_by_ids(memory_ids)

            logger.info(f"Consolidate Agent: Created {saved_count} summaries from {len(memory_ids)} memories for user {user_id}")

        except Exception as e:
            logger.error(f"Consolidate Agent: Failed to consolidate for user {user_id}: {e}")

    logger.info("Consolidate Agent: Consolidation run completed")
