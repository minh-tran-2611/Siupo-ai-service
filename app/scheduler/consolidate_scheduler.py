import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from app.agents.consolidate_agent import run_consolidate_agent
from app.memory.conversation_cache import (
    cleanup_expired_with_flush,
    register_flush_callback,
)
from app.memory.sqlite_memory import bulk_save_memories
from app.events.agent_event_bus import emit as emit_event

CONSOLIDATE_INTERVAL_HOURS = int(os.getenv("CONSOLIDATE_INTERVAL_HOURS", "24"))
CACHE_CLEANUP_INTERVAL_MINUTES = int(os.getenv("CACHE_CLEANUP_INTERVAL_MINUTES", "5"))

scheduler = AsyncIOScheduler()


async def _flush_to_memories(user_id: str, raw_messages: list[str]) -> None:
    """Flush callback: persist evicted session messages to the memories table."""
    await bulk_save_memories(user_id, raw_messages)


async def _consolidate_with_emit():
    """Consolidate job wrapper — emits scheduler + agent.invoke events."""
    emit_event("scheduler.fire", job_id="consolidate_agent_job", phase="start")
    emit_event("agent.invoke.start", agent_id="consolidate")
    ok = True
    try:
        await run_consolidate_agent()
    except Exception:
        ok = False
        raise
    finally:
        emit_event("agent.invoke.end", agent_id="consolidate", ok=ok)
        emit_event("scheduler.fire", job_id="consolidate_agent_job", phase="end")


async def _cache_cleanup_with_emit():
    """Cache cleanup job wrapper — emits scheduler + worker events.

    The cache→turso flush edge is animated via worker.start; the FE hook
    maps worker_id="cache_cleanup" to that edge.
    """
    emit_event("scheduler.fire", job_id="cache_cleanup_job", phase="start")
    emit_event("worker.start", worker_id="cache_cleanup")
    ok = True
    try:
        await cleanup_expired_with_flush()
    except Exception:
        ok = False
        raise
    finally:
        emit_event("worker.end", worker_id="cache_cleanup", ok=ok)
        emit_event("scheduler.fire", job_id="cache_cleanup_job", phase="end")


def start_scheduler():
    """Start consolidation + cache cleanup schedulers, register flush callback."""
    register_flush_callback(_flush_to_memories)

    scheduler.add_job(
        _consolidate_with_emit,
        "interval",
        hours=CONSOLIDATE_INTERVAL_HOURS,
        id="consolidate_agent_job",
        replace_existing=True,
    )
    scheduler.add_job(
        _cache_cleanup_with_emit,
        "interval",
        minutes=CACHE_CLEANUP_INTERVAL_MINUTES,
        id="cache_cleanup_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"Schedulers started — consolidate={CONSOLIDATE_INTERVAL_HOURS}h, "
        f"cache_cleanup={CACHE_CLEANUP_INTERVAL_MINUTES}m"
    )


def stop_scheduler():
    """Stop the scheduler. Note: does NOT flush in-memory cache — use clear endpoint."""
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")
