"""
File log — registry table for the File Manager.
1 row per uploaded file with metadata + storage path.
"""
import os
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


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "filename": row[1],
        "file_type": row[2],
        "extension": row[3],
        "mime_type": row[4],
        "size_bytes": row[5],
        "description": row[6],
        "storage_path": row[7],
        "indexed": bool(row[8]),
        "chunk_count": row[9],
        "uploaded_by": row[10],
        "created_at": row[11],
    }


_SELECT_COLS = (
    "id, filename, file_type, extension, mime_type, size_bytes, description, "
    "storage_path, indexed, chunk_count, uploaded_by, created_at"
)


async def create_file(
    file_id: str,
    filename: str,
    file_type: str,
    extension: str,
    mime_type: str,
    size_bytes: int,
    storage_path: str,
    description: str | None = None,
    uploaded_by: str | None = None,
) -> None:
    """Insert a new file row in unindexed state."""
    def _sync():
        with _db_client() as client:
            client.execute(
                "INSERT INTO files (id, filename, file_type, extension, mime_type, "
                "size_bytes, description, storage_path, uploaded_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [file_id, filename, file_type, extension, mime_type,
                 size_bytes, description, storage_path, uploaded_by]
            )
        logger.info(f"FileLog: Registered file {file_id} ({filename})")

    await asyncio.to_thread(_sync)


async def mark_indexed(file_id: str, chunk_count: int) -> None:
    """Mark a file as indexed in Qdrant with its chunk count."""
    def _sync():
        with _db_client() as client:
            client.execute(
                "UPDATE files SET indexed = 1, chunk_count = ? WHERE id = ?",
                [chunk_count, file_id]
            )

    await asyncio.to_thread(_sync)


async def list_files(file_type: str | None = None, limit: int = 100) -> list[dict]:
    """List files, optionally filtered by file_type."""
    def _sync():
        with _db_client() as client:
            if file_type and file_type != "all":
                result = client.execute(
                    f"SELECT {_SELECT_COLS} FROM files WHERE file_type = ? "
                    f"ORDER BY created_at DESC LIMIT ?",
                    [file_type, limit]
                )
            else:
                result = client.execute(
                    f"SELECT {_SELECT_COLS} FROM files ORDER BY created_at DESC LIMIT ?",
                    [limit]
                )
            return [_row_to_dict(r) for r in result.rows]

    return await asyncio.to_thread(_sync)


async def get_file(file_id: str) -> dict | None:
    """Get a single file row by id."""
    def _sync():
        with _db_client() as client:
            result = client.execute(
                f"SELECT {_SELECT_COLS} FROM files WHERE id = ?",
                [file_id]
            )
            if not result.rows:
                return None
            return _row_to_dict(result.rows[0])

    return await asyncio.to_thread(_sync)


async def delete_file(file_id: str) -> None:
    """Delete a file row by id."""
    def _sync():
        with _db_client() as client:
            client.execute("DELETE FROM files WHERE id = ?", [file_id])
        logger.info(f"FileLog: Deleted file {file_id}")

    await asyncio.to_thread(_sync)


async def count_by_type() -> dict[str, int]:
    """Return total count grouped by file_type. Useful for FE filter chips."""
    def _sync():
        with _db_client() as client:
            result = client.execute(
                "SELECT file_type, COUNT(*) FROM files GROUP BY file_type"
            )
            counts = {row[0]: row[1] for row in result.rows}
            counts["all"] = sum(counts.values())
            return counts

    return await asyncio.to_thread(_sync)
