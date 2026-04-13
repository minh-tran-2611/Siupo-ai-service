"""
Analytics Agent — Business intelligence, insights, and recommendations.

This agent receives a task description from the Orchestrator, fetches
analytics data via tools, analyzes it, and provides insights with
actionable recommendations.

It runs in isolation with its own system prompt and tool set.
"""
import os
import json
import asyncio
import random
from google import genai
from google.genai import types
from loguru import logger

from app.utils.prompt_builder import get_analytics_prompt
from app.tools.tool_declarations import ANALYTICS_DECLARATIONS
from app.tools.tool_registry import get_tool_functions, ANALYTICS_TOOL_NAMES

PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
REGION = os.getenv("GOOGLE_REGION", "us-central1")

client = genai.Client(vertexai=True, project=PROJECT_ID, location=REGION)

# Tool functions for this agent
_tool_functions = get_tool_functions(ANALYTICS_TOOL_NAMES)


async def _execute_tool(name: str, args: dict) -> str:
    """Execute a tool function and return JSON result."""
    logger.info(f"AnalyticsAgent: Executing tool: {name} with args: {args}")
    try:
        func = _tool_functions.get(name)
        if not func:
            return json.dumps({"error": f"Unknown tool: {name}"})

        result = await func(**args)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"AnalyticsAgent: Tool execution error: {e}")
        return json.dumps({"error": str(e)})


async def _call_llm_with_retry(generate_coro_fn, max_retries: int = 3, base_delay: float = 1.0):
    """Call LLM with exponential backoff retry for rate limiting."""
    for attempt in range(max_retries):
        try:
            return await generate_coro_fn()
        except Exception as e:
            error_str = str(e)
            if ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str) and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"AnalyticsAgent: Rate limited, retrying in {delay:.2f}s (attempt {attempt + 1})")
                await asyncio.sleep(delay)
            else:
                raise


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

    # Initial LLM call
    response = await _call_llm_with_retry(
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
            result = await _execute_tool(fc.name, dict(fc.args))
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
        response = await _call_llm_with_retry(
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
