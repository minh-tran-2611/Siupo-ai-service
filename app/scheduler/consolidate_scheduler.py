import os
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from app.agents.consolidate_agent import run_consolidate_agent

CONSOLIDATE_INTERVAL_HOURS = int(os.getenv("CONSOLIDATE_INTERVAL_HOURS", "24"))

scheduler = AsyncIOScheduler()


def _run_consolidate_sync():
    """Wrapper to run async consolidate agent in sync context."""
    asyncio.create_task(run_consolidate_agent())


def start_scheduler():
    """Start the consolidation scheduler."""
    scheduler.add_job(
        _run_consolidate_sync,
        "interval",
        hours=CONSOLIDATE_INTERVAL_HOURS,
        id="consolidate_agent_job",
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"Consolidate scheduler started with interval={CONSOLIDATE_INTERVAL_HOURS}h")


def stop_scheduler():
    """Stop the consolidation scheduler."""
    scheduler.shutdown(wait=False)
    logger.info("Consolidate scheduler stopped")
