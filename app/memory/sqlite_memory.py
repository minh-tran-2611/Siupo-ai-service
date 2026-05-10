import os
import json
import asyncio
import libsql_client
from contextlib import contextmanager
from loguru import logger

TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")


def _get_turso_url():
    """Convert libsql:// URL to https:// for HTTP client."""
    url = TURSO_DATABASE_URL
    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://")
    return url


@contextmanager
def _db_client():
    """Context manager that creates and closes a libsql client."""
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


async def init_db():
    """Initialize database with required tables."""
    def _sync():
        with _db_client() as client:
            client.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      TEXT NOT NULL,
                    summary      TEXT NOT NULL,
                    entities     TEXT,
                    topics       TEXT,
                    raw_message  TEXT,
                    consolidated INTEGER DEFAULT 0,
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            client.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)")
            client.execute("CREATE INDEX IF NOT EXISTS idx_memories_topics ON memories(topics)")
            client.execute("""
                CREATE TABLE IF NOT EXISTS consolidated_memories (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    TEXT NOT NULL,
                    summary    TEXT NOT NULL,
                    topics     TEXT,
                    entities   TEXT,
                    period     TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            client.execute("CREATE INDEX IF NOT EXISTS idx_consolidated_user ON consolidated_memories(user_id)")

            # ── Agent task pipeline ───────────────────────────────────────────
            client.execute("""
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    id            TEXT PRIMARY KEY,
                    user_id       TEXT NOT NULL,
                    user_message  TEXT NOT NULL,
                    topic         TEXT,
                    is_task       INTEGER DEFAULT 1,
                    status        TEXT NOT NULL,
                    started_at    INTEGER NOT NULL,
                    ended_at      INTEGER,
                    duration_ms   INTEGER,
                    response      TEXT,
                    iterations    INTEGER DEFAULT 0,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            client.execute("CREATE INDEX IF NOT EXISTS idx_agent_tasks_started ON agent_tasks(started_at DESC)")
            client.execute("CREATE INDEX IF NOT EXISTS idx_agent_tasks_user ON agent_tasks(user_id)")
            client.execute("CREATE INDEX IF NOT EXISTS idx_agent_tasks_is_task ON agent_tasks(is_task)")

            client.execute("""
                CREATE TABLE IF NOT EXISTS agent_tool_calls (
                    id          TEXT PRIMARY KEY,
                    task_id     TEXT NOT NULL,
                    tool_name   TEXT NOT NULL,
                    duration_ms INTEGER,
                    ok          INTEGER DEFAULT 1,
                    started_at  INTEGER NOT NULL,
                    sequence    INTEGER DEFAULT 0
                )
            """)
            client.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_task ON agent_tool_calls(task_id)")

            # ── File Manager registry ─────────────────────────────────────────
            client.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id            TEXT PRIMARY KEY,
                    filename      TEXT NOT NULL,
                    file_type     TEXT NOT NULL,
                    extension     TEXT,
                    mime_type     TEXT,
                    size_bytes    INTEGER NOT NULL,
                    description   TEXT,
                    storage_path  TEXT NOT NULL,
                    indexed       INTEGER DEFAULT 0,
                    chunk_count   INTEGER DEFAULT 0,
                    uploaded_by   TEXT,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            client.execute("CREATE INDEX IF NOT EXISTS idx_files_created ON files(created_at DESC)")
            client.execute("CREATE INDEX IF NOT EXISTS idx_files_type ON files(file_type)")
        logger.info("Database initialized")

    await asyncio.to_thread(_sync)


async def save_memory(
    user_id: str,
    summary: str,
    entities: list[str],
    topics: list[str],
    raw_message: str
) -> int:
    """Save a memory entry to the database."""
    def _sync():
        with _db_client() as client:
            result = client.execute(
                "INSERT INTO memories (user_id, summary, entities, topics, raw_message) VALUES (?, ?, ?, ?, ?)",
                [user_id, summary, json.dumps(entities), json.dumps(topics), raw_message]
            )
            last_id = result.last_insert_rowid
            logger.info(f"Saved memory for user {user_id}, id={last_id}")
            return last_id

    return await asyncio.to_thread(_sync)


async def bulk_save_memories(user_id: str, raw_messages: list[str]) -> int:
    """Bulk insert raw_message rows for cache eviction flush.

    Each message becomes one row with empty summary/entities/topics — the
    consolidate agent extracts structure later from raw_message.
    """
    if not raw_messages:
        return 0

    def _sync():
        with _db_client() as client:
            for raw in raw_messages:
                client.execute(
                    "INSERT INTO memories (user_id, summary, entities, topics, raw_message) VALUES (?, ?, ?, ?, ?)",
                    [user_id, "", "[]", "[]", raw]
                )
            logger.info(f"Bulk-saved {len(raw_messages)} memories for user {user_id}")
            return len(raw_messages)

    return await asyncio.to_thread(_sync)


async def get_memories_by_user(
    user_id: str,
    limit: int = 20,
    before: str | None = None,
    only_unconsolidated: bool = False
) -> list[dict]:
    """Get recent memories for a user.

    Args:
        before: ISO timestamp string. Only return rows with created_at < before.
                Used to exclude current-session rows already covered by cache.
        only_unconsolidated: If True, filter to consolidated = 0 only.
    """
    def _sync():
        with _db_client() as client:
            sql = "SELECT id, summary, entities, topics, raw_message, created_at FROM memories WHERE user_id = ?"
            params: list = [user_id]
            if only_unconsolidated:
                sql += " AND consolidated = 0"
            if before is not None:
                sql += " AND created_at < ?"
                params.append(before)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            result = client.execute(sql, params)
            return [
                {
                    "id": row[0], "summary": row[1],
                    "entities": json.loads(row[2]) if row[2] else [],
                    "topics": json.loads(row[3]) if row[3] else [],
                    "raw_message": row[4], "created_at": row[5]
                }
                for row in result.rows
            ]

    return await asyncio.to_thread(_sync)


async def get_consolidated_memories_by_user(user_id: str, limit: int = 10) -> list[dict]:
    """Get consolidated memories for a user."""
    def _sync():
        with _db_client() as client:
            result = client.execute(
                "SELECT id, summary, entities, topics, period, created_at "
                "FROM consolidated_memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                [user_id, limit]
            )
            return [
                {
                    "id": row[0], "summary": row[1],
                    "entities": json.loads(row[2]) if row[2] else [],
                    "topics": json.loads(row[3]) if row[3] else [],
                    "period": row[4], "created_at": row[5]
                }
                for row in result.rows
            ]

    return await asyncio.to_thread(_sync)


async def get_unconsolidated_memories() -> dict[str, list[dict]]:
    """Get all unconsolidated memories grouped by user_id."""
    def _sync():
        with _db_client() as client:
            result = client.execute(
                "SELECT id, user_id, summary, entities, topics, raw_message, created_at "
                "FROM memories WHERE consolidated = 0 ORDER BY user_id, created_at"
            )
            grouped: dict[str, list[dict]] = {}
            for row in result.rows:
                uid = row[1]
                if uid not in grouped:
                    grouped[uid] = []
                grouped[uid].append({
                    "id": row[0], "summary": row[2],
                    "entities": json.loads(row[3]) if row[3] else [],
                    "topics": json.loads(row[4]) if row[4] else [],
                    "raw_message": row[5], "created_at": row[6]
                })
            return grouped

    return await asyncio.to_thread(_sync)


async def save_consolidated_memory(
    user_id: str,
    summary: str,
    entities: list[str],
    topics: list[str],
    period: str
) -> int:
    """Save a consolidated memory entry."""
    def _sync():
        with _db_client() as client:
            result = client.execute(
                "INSERT INTO consolidated_memories (user_id, summary, entities, topics, period) VALUES (?, ?, ?, ?, ?)",
                [user_id, summary, json.dumps(entities), json.dumps(topics), period]
            )
            last_id = result.last_insert_rowid
            logger.info(f"Saved consolidated memory for user {user_id}, id={last_id}")
            return last_id

    return await asyncio.to_thread(_sync)


async def mark_memories_as_consolidated(memory_ids: list[int]):
    """Mark memories as consolidated."""
    if not memory_ids:
        return

    def _sync():
        with _db_client() as client:
            placeholders = ",".join("?" * len(memory_ids))
            client.execute(
                f"UPDATE memories SET consolidated = 1 WHERE id IN ({placeholders})",
                memory_ids
            )
            logger.info(f"Marked {len(memory_ids)} memories as consolidated")

    await asyncio.to_thread(_sync)


async def search_memories_by_topics(user_id: str, topics: list[str], limit: int = 10) -> list[dict]:
    """Search memories by matching topics."""
    def _sync():
        with _db_client() as client:
            conditions = " OR ".join(["topics LIKE ?" for _ in topics])
            params = [user_id] + [f"%{topic}%" for topic in topics] + [limit]
            result = client.execute(
                f"SELECT id, summary, entities, topics, raw_message, created_at "
                f"FROM memories WHERE user_id = ? AND ({conditions}) ORDER BY created_at DESC LIMIT ?",
                params
            )
            return [
                {
                    "id": row[0], "summary": row[1],
                    "entities": json.loads(row[2]) if row[2] else [],
                    "topics": json.loads(row[3]) if row[3] else [],
                    "raw_message": row[4], "created_at": row[5]
                }
                for row in result.rows
            ]

    return await asyncio.to_thread(_sync)


async def get_all_memories_by_user(user_id: str) -> list[dict]:
    """Get ALL memories for a user (no limit), ordered by newest first."""
    def _sync():
        with _db_client() as client:
            result = client.execute(
                "SELECT id, summary, entities, topics, raw_message, created_at "
                "FROM memories WHERE user_id = ? ORDER BY created_at DESC",
                [user_id]
            )
            return [
                {
                    "id": row[0], "summary": row[1],
                    "entities": json.loads(row[2]) if row[2] else [],
                    "topics": json.loads(row[3]) if row[3] else [],
                    "raw_message": row[4], "created_at": row[5]
                }
                for row in result.rows
            ]

    return await asyncio.to_thread(_sync)


async def delete_memories_by_ids(memory_ids: list[int]):
    """Delete memories by their IDs (used after consolidation)."""
    if not memory_ids:
        return

    def _sync():
        with _db_client() as client:
            placeholders = ",".join("?" * len(memory_ids))
            client.execute(
                f"DELETE FROM memories WHERE id IN ({placeholders})",
                memory_ids
            )
            logger.info(f"Deleted {len(memory_ids)} memories after consolidation")

    await asyncio.to_thread(_sync)
