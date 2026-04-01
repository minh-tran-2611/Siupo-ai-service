import os
from google import genai
from google.genai import types
from loguru import logger

from app.memory.sqlite_memory import save_memory

PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
REGION = os.getenv("GOOGLE_REGION", "us-central1")

client = genai.Client(vertexai=True, project=PROJECT_ID, location=REGION)


INGEST_SYSTEM_PROMPT = """You are a memory processing agent for a restaurant management system.
Your task is to extract structured information from user messages.

For each message, you must output a JSON object with:
- summary: A concise summary of the message (1-2 sentences)
- entities: A list of named entities (product names, dates, amounts, user names, etc.)
- topics: A list of topic tags from: ["product", "order", "policy", "complaint", "banner", "category", "combo", "notification", "user", "general"]

Output ONLY the JSON object, no other text.

Example:
Input: "Tôi muốn thêm sản phẩm mới là Phở Bò giá 50k"
Output: {"summary": "Người dùng muốn thêm sản phẩm Phở Bò với giá 50.000đ", "entities": ["Phở Bò", "50000"], "topics": ["product"]}
"""


async def run_ingest_agent(user_id: str, message: str) -> dict:
    """
    Process a user message and extract structured memory.
    Returns the extracted memory data.
    """
    logger.info(f"Ingest Agent: Processing message for user {user_id}")

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=message,
        config=types.GenerateContentConfig(
            system_instruction=INGEST_SYSTEM_PROMPT,
            temperature=0.1
        )
    )

    # Parse the JSON response
    try:
        import json
        result_text = response.text.strip()
        # Remove markdown code block if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        memory_data = json.loads(result_text)

        # Save to database
        memory_id = await save_memory(
            user_id=user_id,
            summary=memory_data.get("summary", message[:100]),
            entities=memory_data.get("entities", []),
            topics=memory_data.get("topics", ["general"]),
            raw_message=message
        )

        logger.info(f"Ingest Agent: Saved memory id={memory_id} for user {user_id}")
        return {
            "memory_id": memory_id,
            "summary": memory_data.get("summary"),
            "entities": memory_data.get("entities"),
            "topics": memory_data.get("topics")
        }

    except Exception as e:
        logger.error(f"Ingest Agent: Failed to parse response: {e}")
        # Fallback: save raw message
        memory_id = await save_memory(
            user_id=user_id,
            summary=message[:100],
            entities=[],
            topics=["general"],
            raw_message=message
        )
        return {
            "memory_id": memory_id,
            "summary": message[:100],
            "entities": [],
            "topics": ["general"]
        }
