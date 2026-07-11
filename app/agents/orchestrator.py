import json
import re
import time
import unicodedata
from contextvars import ContextVar
from google.genai import types
from loguru import logger

from app.utils.prompt_builder import get_orchestrator_prompt
from app.utils.llm_utils import get_gemini_client, call_llm_with_retry
from app.tools.tool_declarations import ORCHESTRATOR_DECLARATIONS, DAILY_REVIEW_DECLARATIONS
from app.tools.search_tools import search_internet
from app.tools.memory_tools import remember
from app.agents.management_agent import run_management_agent
from app.agents.analytics_agent import run_analytics_agent
from app.rag.retriever import retrieve_relevant_chunks
from app.tools.gmail_tools import send_email_notification
from app.tools.zalo_notify_tools import send_zalo_notification
from app.memory.task_log import log_tool_call
from app.events.agent_event_bus import emit as emit_event
from app.events.edge_map import tool_to_edges
from app.utils.prompt_builder import get_daily_review_prompt

# Per-request task id used to attribute orchestrator-level tool calls.
current_task_id: ContextVar[str | None] = ContextVar("current_task_id", default=None)
current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)
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


async def _remember(query: str) -> dict:
    """Retrieve long-term memory for the current user."""
    user_id = current_user_id.get()
    if not user_id:
        return {"error": "No current user_id available for remember tool"}
    return await remember(user_id=user_id, query=query)


# Meta-tool functions — maps tool names to actual execution
_orchestrator_tools = {
    "call_management_agent": run_management_agent,
    "call_analytics_agent": run_analytics_agent,
    "search_internet": search_internet,
    "search_documents": _search_documents,
    "remember": _remember,
    "send_email_notification": send_email_notification,
    "send_zalo_notification": send_zalo_notification,
}

_daily_review_tools = {
    "search_documents": _search_documents,
    "send_zalo_notification": send_zalo_notification,
    "send_email_notification": send_email_notification,
}


_META_TO_AGENT = {
    "call_management_agent": "management",
    "call_analytics_agent": "analytics",
}

_URL_RE = re.compile(r"https?://[^\s<>()\"']+")


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _is_new_memory_note(message: str) -> bool:
    """True when user is providing new info to remember, not asking past memory."""
    text = _normalize_text(message)
    save_markers = ("ghi nho", "nho giup", "hay nho", "luu y", "luu lai", "nho rang")
    past_markers = (
        "lan truoc", "truoc do", "hoi truoc", "hom truoc", "da tung noi",
        "toi da noi", "qua khu", "lich su", "memory",
    )
    return any(marker in text for marker in save_markers) and not any(
        marker in text for marker in past_markers
    )


def _orchestrator_declarations_for_message(message: str):
    if not _is_new_memory_note(message):
        return ORCHESTRATOR_DECLARATIONS

    filtered_tools = []
    for tool in ORCHESTRATOR_DECLARATIONS:
        declarations = [
            declaration
            for declaration in (tool.function_declarations or [])
            if declaration.name != "remember"
        ]
        filtered_tools.append(types.Tool(function_declarations=declarations))
    logger.info("Orchestrator: remember tool disabled for new-memory note")
    return filtered_tools


def _extract_urls(text: str) -> list[str]:
    urls = []
    for match in _URL_RE.findall(text):
        url = match.rstrip(".,;:!?)]}")
        if url not in urls:
            urls.append(url)
    return urls[:3]


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

    for url in _extract_urls(message):
        result = await _execute_tool("search_internet", {"query": url})
        contents.append(types.Content(role="user", parts=[types.Part.from_text(
            text=(
                "[URL_FETCH_CONTEXT]\n"
                f"URL user provided: {url}\n"
                f"Fetch result: {result}\n\n"
                "Use this direct fetch result when answering. Do not claim the URL is internal, "
                "private, or unavailable if this result contains page content."
            )
        )]))

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
        tools=_orchestrator_declarations_for_message(message)
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


async def run_daily_review_orchestrator() -> None:
    """Scheduled daily review — retrieves market intel from Qdrant and sends notifications if warranted.

    Runs autonomously (no user, no conversation history). Uses a focused tool set:
    search_documents, send_zalo_notification, send_email_notification.
    """
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Daily Review Orchestrator: Starting review for {today}")

    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(
                text=f"Thực hiện kiểm tra thị trường hàng ngày cho ngày {today}."
            )]
        )
    ]

    llm_config = types.GenerateContentConfig(
        system_instruction=get_daily_review_prompt(),
        temperature=0.4,
        tools=DAILY_REVIEW_DECLARATIONS,
    )

    client = get_gemini_client()
    response = await call_llm_with_retry(
        lambda: client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=llm_config,
        )
    )

    max_iterations = 5
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        function_calls = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    function_calls.append(part.function_call)

        if not function_calls:
            break

        contents.append(response.candidates[0].content)

        function_responses = []
        for fc in function_calls:
            func = _daily_review_tools.get(fc.name)
            if not func:
                result = json.dumps({"error": f"Unknown tool: {fc.name}"})
            else:
                try:
                    result = await func(**dict(fc.args))
                    if not isinstance(result, str):
                        result = json.dumps(result, ensure_ascii=False, default=str)
                except Exception as e:
                    logger.error(f"Daily Review: Tool {fc.name} error: {e}")
                    result = json.dumps({"error": str(e)})
            logger.info(f"Daily Review: Tool {fc.name} completed")
            function_responses.append(
                types.Part.from_function_response(name=fc.name, response={"result": result})
            )

        contents.append(types.Content(role="user", parts=function_responses))

        response = await call_llm_with_retry(
            lambda: client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=llm_config,
            )
        )

    logger.info(f"Daily Review Orchestrator: Completed in {iteration} iterations")
