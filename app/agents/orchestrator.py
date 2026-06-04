import json
import time
from contextvars import ContextVar
from google.genai import types
from loguru import logger

from app.utils.prompt_builder import get_orchestrator_prompt
from app.utils.llm_utils import get_gemini_client, call_llm_with_retry
from app.tools.tool_declarations import ORCHESTRATOR_DECLARATIONS
from app.tools.search_tools import search_internet
from app.agents.management_agent import run_management_agent
from app.agents.analytics_agent import run_analytics_agent
from app.rag.retriever import retrieve_relevant_chunks
from app.tools.gmail_tools import send_email_notification
from app.memory.task_log import log_tool_call
from app.events.agent_event_bus import emit as emit_event
from app.events.edge_map import tool_to_edges

# Per-request task id used to attribute orchestrator-level tool calls.
current_task_id: ContextVar[str | None] = ContextVar("current_task_id", default=None)
# Sequence counter per request — incremented for each tool call within a task.
_tool_sequence: ContextVar[int] = ContextVar("_tool_sequence", default=0)


async def _search_documents(query: str) -> dict:
    """Search internal documents via RAG."""
    chunks = await retrieve_relevant_chunks(query, top_k=5)
    if not chunks:
        return {"results": [], "message": "Không tìm thấy tài liệu liên quan."}
    results = [
        {"title": chunk["title"], "content": chunk["content"]}
        for chunk in chunks
    ]
    return {"results": results}


# Meta-tool functions — maps tool names to actual execution
_orchestrator_tools = {
    "call_management_agent": run_management_agent,
    "call_analytics_agent": run_analytics_agent,
    "search_internet": search_internet,
    "search_documents": _search_documents,
    "send_email_notification": send_email_notification,
}


_META_TO_AGENT = {
    "call_management_agent": "management",
    "call_analytics_agent": "analytics",
}


async def _execute_tool(name: str, args: dict) -> str:
    """Execute an orchestrator tool (meta-tool or utility)."""
    logger.info(f"Orchestrator: Executing tool: {name}")
    started = time.time()
    ok = True
    task_id = current_task_id.get()
    edges = tool_to_edges(name, "")
    sub_agent_id = _META_TO_AGENT.get(name)

    emit_event(
        "tool.call.start",
        agent_id="orchestrator",
        tool_name=name,
        edges=edges,
        task_id=task_id,
    )
    if sub_agent_id:
        emit_event(
            "agent.invoke.start",
            agent_id=sub_agent_id,
            parent_agent_id="orchestrator",
            task_id=task_id,
        )

    try:
        func = _orchestrator_tools.get(name)
        if not func:
            ok = False
            return json.dumps({"error": f"Unknown tool: {name}"})

        # Meta-tools (sub-agents) take a single 'task' param and return a string
        if name in ("call_management_agent", "call_analytics_agent"):
            task = args.get("task", "")
            logger.info(f"Orchestrator: Delegating to {name} with task: {task[:100]}...")
            result = await func(task)
            return result  # Already a string from sub-agent
        else:
            # Regular tools return dicts
            result = await func(**args)
            return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as e:
        ok = False
        logger.error(f"Orchestrator: Tool execution error: {e}")
        return json.dumps({"error": str(e)})
    finally:
        duration_ms = int((time.time() - started) * 1000)
        if sub_agent_id:
            emit_event(
                "agent.invoke.end",
                agent_id=sub_agent_id,
                parent_agent_id="orchestrator",
                ok=ok,
                duration_ms=duration_ms,
                task_id=task_id,
            )
        emit_event(
            "tool.call.end",
            agent_id="orchestrator",
            tool_name=name,
            edges=edges,
            ok=ok,
            duration_ms=duration_ms,
            task_id=task_id,
        )

        # Log orchestrator-level tool call (fire-and-forget)
        if task_id:
            seq = _tool_sequence.get() + 1
            _tool_sequence.set(seq)
            try:
                await log_tool_call(task_id, name, duration_ms, ok, seq)
            except Exception as e:
                logger.error(f"Orchestrator: Failed to log tool call: {e}")


def _build_parts_from_message(msg: dict) -> list:
    """Build Gemini Parts from a cache message dict, including any image bytes."""
    parts: list = []
    content = msg.get("content", "")
    if content:
        parts.append(types.Part.from_text(text=content))
    for img in msg.get("images") or []:
        try:
            parts.append(types.Part.from_bytes(data=img["bytes"], mime_type=img["mime"]))
        except Exception as e:
            logger.warning(f"Orchestrator: skipping malformed image in history: {e}")
    if not parts:
        parts.append(types.Part.from_text(text=""))
    return parts


async def run_orchestrator(user_id: str, message: str, memory_context: str,
                           conversation_history: list,
                           current_images: list | None = None) -> tuple[str, int]:
    """
    Main orchestrator — routes user requests to the appropriate sub-agent.

    Args:
        user_id: User identifier
        message: Current user message text
        memory_context: Formatted long-term memory string
        conversation_history: List of previous messages [{role, content, images?}]
        current_images: Optional list of {bytes, mime, hint} for the current turn

    Returns:
        Tuple (final response text, number of LLM iterations).
    """
    logger.info(f"Orchestrator: Processing request from user {user_id}")

    # Build contents with conversation history
    contents = []

    # Add memory context as first context message
    if memory_context:
        context_prompt = f"[MEMORY CONTEXT]\n{memory_context}\n\n[CONVERSATION START]"
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=context_prompt)]))
        contents.append(types.Content(role="model", parts=[types.Part.from_text(
            text="Tôi đã nhận được thông tin từ bộ nhớ. Hãy tiếp tục cuộc hội thoại.")]))

    # Add previous conversation history (images carried as bytes if still in cache)
    for msg in conversation_history:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=_build_parts_from_message(msg)))

    # Add current user message — text + any inline images
    current_parts: list = [types.Part.from_text(text=message)]
    for img in current_images or []:
        try:
            current_parts.append(types.Part.from_bytes(data=img["bytes"], mime_type=img["mime"]))
        except Exception as e:
            logger.warning(f"Orchestrator: skipping malformed current image: {e}")
    contents.append(types.Content(role="user", parts=current_parts))

    # LLM config
    llm_config = types.GenerateContentConfig(
        system_instruction=get_orchestrator_prompt(),
        temperature=0.7,
        tools=ORCHESTRATOR_DECLARATIONS
    )

    client = get_gemini_client()

    # Initial LLM call
    response = await call_llm_with_retry(
        lambda: client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=llm_config
        )
    )

    # Tool execution loop (max 5 iterations — orchestrator shouldn't need many)
    max_iterations = 5
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # Check for function calls
        function_calls = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    function_calls.append(part.function_call)

        if not function_calls:
            break

        # Append assistant response to history
        contents.append(response.candidates[0].content)

        # Execute function calls (may include sub-agent calls)
        function_responses = []
        for fc in function_calls:
            result = await _execute_tool(fc.name, dict(fc.args))
            function_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result}
                )
            )
            logger.info(f"Orchestrator: Tool {fc.name} completed, result length: {len(result)} chars")

        # Append tool results
        contents.append(types.Content(role="user", parts=function_responses))

        # Continue conversation
        response = await call_llm_with_retry(
            lambda: client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=llm_config
            )
        )

    # Extract final text
    final_response = response.text if response.text else "Xin lỗi, tôi không thể xử lý yêu cầu này."
    logger.info(f"Orchestrator: Completed in {iteration} iterations, response: {len(final_response)} chars")

    return final_response, iteration
