"""
Management Agent — Handles restaurant CRUD operations.

This agent receives a task description from the Orchestrator and executes
it using restaurant management tools (products, categories, combos, banners,
notifications, users).

It runs in isolation with its own system prompt and tool set.
"""
from google.genai import types
from loguru import logger

from app.utils.prompt_builder import get_management_prompt
from app.utils.llm_utils import get_gemini_client, call_llm_with_retry, execute_tool
from app.tools.tool_declarations import MANAGEMENT_DECLARATIONS
from app.tools.tool_registry import get_tool_functions, MANAGEMENT_TOOL_NAMES

# Tool functions for this agent
_tool_functions = get_tool_functions(MANAGEMENT_TOOL_NAMES)


async def run_management_agent(task: str) -> str:
    """
    Execute a restaurant management task.

    Args:
        task: Complete task description from the orchestrator.

    Returns:
        Text result describing what was done.
    """
    logger.info(f"ManagementAgent: Received task: {task[:100]}...")

    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=task)])
    ]

    llm_config = types.GenerateContentConfig(
        system_instruction=get_management_prompt(),
        temperature=0.3,
        tools=MANAGEMENT_DECLARATIONS
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

    # Tool execution loop (max 10 iterations for complex multi-step tasks)
    max_iterations = 10
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

        # Execute all function calls
        function_responses = []
        for fc in function_calls:
            result = await execute_tool(_tool_functions, fc.name, dict(fc.args), label="ManagementAgent")
            function_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result}
                )
            )
            logger.info(f"ManagementAgent: Tool {fc.name} → {result[:200]}...")

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
    final_response = response.text if response.text else "Không thể hoàn thành yêu cầu quản lý."
    logger.info(f"ManagementAgent: Completed in {iteration} iterations, response: {len(final_response)} chars")

    return final_response
