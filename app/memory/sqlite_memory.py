import os
import json
import libsql_client
from datetime import datetime
from typing import Optional
from loguru import logger

TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")


def _get_turso_url():
    """Convert libsql:// URL to https:// for HTTP client."""
    url = TURSO_DATABASE_URL
    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://")
    return url


def _get_client():
    """Get libsql client for Turso."""
    if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
        return libsql_client.create_client_sync(
            url=_get_turso_url(),
            auth_token=TURSO_AUTH_TOKEN
        )
    else:
        # Fallback to local SQLite
        local_path = os.getenv("MEMORY_DB_PATH", "memory.db")
        return libsql_client.create_client_sync(url=f"file:{local_path}")


async def init_db():
    """Initialize database with required tables."""
    client = _get_client()
    try:
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
        logger.info("Database initialized")
    finally:
        client.close()


async def save_memory(
    user_id: str,
    summary: str,
    entities: list[str],
    topics: list[str],
    raw_message: str
) -> int:
    """Save a memory entry to the database."""
    client = _get_client()
    try:
        result = client.execute(
            """
            INSERT INTO memories (user_id, summary, entities, topics, raw_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            [user_id, summary, json.dumps(entities), json.dumps(topics), raw_message]
        )
        last_id = result.last_insert_rowid
        logger.info(f"Saved memory for user {user_id}, id={last_id}")
        return last_id
    finally:
        client.close()


async def get_memories_by_user(user_id: str, limit: int = 20) -> list[dict]:
    """Get recent memories for a user."""
    client = _get_client()
    try:
        result = client.execute(
            """
            SELECT id, summary, entities, topics, raw_message, created_at
            FROM memories
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [user_id, limit]
        )
        return [
            {
                "id": row[0],
                "summary": row[1],
                "entities": json.loads(row[2]) if row[2] else [],
                "topics": json.loads(row[3]) if row[3] else [],
                "raw_message": row[4],
                "created_at": row[5]
            }
            for row in result.rows
        ]
    finally:
        client.close()


async def get_consolidated_memories_by_user(user_id: str, limit: int = 10) -> list[dict]:
    """Get consolidated memories for a user."""
    client = _get_client()
    try:
        result = client.execute(
            """
            SELECT id, summary, entities, topics, period, created_at
            FROM consolidated_memories
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [user_id, limit]
        )
        return [
            {
                "id": row[0],
                "summary": row[1],
                "entities": json.loads(row[2]) if row[2] else [],
                "topics": json.loads(row[3]) if row[3] else [],
                "period": row[4],
                "created_at": row[5]
            }
            for row in result.rows
        ]
    finally:
        client.close()


async def get_unconsolidated_memories() -> dict[str, list[dict]]:
    """Get all unconsolidated memories grouped by user_id."""
    client = _get_client()
    try:
        result = client.execute(
            """
            SELECT id, user_id, summary, entities, topics, raw_message, created_at
            FROM memories
            WHERE consolidated = 0
            ORDER BY user_id, created_at
            """
        )

        grouped: dict[str, list[dict]] = {}
        for row in result.rows:
            user_id = row[1]
            if user_id not in grouped:
                grouped[user_id] = []
            grouped[user_id].append({
                "id": row[0],
                "summary": row[2],
                "entities": json.loads(row[3]) if row[3] else [],
                "topics": json.loads(row[4]) if row[4] else [],
                "raw_message": row[5],
                "created_at": row[6]
            })
        return grouped
    finally:
        client.close()


async def save_consolidated_memory(
    user_id: str,
    summary: str,
    entities: list[str],
    topics: list[str],
    period: str
) -> int:
    """Save a consolidated memory entry."""
    client = _get_client()
    try:
        result = client.execute(
            """
            INSERT INTO consolidated_memories (user_id, summary, entities, topics, period)
            VALUES (?, ?, ?, ?, ?)
            """,
            [user_id, summary, json.dumps(entities), json.dumps(topics), period]
        )
        last_id = result.last_insert_rowid
        logger.info(f"Saved consolidated memory for user {user_id}, id={last_id}")
        return last_id
    finally:
        client.close()


async def mark_memories_as_consolidated(memory_ids: list[int]):
    """Mark memories as consolidated."""
    if not memory_ids:
        return
    client = _get_client()
    try:
        placeholders = ",".join("?" * len(memory_ids))
        client.execute(
            f"UPDATE memories SET consolidated = 1 WHERE id IN ({placeholders})",
            memory_ids
        )
        logger.info(f"Marked {len(memory_ids)} memories as consolidated")
    finally:
        client.close()


async def search_memories_by_topics(user_id: str, topics: list[str], limit: int = 10) -> list[dict]:
    """Search memories by matching topics."""
    client = _get_client()
    try:
        # Build LIKE conditions for each topic
        conditions = " OR ".join(["topics LIKE ?" for _ in topics])
        params = [user_id] + [f"%{topic}%" for topic in topics] + [limit]

        result = client.execute(
            f"""
            SELECT id, summary, entities, topics, raw_message, created_at
            FROM memories
            WHERE user_id = ? AND ({conditions})
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params
        )
        return [
            {
                "id": row[0],
                "summary": row[1],
                "entities": json.loads(row[2]) if row[2] else [],
                "topics": json.loads(row[3]) if row[3] else [],
                "raw_message": row[4],
                "created_at": row[5]
            }
            for row in result.rows
        ]
    finally:
        client.close()


async def get_all_memories_by_user(user_id: str) -> list[dict]:
    """Get ALL memories for a user (no limit), ordered by newest first."""
    client = _get_client()
    try:
        result = client.execute(
            """
            SELECT id, summary, entities, topics, raw_message, created_at
            FROM memories
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            [user_id]
        )
        return [
            {
                "id": row[0],
                "summary": row[1],
                "entities": json.loads(row[2]) if row[2] else [],
                "topics": json.loads(row[3]) if row[3] else [],
                "raw_message": row[4],
                "created_at": row[5]
            }
            for row in result.rows
        ]
    finally:
        client.close()


async def delete_memories_by_ids(memory_ids: list[int]):
    """Delete memories by their IDs (used after consolidation)."""
    if not memory_ids:
        return
    client = _get_client()
    try:
        placeholders = ",".join("?" * len(memory_ids))
        client.execute(
            f"DELETE FROM memories WHERE id IN ({placeholders})",
            memory_ids
        )
        logger.info(f"Deleted {len(memory_ids)} memories after consolidation")
    finally:
        client.close()
