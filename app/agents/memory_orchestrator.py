from google.genai import types
from loguru import logger

from app.utils.llm_utils import get_gemini_client, call_llm_with_retry
from app.agents.ingest_agent import run_ingest_agent
from app.memory.sqlite_memory import save_memory

# Threshold: inputs longer than this trigger 2-step pipeline
LONG_INPUT_THRESHOLD = 300

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 1: Key Point Evaluator — lightweight LLM call
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EVALUATE_PROMPT = """From the following conversation, list 5-10 most important facts.
Rank by importance: identity > actions/requests > preferences > specific details.
Discard generic filler like "good teamwork", "highly responsible".

Output format — numbered list, most important first:
1. [fact]
2. [fact]
...

ONLY output the numbered list, nothing else."""


async def _evaluate_key_points(conversation: str) -> str | None:
    """
    Step 1: Lightweight LLM call to extract 5-10 key points from long input.
    Returns a numbered list string, or None if extraction fails.
    """
    try:
        client = get_gemini_client()
        response = await call_llm_with_retry(
            lambda: client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=conversation,
                config=types.GenerateContentConfig(
                    system_instruction=EVALUATE_PROMPT,
                    temperature=0.1,
                    max_output_tokens=300
                )
            )
        )
        key_points = response.text.strip() if response.text else None
        if key_points:
            logger.info(f"Memory Orchestrator: Extracted key points:\n{key_points}")
        return key_points
    except Exception as e:
        logger.error(f"Memory Orchestrator: Key point evaluation failed: {e}")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Trivial message filter — no LLM needed
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TRIVIAL_RESPONSES = {
    "greeting": {
        "patterns": ["xin chào", "chào", "hello", "hi", "hey", "chào bạn", "chào bot"],
        "output": {"summary": "Người dùng gửi lời chào.", "entities": [], "topics": ["general"]}
    },
    "confirm": {
        "patterns": ["ok", "okay", "oke", "ừ", "ờ", "được", "được rồi", "vâng", "dạ", "đồng ý",
                      "có", "rồi", "yes", "yeah", "yep", "sure"],
        "output": {"summary": "Người dùng xác nhận / đồng ý.", "entities": [], "topics": ["general"]}
    },
    "thanks": {
        "patterns": ["cảm ơn", "cám ơn", "thanks", "thank you", "tks", "thankss", "cảm ơn bạn",
                      "cảm ơn nha", "cảm ơn nhé"],
        "output": {"summary": "Người dùng cảm ơn.", "entities": [], "topics": ["general"]}
    },
    "farewell": {
        "patterns": ["bye", "tạm biệt", "goodbye", "bye bye", "hẹn gặp lại", "bái bai"],
        "output": {"summary": "Người dùng chào tạm biệt.", "entities": [], "topics": ["general"]}
    },
    "negative": {
        "patterns": ["không", "ko", "no", "nope", "thôi", "hủy", "bỏ", "không cần",
                      "thôi khỏi", "hủy đi"],
        "output": {"summary": "Người dùng từ chối / hủy yêu cầu.", "entities": [], "topics": ["general"]}
    }
}


def _match_trivial(message: str) -> dict | None:
    """Check if message matches a trivial pattern. Returns predefined output or None."""
    msg = message.strip().lower()
    for category, data in TRIVIAL_RESPONSES.items():
        if msg in data["patterns"]:
            return data["output"]
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main orchestrator — 3-tier routing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def ingest_memory(user_id: str, message: str, reply: str) -> None:
    """
    Brain-inspired memory pipeline with 3-tier routing:

    1. TRIVIAL (exact match)   → predefined output, 0 LLM calls
    2. SHORT (<300 chars)      → direct to ingest, 1 LLM call
    3. LONG (>300 chars)       → evaluate key points first, then ingest with guidance, 2 LLM calls

    This mimics human attention:
    - Quick scan: is this worth remembering? (trivial filter)
    - Short-term: encode directly (short messages)
    - Deep processing: extract important bits, then encode (long inputs)
    """
    logger.info(f"Memory Orchestrator: Processing message for user {user_id} ({len(message)} chars)")

    try:
        # ── Tier 1: Trivial → predefined output, skip LLM ──
        trivial_output = _match_trivial(message)
        if trivial_output:
            full_conversation = f"User: {message}\nAssistant: {reply}"
            await save_memory(
                user_id=user_id,
                summary=trivial_output["summary"],
                entities=trivial_output["entities"],
                topics=trivial_output["topics"],
                raw_message=full_conversation
            )
            logger.info(f"Memory Orchestrator: Trivial message saved (0 LLM calls)")
            return

        full_conversation = f"User: {message}\nAssistant: {reply}"

        # ── Tier 2: Short conversation → direct ingest (1 LLM call) ──
        # Check full_conversation length (includes assistant reply, which can be very long)
        if len(full_conversation) <= LONG_INPUT_THRESHOLD:
            ingest_result = await run_ingest_agent(user_id, full_conversation)
            logger.info(f"Memory Orchestrator: Short message ingested (1 LLM call) - {ingest_result}")
            return

        # ── Tier 3: Long input → 2-step pipeline (2 LLM calls) ──
        logger.info(f"Memory Orchestrator: Long input detected ({len(message)} chars), running 2-step pipeline")

        # Step 1: Evaluate key points
        key_points = await _evaluate_key_points(full_conversation)

        # Step 2: Ingest with key points as guidance
        if key_points:
            guided_input = (
                f"[KEY POINTS — focus on these]\n{key_points}\n\n"
                f"[FULL CONVERSATION]\n{full_conversation}"
            )
        else:
            # Fallback: no key points extracted, send raw
            guided_input = full_conversation

        ingest_result = await run_ingest_agent(user_id, guided_input)
        logger.info(f"Memory Orchestrator: Long input ingested (2 LLM calls) - {ingest_result}")

    except Exception as e:
        logger.error(f"Memory Orchestrator: Ingest failed - {e}")
