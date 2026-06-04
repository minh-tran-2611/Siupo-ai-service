from google.genai import types
from loguru import logger

from app.utils.prompt_builder import get_analytics_prompt
from app.utils.llm_utils import get_gemini_client, call_llm_with_retry, execute_tool
from app.tools.tool_declarations import ANALYTICS_DECLARATIONS
from app.tools.tool_registry import get_tool_functions, ANALYTICS_TOOL_NAMES

_tool_functions = get_tool_functions(ANALYTICS_TOOL_NAMES)


async def run_analytics_agent(task: str) -> str:
    """
    Run a single declarative tool-call loop. The model decides how many tools
    to call and how to format the answer based on the task.
    """
    logger.info(f"AnalyticsAgent: Received task: {task[:100]}...")

    client = get_gemini_client()
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=task)])]

    config = types.GenerateContentConfig(
        system_instruction=get_analytics_prompt(),
        temperature=0.4,
        tools=ANALYTICS_DECLARATIONS,
    )

    response = await call_llm_with_retry(
        lambda: client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config,
        )
    )

    max_iterations = 8
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
            result = await execute_tool(_tool_functions, fc.name, dict(fc.args), label="AnalyticsAgent")
            function_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result},
                )
            )
            logger.info(f"AnalyticsAgent: Tool {fc.name} → {result[:200]}...")

        contents.append(types.Content(role="user", parts=function_responses))

        response = await call_llm_with_retry(
            lambda: client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=config,
            )
        )

    final_text = response.text if response.text else ""
    logger.info(f"AnalyticsAgent: Completed in {iteration} iterations ({len(final_text)} chars)")

    return final_text if final_text else "Không thể hoàn thành phân tích."
