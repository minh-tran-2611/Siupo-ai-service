"""
Task log — persists agent task lifecycle and orchestrator-level tool calls.

Two tables:
- agent_tasks: 1 row per chat message (user_message = title)
- agent_tool_calls: 1 row per orchestrator-level tool invocation (call_management_agent,
  call_analytics_agent, search_documents, search_internet)
"""
import os
import time
import uuid
import asyncio
import libsql_client
from contextlib import contextmanager
from loguru import logger

TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")


def _get_turso_url():
    url = TURSO_DATABASE_URL
    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://")
    return url


@contextmanager
def _db_client():
    if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
        client = libsql_client.create_client_sync(
            url=_get_turso_url(),
            auth_token=TURSO_AUTH_TOKEN
        )
    else:
        local_path = os.getenv("MEMORY_DB_PATH", "memory.db")
        client = libsql_client.create_client_sync(url=f"file:{local_path}")
    try:
        yield client
    finally:
        client.close()


def _now_ms() -> int:
    return int(time.time() * 1000)


async def start_task(user_id: str, user_message: str) -> str:
    """Insert a new task row in 'processing' state. Returns task_id (uuid)."""
    task_id = str(uuid.uuid4())
    started = _now_ms()

    def _sync():
        with _db_client() as client:
            client.execute(
                "INSERT INTO agent_tasks (id, user_id, user_message, status, started_at) "
                "VALUES (?, ?, ?, 'processing', ?)",
                [task_id, user_id, user_message, started]
            )
        logger.info(f"TaskLog: Started task {task_id} for user {user_id}")

    await asyncio.to_thread(_sync)
    return task_id


async def end_task(task_id: str, status: str, response: str, iterations: int = 0):
    """Mark a task as completed/failed with final response + duration."""
    ended = _now_ms()

    def _sync():
        with _db_client() as client:
            client.execute(
                "UPDATE agent_tasks SET status = ?, response = ?, ended_at = ?, "
                "duration_ms = ended_at - started_at, iterations = ? WHERE id = ?",
                [status, response, ended, iterations, task_id]
            )
        logger.info(f"TaskLog: Ended task {task_id} status={status}")

    await asyncio.to_thread(_sync)


async def log_tool_call(task_id: str, tool_name: str, duration_ms: int, ok: bool, sequence: int):
    """Record one orchestrator-level tool invocation."""
    def _sync():
        with _db_client() as client:
            client.execute(
                "INSERT INTO agent_tool_calls (id, task_id, tool_name, duration_ms, ok, started_at, sequence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [str(uuid.uuid4()), task_id, tool_name, duration_ms, 1 if ok else 0, _now_ms(), sequence]
            )

    await asyncio.to_thread(_sync)


async def finalize_classification(task_id: str, is_task: bool, topic: str):
    """Set classifier output (is_task + topic) on an existing task row."""
    def _sync():
        with _db_client() as client:
            client.execute(
                "UPDATE agent_tasks SET is_task = ?, topic = ? WHERE id = ?",
                [1 if is_task else 0, topic, task_id]
            )
        logger.info(f"TaskLog: Classified task {task_id} is_task={is_task} topic={topic}")

    await asyncio.to_thread(_sync)


async def get_recent_tasks(limit: int = 50, only_tasks: bool = True) -> list[dict]:
    """
    Get the most recent tasks with their orchestrator-level tools attached.
    Sort: processing first, then by started_at desc.
    """
    def _sync():
        with _db_client() as client:
            where = "WHERE is_task = 1" if only_tasks else ""
            tasks_result = client.execute(
                f"SELECT id, user_id, user_message, topic, is_task, status, "
                f"started_at, ended_at, duration_ms, response, iterations "
                f"FROM agent_tasks {where} "
                f"ORDER BY (status = 'processing') DESC, started_at DESC LIMIT ?",
                [limit]
            )

            tasks = []
            task_ids = []
            for row in tasks_result.rows:
                tasks.append({
                    "id": row[0],
                    "user_id": row[1],
                    "user_message": row[2],
                    "topic": row[3],
                    "is_task": bool(row[4]),
                    "status": row[5],
                    "started_at": row[6],
                    "ended_at": row[7],
                    "duration_ms": row[8],
                    "response": row[9],
                    "iterations": row[10],
                    "tools": []
                })
                task_ids.append(row[0])

            if not task_ids:
                return tasks

            # Fetch all tool calls in one query
            placeholders = ",".join("?" * len(task_ids))
            tools_result = client.execute(
                f"SELECT task_id, tool_name FROM agent_tool_calls "
                f"WHERE task_id IN ({placeholders}) ORDER BY task_id, sequence",
                task_ids
            )
            by_task: dict[str, list[str]] = {}
            for row in tools_result.rows:
                by_task.setdefault(row[0], []).append(row[1])

            for t in tasks:
                t["tools"] = by_task.get(t["id"], [])

            return tasks

    return await asyncio.to_thread(_sync)


async def get_task_detail(task_id: str) -> dict | None:
    """Get a single task with full tool call history."""
    def _sync():
        with _db_client() as client:
            r = client.execute(
                "SELECT id, user_id, user_message, topic, is_task, status, started_at, "
                "ended_at, duration_ms, response, iterations FROM agent_tasks WHERE id = ?",
                [task_id]
            )
            if not r.rows:
                return None
            row = r.rows[0]
            task = {
                "id": row[0], "user_id": row[1], "user_message": row[2],
                "topic": row[3], "is_task": bool(row[4]), "status": row[5],
                "started_at": row[6], "ended_at": row[7], "duration_ms": row[8],
                "response": row[9], "iterations": row[10]
            }

            tools = client.execute(
                "SELECT tool_name, duration_ms, ok, sequence FROM agent_tool_calls "
                "WHERE task_id = ? ORDER BY sequence",
                [task_id]
            )
            task["tool_calls"] = [
                {"tool_name": tr[0], "duration_ms": tr[1], "ok": bool(tr[2]), "sequence": tr[3]}
                for tr in tools.rows
            ]
            return task

    return await asyncio.to_thread(_sync)
