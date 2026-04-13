"""
Chat Service — Thin orchestration layer.

Responsibilities:
1. Fetch long-term memories + conversation history
2. Delegate to Orchestrator Agent (which routes to sub-agents)
3. Cache conversation + schedule memory ingest in background

All tool logic, prompts, and LLM calls are handled by the agent layer.
"""
import asyncio
from loguru import logger

from app.agents.orchestrator import run_orchestrator
from app.agents.memory_orchestrator import ingest_memory
from app.memory.sqlite_memory import get_memories_by_user, get_consolidated_memories_by_user
from app.memory.conversation_cache import get_conversation, add_message, clear_conversation


def format_memory_context(memories: list[dict], consolidated: list[dict]) -> str:
    """Format memories into simple context string (no LLM needed)."""
    if not memories and not consolidated:
        return ""

    parts = []

    # Consolidated memories (important summaries)
    if consolidated:
        parts.append("Tóm tắt về người dùng:")
        for m in consolidated[:5]:  # Limit to 5
            parts.append(f"- {m['summary']}")

    # Recent memories
    if memories:
        parts.append("\nHội thoại gần đây:")
        for m in memories[:10]:  # Limit to 10 most recent
            parts.append(f"- {m['summary']}")

    return "\n".join(parts)


async def chat(user_id: str, message: str) -> str:
    """
    Main chat function — thin layer that coordinates memory, orchestrator, and caching.

    Flow:
    1. Fetch memories (long-term) and conversation history (short-term)
    2. Delegate to Orchestrator Agent (which routes to management/analytics sub-agents)
    3. Cache conversation + schedule memory ingest in background
    """
    logger.info(f"Chat: Processing message from user {user_id}")

    # Step 1: Fetch long-term memories
    memories, consolidated = await asyncio.gather(
        get_memories_by_user(user_id, limit=10),
        get_consolidated_memories_by_user(user_id, limit=5)
    )
    memory_context = format_memory_context(memories, consolidated)

    # Step 2: Get conversation history from cache (short-term context)
    conversation_history = get_conversation(user_id)

    # Save user message to cache immediately
    add_message(user_id, "user", message)

    logger.info(f"Chat: Built context with {len(conversation_history)} history messages, memory={'yes' if memory_context else 'no'}")

    # Step 3: Delegate to Orchestrator Agent
    final_response = await run_orchestrator(
        user_id=user_id,
        message=message,
        memory_context=memory_context,
        conversation_history=conversation_history
    )

    logger.info(f"Chat: Final response length={len(final_response)}")

    # Step 4: Save assistant response to conversation cache
    add_message(user_id, "assistant", final_response)

    # Step 5: Ingest Agent - store conversation in background (non-blocking)
    asyncio.create_task(ingest_memory(user_id, message, final_response))
    logger.info(f"Chat: Ingest task scheduled in background")

    return final_response
