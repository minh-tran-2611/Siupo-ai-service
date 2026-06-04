"""
Agents controller — exposes Task Pipeline data + live event stream to the FE.
"""
import asyncio
import json
import traceback
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from app.memory.task_log import get_recent_tasks, get_task_detail
from app.events.agent_event_bus import get_bus
from app.scheduler.consolidate_scheduler import trigger_consolidate_now

router = APIRouter()

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
