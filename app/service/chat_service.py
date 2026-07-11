"""
Chat Service — Thin orchestration layer.

Flow (lazy-write strategy):
1. Fetch raw long-term memories from previous sessions only
2. Read current session from cache (cache is the truth for current session)
3. Add user turn to cache (NO Turso write per turn — flush happens on eviction)
4. Start a task row (Task Pipeline)
5. Run orchestrator with current images + cache history
6. Add assistant reply to cache
7. Background: describe_image to replace bytes with text in cache; classifier
"""
import asyncio
import time
from loguru import logger

from app.agents.orchestrator import run_orchestrator, current_task_id, current_user_id, _tool_sequence
from app.agents.image_describer import describe_image
from app.agents.topic_classifier import classify_message
from app.memory.sqlite_memory import (
    get_memories_by_user,
)
from app.memory.conversation_cache import (
    get_conversation,
    add_message,
    get_session_start,
    get_session_memory,
    set_session_memory,
    replace_images_with_description,
)
from app.memory.task_log import start_task, end_task, finalize_classification
from app.events.agent_event_bus import emit as emit_event
from app.tools.report_tools import created_files
from app.utils.llm_utils import is_resource_exhausted_error


def format_memory_context(memories: list[dict]) -> str:
    """Format memories into simple context string (no LLM needed)."""
    if not memories:
        return ""

    parts = []

    # Raw memories from previous sessions (raw_message is the truth) — all of them
    if memories:
        parts.append("\nHội thoại trước đây:")
        for m in memories:
            text = m.get("raw_message") or m.get("summary") or ""
            if text:
                parts.append(f"- {text}")

    return "\n".join(parts)


async def _build_memory_context(user_id: str, before_iso: str | None) -> tuple[str, int]:
    memories = await get_memories_by_user(
        user_id,
        limit=None,
        before=before_iso,
        only_unconsolidated=True,
    )
    return format_memory_context(memories), len(memories)


async def _classify_and_finalize(task_id: str, user_message: str, response: str):
    """Background task: run classifier and update is_task + topic on the row."""
    emit_event("worker.start", worker_id="topic_classifier", task_id=task_id)
    try:
        result = await classify_message(user_message, response)
        await finalize_classification(task_id, result["is_task"], result["topic"])
    except Exception as e:
        logger.error(f"Chat: Classifier finalize failed for task {task_id}: {e}")
    finally:
        emit_event("worker.end", worker_id="topic_classifier", task_id=task_id)


async def _describe_and_replace(user_id: str, turn_id: int, images: list[dict], hint: str, task_id: str | None = None):
    """Background: describe each image and replace bytes in cache with text.

    Runs concurrently for multiple images. Uses the first image's description
    (joined if several) for the replacement. Cache then frees the bytes.
    """
    emit_event("worker.start", worker_id="image_describer", task_id=task_id)
    try:
        descriptions = await asyncio.gather(*[
            describe_image(img["bytes"], img["mime"], hint=hint) for img in images
        ])
        joined = " | ".join(d for d in descriptions if d)
        if not joined:
            joined = "không thể mô tả ảnh"
        replace_images_with_description(user_id, turn_id, joined)
    except Exception as e:
        logger.error(f"Chat: image describe-and-replace failed: {e}")
    finally:
        emit_event("worker.end", worker_id="image_describer", task_id=task_id)


async def chat(user_id: str, message: str, images: list[dict] | None = None) -> dict:
    """
    Main chat function — coordinates memory, orchestrator, task log, and caching.

    Args:
        user_id: User identifier
        message: User text message
        images: Optional list of {bytes, mime} dicts for inline image attachments

    Returns:
        Dict with 'reply' (str) and 'files' (list of file metadata dicts).
    """
    images = images or []
    logger.info(
        f"Chat: Processing message from user {user_id}, "
        f"has_images={bool(images)}, count={len(images)}"
    )

    # Step 1: Determine session boundary BEFORE adding the new message
    # (so memories filter excludes anything written in this session by past flushes)
    session_start = get_session_start(user_id)

    # Step 2: Raw long-term memory - fetch ONCE per session, then reuse from cache.
    # Consolidated memory is retrieved on demand by the orchestrator's remember tool.
    # Raw memories are ~static within a session (session_start is fixed and nothing
    # flushes mid-session), so we only hit Turso on the first turn and store the
    # formatted block on the session for the rest of the conversation.
    memory_context = ""
    needs_long_term_memory = True
    cached_memory_context = get_session_memory(user_id) if needs_long_term_memory else None
    should_refresh_memory = needs_long_term_memory and cached_memory_context is None
    if should_refresh_memory:
        before_iso = session_start.isoformat(sep=" ") if session_start else None
        memory_context, raw_count = await _build_memory_context(
            user_id,
            before_iso,
        )

        # Counts only — the actual block is logged per-turn just before the
        # orchestrator call (see "Memory context fed to prompt" below).
        logger.info(
            f"Chat: Memory fetched from Turso for user {user_id} — "
            f"raw={raw_count}"
        )
    elif needs_long_term_memory:
        memory_context = cached_memory_context or ""
        logger.info(
            f"Chat: Reusing cached memory context for user {user_id} (no Turso fetch)"
        )
    else:
        logger.info(
            f"Chat: Skipping long-term memory prefetch for user {user_id}; remember tool handles past/memory queries"
        )

    # Step 3: Read current session history from cache (current session truth)
    conversation_history = get_conversation(user_id)

    # Step 4: Add user turn to cache (RAM only, with image bytes if any)
    user_turn_id = add_message(
        user_id,
        "user",
        message,
        images=images if images else None,
    )

    # Persist the long-term memory block on the (now-existing) session so the next
    # turn reuses it from RAM instead of re-querying Turso.
    if needs_long_term_memory:
        set_session_memory(user_id, memory_context)

    logger.info(
        f"Chat: Built context — history={len(conversation_history)} msgs, "
        f"memory={'yes' if memory_context else 'no'}, "
        f"session_start={session_start}"
    )

    # Step 5: Start a task row + bind ContextVar so orchestrator tool calls get logged
    task_id = await start_task(user_id, message)
    current_task_id.set(task_id)
    current_user_id.set(user_id)
    _tool_sequence.set(0)

    started_at = time.time()
    emit_event(
        "chat.start",
        task_id=task_id,
        user_id=user_id,
        has_images=bool(images),
    )

    # Step 6: Reset created_files tracker for this turn
    created_files.set([])

    # Log the exact long-term memory block fed into the prompt for THIS turn
    # (runs on every turn, including cache hits, so we always see what was gathered)
    if memory_context:
        logger.info(
            f"Chat: Memory context fed to prompt for user {user_id}:\n{memory_context}"
        )
    else:
        logger.info(f"Chat: Memory context fed to prompt for user {user_id}: <empty>")

    # Step 7: Delegate to Orchestrator Agent
    status = "completed"
    final_response = ""
    iterations = 0
    try:
        final_response, iterations = await run_orchestrator(
            user_id=user_id,
            message=message,
            memory_context=memory_context,
            conversation_history=conversation_history,
            current_images=images if images else None,
        )
    except Exception as e:
        status = "failed"
        final_response = f"Đã có lỗi xảy ra: {e}"
        if is_resource_exhausted_error(e):
            final_response = (
                "Gemini/Vertex AI đang bị giới hạn tài nguyên tạm thời (429). "
                "Hệ thống đã thử lại nhiều lần nhưng vẫn chưa có capacity. "
                "Bạn đợi khoảng 30-60 giây rồi gửi lại giúp tôi."
            )
        logger.error(f"Chat: Orchestrator failed for task {task_id}: {e}")
    finally:
        await end_task(task_id, status, final_response, iterations)
        emit_event(
            "chat.end",
            task_id=task_id,
            status=status,
            duration_ms=int((time.time() - started_at) * 1000),
        )

    logger.info(f"Chat: Final response length={len(final_response)}, task={task_id}")

    # Capture any files created during this turn
    turn_files = []
    try:
        turn_files = created_files.get()
    except LookupError:
        pass

    # Step 7: Save assistant response to cache
    add_message(user_id, "assistant", final_response)

    # Step 8: Background — describe images (replaces bytes with text in cache)
    if images:
        asyncio.create_task(_describe_and_replace(user_id, user_turn_id, images, message, task_id))

    # Step 9: Background — classify task type for analytics
    asyncio.create_task(_classify_and_finalize(task_id, message, final_response))
    logger.info("Chat: Background tasks scheduled")

    return {"reply": final_response, "files": turn_files}
