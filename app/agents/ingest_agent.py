from google.genai import types
from loguru import logger

from app.utils.llm_utils import get_gemini_client, call_llm_with_retry, extract_json_from_llm
from app.memory.sqlite_memory import save_memory


INGEST_SYSTEM_PROMPT = """You are a memory extraction agent that mimics how the human brain filters information.
Your job: classify every piece of information by importance, then store ONLY what matters.

MEMORY TIERS (like human brain):

CORE — Identity & key context. Always remember.
  What: name, role, relationship, core identity, main responsibility.
  Example: "Trần Nhật Minh, quản lý nhà hàng" or "Khách VIP hay đặt bàn mỗi thứ 7"

IMPORTANT — Actionable facts the system needs later. Remember when relevant.
  What: specific requests, decisions, preferences, complaints, key skills, notable actions.
  Example: "thích ăn cay", "yêu cầu giảm 20% cho combo", "phàn nàn món Bún Bò nguội"

DETAIL — Specific but secondary. Store as searchable entities only.
  What: exact dates, URLs, project names, tool names, certifications, exact numbers.
  Example: "GPA 3.0/4.0", "github.com/xxx", "TOEIC 735"

NOISE — Generic, obvious, or filler. Discard completely.
  What: "good teamwork skills", "highly responsible", greetings, filler sentences.

OUTPUT FORMAT — Return ONLY a JSON object:
{
  "summary": "ONLY CORE + IMPORTANT facts. Max 3-5 sentences. Must be specific, never generic.",
  "entities": ["ONLY DETAIL-level items for search. Max 15-20 items. No generic phrases."],
  "topics": ["Choose from: product, order, policy, complaint, banner, category, combo, notification, user, preference, general"]
}

EXAMPLES:

Input: "User: Tôi là Trần Nhật Minh, quản lý của nhà hàng này. tôi làm việc cẩu thả, thích ăn chơi lười làm, tôi đẹp trai\\nAssistant: Chào anh Minh!"
Output: {"summary": "Trần Nhật Minh, quản lý nhà hàng. Tự nhận xét: cẩu thả, thích ăn chơi, lười làm, đẹp trai.", "entities": ["Trần Nhật Minh", "quản lý nhà hàng"], "topics": ["user", "preference"]}

Input: "User: Khách Nguyễn Văn An gọi phàn nàn Bún Bò nguội, phục vụ chậm, đòi hoàn tiền 50k\\nAssistant: Đã ghi nhận."
Output: {"summary": "Khách Nguyễn Văn An phàn nàn Bún Bò nguội, phục vụ chậm, đòi hoàn tiền 50.000đ.", "entities": ["Nguyễn Văn An", "Bún Bò", "50000"], "topics": ["complaint", "product"]}

Input: "User: [Long CV/document with education, skills, projects, certifications...]\\nAssistant: Đã nhận."
Output: {"summary": "Trần Nhật Minh, sinh viên CNPM tại HCMUTE. Kinh nghiệm: Backend dev (Spring Boot, FastAPI), từng intern AI Backend tại Hitek Solution, làm RAG system. Có dự án e-commerce và e-learning.", "entities": ["HCMUTE", "GPA 3.0/4.0", "Hitek Solution", "Oct 2025-Jan 2026", "Jewelry Store", "E-Learning App", "TOEIC 735/990"], "topics": ["user"]}

Input: "User: Doanh thu giảm 20%, combo Gia Đình bán 150 phần, combo Lãng Mạn chỉ 12 phần\\nAssistant: Phân tích ngay."
Output: {"summary": "Doanh thu giảm 20%. Combo Gia Đình bán chạy (150 phần). Combo Lãng Mạn bán kém (12 phần).", "entities": ["giảm 20%", "combo Gia Đình", "150 phần", "combo Lãng Mạn", "12 phần"], "topics": ["order", "combo"]}
"""


async def run_ingest_agent(user_id: str, message: str) -> dict:
    """
    Process a user message and extract structured memory using tiered importance.
    
    Memory tiers (brain-inspired):
    - CORE + IMPORTANT → stored in summary (3-5 sentences max)
    - DETAIL → stored in entities (for search, max 15-20)
    - NOISE → discarded completely
    """
    logger.info(f"Ingest Agent: Processing message for user {user_id}")

    client = get_gemini_client()
    response = await call_llm_with_retry(
        lambda: client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=message,
            config=types.GenerateContentConfig(
                system_instruction=INGEST_SYSTEM_PROMPT,
                temperature=0.1
            )
        )
    )

    # Parse the JSON response
    try:
        memory_data = extract_json_from_llm(response.text)

        # Save to database
        memory_id = await save_memory(
            user_id=user_id,
            summary=memory_data.get("summary", message[:200]),
            entities=memory_data.get("entities", []),
            topics=memory_data.get("topics", ["general"]),
            raw_message=message
        )

        logger.info(f"Ingest Agent: Saved memory id={memory_id} for user {user_id}")
        return {
            "memory_id": memory_id,
            "summary": memory_data.get("summary"),
            "entities": memory_data.get("entities"),
            "topics": memory_data.get("topics")
        }

    except Exception as e:
        logger.error(f"Ingest Agent: Failed to parse response: {e}")
        # Fallback: save raw message
        memory_id = await save_memory(
            user_id=user_id,
            summary=message[:200],
            entities=[],
            topics=["general"],
            raw_message=message
        )
        return {
            "memory_id": memory_id,
            "summary": message[:200],
            "entities": [],
            "topics": ["general"]
        }
