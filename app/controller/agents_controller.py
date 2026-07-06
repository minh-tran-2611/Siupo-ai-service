"""
Agents controller — exposes Task Pipeline data + live event stream to the FE.
"""
import asyncio
import json
import traceback
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from loguru import logger

from app.memory.task_log import get_recent_tasks, get_task_detail
from app.events.agent_event_bus import get_bus
from app.service.crawl_config import get_crawl_urls, set_crawl_urls
from app.scheduler.consolidate_scheduler import (
    trigger_consolidate_now,
    trigger_market_intel_now,
    trigger_daily_review_now,
    trigger_crawl_now,
    crawl_status,
    scheduler,
)

router = APIRouter()


class CrawlConfigRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, description="Target URLs to crawl")

_KEEPALIVE_SECONDS = 15


@router.get("/agents/tasks")
async def list_tasks(
    limit: int = Query(50, ge=1, le=200),
    include_non_task: bool = Query(False)
):
    """
    Return recent agent tasks for the Task Pipeline UI.
    Each task includes its orchestrator-level tool list.

    Query params:
    - limit: max rows (default 50)
    - include_non_task: also return non-task chats (smalltalk) — default false
    """
    try:
        tasks = await get_recent_tasks(limit=limit, only_tasks=not include_non_task)
        return {"tasks": tasks, "count": len(tasks)}
    except Exception as e:
        logger.error(f"list_tasks error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/tasks/{task_id}")
async def get_task(task_id: str):
    """Return one task with full tool call history."""
    try:
        task = await get_task_detail(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_task error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/consolidate/run")
async def run_consolidate_manual():
    """Manually trigger a consolidation run (the 'Consolidate' node button).

    Runs inline and returns when done so the UI can show a definitive result.
    """
    try:
        await trigger_consolidate_now()
        return {"status": "ok", "message": "Consolidate hoàn tất"}
    except Exception as e:
        logger.error(f"run_consolidate_manual error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/market-intel/run")
async def run_market_intel_manual():
    """Manually trigger a market intel crawl (for testing)."""
    try:
        await trigger_market_intel_now()
        return {"status": "ok", "message": "Market intel crawl hoàn tất"}
    except Exception as e:
        logger.error(f"run_market_intel_manual error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/daily-review/run")
async def run_daily_review_manual():
    """Manually trigger a daily market review (for testing)."""
    try:
        await trigger_daily_review_now()
        return {"status": "ok", "message": "Daily review hoàn tất"}
    except Exception as e:
        logger.error(f"run_daily_review_manual error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/crawl/run")
async def run_crawl_manual():
    """Manually trigger a crawl run immediately (bypass schedule).

    Returns 409 if a crawl is already in progress.
    """
    if crawl_status.get("status") == "running":
        raise HTTPException(status_code=409, detail="Crawl đang chạy, vui lòng đợi hoàn tất.")
    try:
        asyncio.ensure_future(trigger_crawl_now())
        return {"status": "triggered", "message": "Crawl đã được trigger thủ công."}
    except Exception as e:
        logger.error(f"run_crawl_manual error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/crawl/status")
async def get_crawl_status():
    """Return last crawl run metadata for the FE Crawl Agent card."""
    job = scheduler.get_job("crawl_agent_job")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    return {**crawl_status, "next_run": next_run}


@router.get("/agents/crawl/config")
async def get_crawl_config():
    """Return the list of target URLs the crawl agent will fetch."""
    return {"urls": get_crawl_urls()}


@router.put("/agents/crawl/config")
async def update_crawl_config(body: CrawlConfigRequest):
    """Persist a new list of target URLs for the crawl agent."""
    try:
        saved = set_crawl_urls(body.urls)
        return {"status": "ok", "urls": saved, "message": f"Đã lưu {len(saved)} URLs"}
    except Exception as e:
        logger.error(f"update_crawl_config error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/state")
async def get_agents_state():
    """Snapshot of currently active agents/workers/jobs (in-memory, no DB hit).

    Used by the FE on initial mount and after SSE reconnect to reconcile state.
    """
    return get_bus().get_snapshot()


@router.get("/agents/events")
async def stream_agent_events(request: Request):
    """SSE stream of live agent telemetry events.

    Each chunk is a `data: {json}\\n\\n` frame; comments (`: ping`) are sent
    every 15s to defeat proxy idle timeouts.
    """
    bus = get_bus()

    async def event_gen():
        # Emit an initial snapshot frame so the consumer can reconcile state
        # without a separate /agents/state call.
        snap = {"type": "snapshot", **bus.get_snapshot()}
        yield f"data: {json.dumps(snap, ensure_ascii=False)}\n\n"

        sub = bus.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(sub.__anext__(), timeout=_KEEPALIVE_SECONDS)
                    yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive comment; clients ignore lines starting with ':'.
                    yield ": ping\n\n"
                except StopAsyncIteration:
                    break
        finally:
            await sub.aclose()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
