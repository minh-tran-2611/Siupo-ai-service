from loguru import logger

from app.agents.ingest_agent import run_ingest_agent


async def ingest_memory(user_id: str, message: str, reply: str) -> None:
    """
    Ingest Agent: Process and store the conversation as structured memory.
    This runs AFTER LLM response in background.
    """
    logger.info(f"Memory Orchestrator: Ingesting memory for user {user_id}")
    try:
        # Ingest both user message and assistant reply
        full_conversation = f"User: {message}\nAssistant: {reply}"
        ingest_result = await run_ingest_agent(user_id, full_conversation)
        logger.info(f"Memory Orchestrator: Ingest complete - {ingest_result}")
    except Exception as e:
        logger.error(f"Memory Orchestrator: Ingest failed - {e}")
