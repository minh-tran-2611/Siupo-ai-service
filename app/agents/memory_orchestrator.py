from loguru import logger

from app.agents.ingest_agent import run_ingest_agent
from app.memory.sqlite_memory import save_memory


# Predefined outputs for trivial messages — skip LLM, save directly
TRIVIAL_RESPONSES = {
    # Chào hỏi
    "greeting": {
        "patterns": ["xin chào", "chào", "hello", "hi", "hey", "chào bạn", "chào bot"],
        "output": {
            "summary": "Người dùng gửi lời chào.",
            "entities": [],
            "topics": ["general"]
        }
    },
    # Xác nhận
    "confirm": {
        "patterns": ["ok", "okay", "oke", "ừ", "ờ", "được", "được rồi", "vâng", "dạ", "đồng ý",
                      "có", "rồi", "yes", "yeah", "yep", "sure"],
        "output": {
            "summary": "Người dùng xác nhận / đồng ý.",
            "entities": [],
            "topics": ["general"]
        }
    },
    # Cảm ơn
    "thanks": {
        "patterns": ["cảm ơn", "cám ơn", "thanks", "thank you", "tks", "thankss", "cảm ơn bạn",
                      "cảm ơn nha", "cảm ơn nhé"],
        "output": {
            "summary": "Người dùng cảm ơn.",
            "entities": [],
            "topics": ["general"]
        }
    },
    # Tạm biệt
    "farewell": {
        "patterns": ["bye", "tạm biệt", "goodbye", "bye bye", "hẹn gặp lại", "bái bai"],
        "output": {
            "summary": "Người dùng chào tạm biệt.",
            "entities": [],
            "topics": ["general"]
        }
    },
    # Phủ định
    "negative": {
        "patterns": ["không", "ko", "no", "nope", "thôi", "hủy", "bỏ", "không cần",
                      "thôi khỏi", "hủy đi"],
        "output": {
            "summary": "Người dùng từ chối / hủy yêu cầu.",
            "entities": [],
            "topics": ["general"]
        }
    }
}


def _match_trivial(message: str) -> dict | None:
    """Check if message matches a trivial pattern. Returns predefined output or None."""
    msg = message.strip().lower()

    # Skip very short messages or messages that exactly match patterns
    for category, data in TRIVIAL_RESPONSES.items():
        if msg in data["patterns"]:
            return data["output"]

    return None


async def ingest_memory(user_id: str, message: str, reply: str) -> None:
    """
    Ingest Agent: Process and store the conversation as structured memory.
    This runs AFTER LLM response in background.

    - Trivial messages (greetings, confirmations, farewells) → save predefined output, skip LLM.
    - Meaningful messages → call Ingest Agent (LLM) for full extraction.
    """
    logger.info(f"Memory Orchestrator: Ingesting memory for user {user_id}")
    try:
        # Check for trivial message first — save LLM cost
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
            logger.info(f"Memory Orchestrator: Trivial message saved without LLM for user {user_id}")
            return

        # Meaningful message → full LLM extraction
        full_conversation = f"User: {message}\nAssistant: {reply}"
        ingest_result = await run_ingest_agent(user_id, full_conversation)
        logger.info(f"Memory Orchestrator: Ingest complete - {ingest_result}")
    except Exception as e:
        logger.error(f"Memory Orchestrator: Ingest failed - {e}")
