"""
Analytics Agent — Business intelligence, insights, and recommendations.

This agent receives a task description from the Orchestrator, fetches
analytics data via tools, analyzes it, and provides insights with
actionable recommendations.

It runs in isolation with its own system prompt and tool set.
"""
import json
from google.genai import types
from loguru import logger

from app.utils.prompt_builder import get_analytics_prompt
from app.utils.llm_utils import get_gemini_client, call_llm_with_retry, execute_tool
from app.tools.tool_declarations import ANALYTICS_DECLARATIONS
from app.tools.tool_registry import get_tool_functions, ANALYTICS_TOOL_NAMES

# Tool functions for this agent
_tool_functions = get_tool_functions(ANALYTICS_TOOL_NAMES)


async def run_analytics_agent(task: str) -> str:
    """
    Execute a business analytics task.

    Args:
        task: Complete analytics task description from the orchestrator.
              May include time period, specific metrics, or general questions.

    Returns:
        Text result with analysis, insights, and recommendations.
    """
    logger.info(f"AnalyticsAgent: Received task: {task[:100]}...")

    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=task)])
    ]

    llm_config = types.GenerateContentConfig(
        system_instruction=get_analytics_prompt(),
        temperature=0.5,  # Slightly higher for creative insights
        tools=ANALYTICS_DECLARATIONS
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

    # Tool execution loop (max 8 iterations — analytics may need multiple data fetches)
    max_iterations = 8
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
            result = await execute_tool(_tool_functions, fc.name, dict(fc.args), label="AnalyticsAgent")
            function_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result}
                )
            )
            logger.info(f"AnalyticsAgent: Tool {fc.name} → {result[:200]}...")

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
    final_response = response.text if response.text else "Không thể hoàn thành phân tích."
    logger.info(f"AnalyticsAgent: Completed in {iteration} iterations, response: {len(final_response)} chars")

    return final_response
