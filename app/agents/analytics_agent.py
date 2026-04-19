"""
Analytics Agent — Business intelligence, insights, and recommendations.

This agent receives a task description from the Orchestrator, fetches
analytics data via tools, analyzes it, and provides insights with
actionable recommendations.

It runs in isolation with its own system prompt and tool set.
"""
from google.genai import types
from loguru import logger

from app.utils.prompt_builder import get_analytics_data_prompt, get_analytics_strategy_prompt
from app.utils.llm_utils import get_gemini_client, call_llm_with_retry, execute_tool
from app.tools.tool_declarations import ANALYTICS_DECLARATIONS
from app.tools.tool_registry import get_tool_functions, ANALYTICS_TOOL_NAMES

# Tool functions for this agent
_tool_functions = get_tool_functions(ANALYTICS_TOOL_NAMES)


async def run_analytics_agent(task: str) -> str:
    """
    Execute a business analytics task using a 2-phase pipeline:
      Phase 1 (Data Analyst): collect data via tools, calculate metrics, summarize
      Phase 2 (Strategy Advisor): analyze root causes, forecast, produce prioritized actions

    Args:
        task: Complete analytics task description from the orchestrator.

    Returns:
        Combined report: structured data summary + strategic action plan.
    """
    logger.info(f"AnalyticsAgent: Received task: {task[:100]}...")

    client = get_gemini_client()

    # ── Phase 1: Data Collection & Calculation ──────────────────────────────
    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=task)])
    ]

    data_config = types.GenerateContentConfig(
        system_instruction=get_analytics_data_prompt(),
        temperature=0.3,
        tools=ANALYTICS_DECLARATIONS
    )

    response = await call_llm_with_retry(
        lambda: client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=data_config
        )
    )

    max_iterations = 8
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        function_calls = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    function_calls.append(part.function_call)

        if not function_calls:
            break

        contents.append(response.candidates[0].content)

        function_responses = []
        for fc in function_calls:
            result = await execute_tool(_tool_functions, fc.name, dict(fc.args), label="AnalyticsAgent[P1]")
            function_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result}
                )
            )
            logger.info(f"AnalyticsAgent[P1]: Tool {fc.name} → {result[:200]}...")

        contents.append(types.Content(role="user", parts=function_responses))

        response = await call_llm_with_retry(
            lambda: client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=data_config
            )
        )

    data_report = response.text if response.text else ""
    logger.info(f"AnalyticsAgent[P1]: Data report done in {iteration} iterations ({len(data_report)} chars)")

    # ── Phase 2: Strategy Synthesis (no tools, pure reasoning) ──────────────
    strategy_input = (
        f"[BÁO CÁO SỐ LIỆU]\n{data_report}\n\n"
        f"[YÊU CẦU GỐC]\n{task}"
    )

    strategy_response = await call_llm_with_retry(
        lambda: client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=strategy_input,
            config=types.GenerateContentConfig(
                system_instruction=get_analytics_strategy_prompt(),
                temperature=0.4
            )
        )
    )

    strategy = strategy_response.text if strategy_response.text else ""
    logger.info(f"AnalyticsAgent[P2]: Strategy done ({len(strategy)} chars)")

    if not data_report and not strategy:
        return "Không thể hoàn thành phân tích."

    return f"{data_report}\n\n{strategy}" if strategy else data_report
