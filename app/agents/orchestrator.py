"""
Orchestrator Agent — Main entry point that routes user requests to sub-agents.

Architecture:
- Receives user message + memory context from chat_service
- Uses LLM function calling to decide: management_agent / analytics_agent / direct response
- Delegates to the appropriate sub-agent
- Returns final response to user

Sub-agents are exposed as meta-tools via Gemini function calling.
"""
import json
import asyncio
import random
from google.genai import types
from loguru import logger

from app.utils.prompt_builder import get_orchestrator_prompt
from app.utils.llm_utils import get_gemini_client, call_llm_with_retry
from app.tools.tool_declarations import ORCHESTRATOR_DECLARATIONS
from app.tools.search_tools import search_internet
from app.agents.management_agent import run_management_agent
from app.agents.analytics_agent import run_analytics_agent
from app.rag.retriever import retrieve_relevant_chunks


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
}


async def _execute_tool(name: str, args: dict) -> str:
    """Execute an orchestrator tool (meta-tool or utility)."""
    logger.info(f"Orchestrator: Executing tool: {name}")
    try:
        func = _orchestrator_tools.get(name)
        if not func:
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
        logger.error(f"Orchestrator: Tool execution error: {e}")
        return json.dumps({"error": str(e)})


async def run_orchestrator(user_id: str, message: str, memory_context: str,
                           conversation_history: list) -> str:
    """
    Main orchestrator — routes user requests to the appropriate sub-agent.

    Args:
        user_id: User identifier
        message: Current user message
        memory_context: Formatted long-term memory string
        conversation_history: List of previous messages [{role, content}]

    Returns:
        Final response text for the user.
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

    # Add previous conversation history
    for msg in conversation_history:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))

    # Add current user message
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

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

    return final_response
