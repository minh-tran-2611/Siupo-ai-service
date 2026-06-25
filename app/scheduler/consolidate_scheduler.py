import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from app.agents.consolidate_agent import run_consolidate_agent
from app.agents.market_intel_agent import run_market_intel_agent
from app.agents.orchestrator import run_daily_review_orchestrator
from app.memory.conversation_cache import (
    cleanup_expired_with_flush,
    register_flush_callback,
)
from app.memory.sqlite_memory import bulk_save_memories
from app.events.agent_event_bus import emit as emit_event

CONSOLIDATE_INTERVAL_HOURS = int(os.getenv("CONSOLIDATE_INTERVAL_HOURS", "24"))
CACHE_CLEANUP_INTERVAL_MINUTES = int(os.getenv("CACHE_CLEANUP_INTERVAL_MINUTES", "5"))
MARKET_INTEL_HOUR = int(os.getenv("MARKET_INTEL_HOUR", "5"))
MARKET_INTEL_MINUTE = int(os.getenv("MARKET_INTEL_MINUTE", "30"))
DAILY_REVIEW_HOUR = int(os.getenv("DAILY_REVIEW_HOUR", "6"))
DAILY_REVIEW_MINUTE = int(os.getenv("DAILY_REVIEW_MINUTE", "0"))
CRAWL_INTERVAL_HOURS = int(os.getenv("CRAWL_INTERVAL_HOURS", "24"))

scheduler = AsyncIOScheduler()

# Shared crawl status — read by agents_controller GET /agents/crawl/status
crawl_status: dict = {
    "last_run": None,
    "status": "idle",
    "pages_crawled": 0,
    "chunks_indexed": 0,
    "error": None,
}


def update_crawl_status(**kwargs) -> None:
    crawl_status.update(kwargs)


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


async def _market_intel_with_emit():
    """Market intel crawl job wrapper."""
    emit_event("scheduler.fire", job_id="market_intel_job", phase="start")
    emit_event("agent.invoke.start", agent_id="market_intel")
    ok = True
    try:
        await run_market_intel_agent()
    except Exception:
        ok = False
        raise
    finally:
        emit_event("agent.invoke.end", agent_id="market_intel", ok=ok)
        emit_event("scheduler.fire", job_id="market_intel_job", phase="end")


async def _daily_review_with_emit():
    """Daily review orchestrator job wrapper."""
    emit_event("scheduler.fire", job_id="daily_review_job", phase="start")
    emit_event("agent.invoke.start", agent_id="daily_review")
    ok = True
    try:
        await run_daily_review_orchestrator()
    except Exception:
        ok = False
        raise
    finally:
        emit_event("agent.invoke.end", agent_id="daily_review", ok=ok)
        emit_event("scheduler.fire", job_id="daily_review_job", phase="end")


async def trigger_consolidate_now():
    """Run consolidation immediately (manual trigger from the UI)."""
    await _consolidate_with_emit()


async def trigger_market_intel_now():
    """Run market intel crawl immediately (manual trigger for testing)."""
    await _market_intel_with_emit()


async def trigger_daily_review_now():
    """Run daily review orchestrator immediately (manual trigger for testing)."""
    await _daily_review_with_emit()


async def _crawl_with_emit():
    """Crawl job wrapper — emits scheduler + agent.invoke events, updates crawl_status."""
    import datetime as _dt

    emit_event("scheduler.fire", job_id="crawl_agent_job", phase="start")
    emit_event("agent.invoke.start", agent_id="crawl_agent")
    update_crawl_status(status="running", error=None)
    ok = True
    pages = 0
    chunks = 0
    try:
        from app.agents.crawl_agent import run_crawl_agent
        result = await run_crawl_agent()
        pages = result.get("pages_crawled", 0) if isinstance(result, dict) else 0
        chunks = result.get("chunks_indexed", 0) if isinstance(result, dict) else 0
    except Exception:
        ok = False
        raise
    finally:
        update_crawl_status(
            status="completed" if ok else "failed",
            last_run=_dt.datetime.utcnow().isoformat() + "Z",
            pages_crawled=pages,
            chunks_indexed=chunks,
            error=None if ok else "Crawl thất bại — xem log server",
        )
        emit_event("agent.invoke.end", agent_id="crawl_agent", ok=ok)
        emit_event("scheduler.fire", job_id="crawl_agent_job", phase="end")


async def trigger_crawl_now():
    """Run crawl agent immediately (manual trigger from the UI)."""
    await _crawl_with_emit()


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
    """Start all scheduled jobs and register flush callback."""
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
    scheduler.add_job(
        _market_intel_with_emit,
        "cron",
        hour=MARKET_INTEL_HOUR,
        minute=MARKET_INTEL_MINUTE,
        id="market_intel_job",
        replace_existing=True,
    )
    scheduler.add_job(
        _daily_review_with_emit,
        "cron",
        hour=DAILY_REVIEW_HOUR,
        minute=DAILY_REVIEW_MINUTE,
        id="daily_review_job",
        replace_existing=True,
    )
    scheduler.add_job(
        _crawl_with_emit,
        "interval",
        hours=CRAWL_INTERVAL_HOURS,
        id="crawl_agent_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"Schedulers started — consolidate={CONSOLIDATE_INTERVAL_HOURS}h, "
        f"cache_cleanup={CACHE_CLEANUP_INTERVAL_MINUTES}m, "
        f"market_intel={MARKET_INTEL_HOUR:02d}:{MARKET_INTEL_MINUTE:02d}, "
        f"daily_review={DAILY_REVIEW_HOUR:02d}:{DAILY_REVIEW_MINUTE:02d}, "
        f"crawl={CRAWL_INTERVAL_HOURS}h"
    )


def stop_scheduler():
    """Stop the scheduler. Note: does NOT flush in-memory cache — use clear endpoint."""
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")
