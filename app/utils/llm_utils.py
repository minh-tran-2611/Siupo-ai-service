"""
Shared LLM utilities — singleton client, retry logic, tool execution, JSON parsing.
Centralizes duplicated code that previously existed across all agent files.
"""
import os
import json
import re
import asyncio
import random
from google import genai
from loguru import logger

_gemini_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    """Return the shared Gemini client, creating it on first call (singleton)."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_PROJECT_ID"),
            location=os.getenv("GOOGLE_REGION", "us-central1")
        )
    return _gemini_client


async def call_llm_with_retry(generate_coro_fn, max_retries: int = 3, base_delay: float = 1.0):
    """Call an LLM coroutine with exponential backoff retry on rate limiting (429/RESOURCE_EXHAUSTED)."""
    for attempt in range(max_retries):
        try:
            return await generate_coro_fn()
        except Exception as e:
            error_str = str(e)
            if ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str) and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"LLM rate limited, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(delay)
            else:
                raise


async def execute_tool(tool_functions: dict, name: str, args: dict, label: str = "") -> str:
    """Execute a tool by name, returning a JSON-serialized result string."""
    prefix = f"[{label}] " if label else ""
    logger.info(f"{prefix}Executing tool: {name} with args: {args}")
    try:
        func = tool_functions.get(name)
        if not func:
            return json.dumps({"error": f"Unknown tool: {name}"})
        result = await func(**args)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"{prefix}Tool execution error [{name}]: {e}")
        return json.dumps({"error": str(e)})


def extract_json_from_llm(text: str):
    """
    Robustly extract a JSON value (object or array) from an LLM response.
    Handles plain JSON, markdown code blocks, and embedded JSON.
    Returns a dict or list depending on the LLM output.
    """
    text = text.strip()

    # Try 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try 2: extract from ```json ... ``` or ``` ... ```
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try 3: find first [...] or {...} block (arrays first since consolidate returns arrays)
    for pattern in (r'\[.*\]', r'\{.*\}'):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass

    raise ValueError(f"Cannot extract JSON from LLM response: {text[:200]}")
