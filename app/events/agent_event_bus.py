"""
In-process pub-sub for live agent telemetry.

The bus is a singleton with N subscriber queues (one per SSE connection).
publish() fans out non-blocking — if a subscriber's queue is full, the event
for that subscriber is dropped (other subscribers still receive it). FE can
recover from drops by calling get_snapshot() after reconnect.

Snapshot is a lightweight aggregation kept in-memory: number of active chats
per agent, currently-running workers, currently-firing scheduler jobs. This
lets a freshly-mounted FE render the correct initial state without replaying
event history.
"""
import asyncio
import time
from collections import defaultdict
from typing import AsyncIterator
from loguru import logger

_QUEUE_MAX = 200


class AgentEventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        # Snapshot state — incremented/decremented as events flow through
        self._invoke_count: dict[str, int] = defaultdict(int)
        self._active_tasks: set[str] = set()
        self._active_workers: set[str] = set()
        self._active_jobs: set[str] = set()

    def publish(self, event: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop for this slow subscriber; others still get the event.
                pass

    async def subscribe(self) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._subscribers.add(q)
        try:
            while True:
                evt = await q.get()
                yield evt
        finally:
            self._subscribers.discard(q)

    def get_snapshot(self) -> dict:
        return {
            "agent_invokes": dict(self._invoke_count),
            "active_tasks": list(self._active_tasks),
            "active_workers": list(self._active_workers),
            "active_jobs": list(self._active_jobs),
            "subscribers": len(self._subscribers),
        }

    def _update_state(self, evt: dict) -> None:
        t = evt.get("type")
        if t == "chat.start":
            tid = evt.get("task_id")
            if tid:
                self._active_tasks.add(tid)
        elif t == "chat.end":
            tid = evt.get("task_id")
            if tid:
                self._active_tasks.discard(tid)
        elif t == "agent.invoke.start":
            aid = evt.get("agent_id")
            if aid:
                self._invoke_count[aid] += 1
        elif t == "agent.invoke.end":
            aid = evt.get("agent_id")
            if aid and self._invoke_count.get(aid, 0) > 0:
                self._invoke_count[aid] -= 1
        elif t == "worker.start":
            wid = evt.get("worker_id")
            if wid:
                self._active_workers.add(wid)
        elif t == "worker.end":
            wid = evt.get("worker_id")
            if wid:
                self._active_workers.discard(wid)
        elif t == "scheduler.fire":
            jid = evt.get("job_id")
            phase = evt.get("phase")
            if jid and phase == "start":
                self._active_jobs.add(jid)
            elif jid and phase == "end":
                self._active_jobs.discard(jid)


_bus = AgentEventBus()


def get_bus() -> AgentEventBus:
    return _bus


def emit(type: str, **payload) -> None:
    """Build event with timestamp and fan out. Safe to call from any context."""
    evt = {"type": type, "ts": int(time.time() * 1000), **payload}
    try:
        _bus._update_state(evt)
        _bus.publish(evt)
    except Exception as e:
        # Telemetry failures must never break callers.
        logger.warning(f"AgentEventBus.emit failed: {e}")
