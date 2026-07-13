"""Durable per-URL state for conditional and incremental crawling."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.memory.sqlite_memory import _db_client


async def get_crawl_state(canonical_url: str) -> dict | None:
    def _sync():
        with _db_client() as client:
            result = client.execute(
                "SELECT canonical_url, document_id, raw_hash, etag, last_modified, "
                "last_status, last_error, consecutive_failures, last_crawled_at, last_changed_at "
                "FROM crawl_source_state WHERE canonical_url = ?",
                [canonical_url],
            )
            if not result.rows:
                return None
            row = result.rows[0]
            return {
                "canonical_url": row[0], "document_id": row[1], "raw_hash": row[2],
                "etag": row[3], "last_modified": row[4], "last_status": row[5],
                "last_error": row[6], "consecutive_failures": row[7] or 0,
                "last_crawled_at": row[8], "last_changed_at": row[9],
            }
    return await asyncio.to_thread(_sync)


async def save_crawl_state(
    *,
    canonical_url: str,
    document_id: str,
    raw_hash: str | None,
    etag: str | None,
    last_modified: str | None,
    status: str,
    error: str | None = None,
    changed: bool = False,
) -> None:
    now = datetime.now(timezone.utc).isoformat()

    def _sync():
        with _db_client() as client:
            previous = client.execute(
                "SELECT consecutive_failures, last_changed_at FROM crawl_source_state WHERE canonical_url = ?",
                [canonical_url],
            )
            failures = 0
            last_changed_at = now if changed else None
            if previous.rows:
                failures = int(previous.rows[0][0] or 0)
                if status == "failed":
                    failures += 1
                else:
                    failures = 0
                if not changed:
                    last_changed_at = previous.rows[0][1]
            elif status == "failed":
                failures = 1

            client.execute(
                "INSERT INTO crawl_source_state (canonical_url, document_id, raw_hash, etag, last_modified, "
                "last_status, last_error, consecutive_failures, last_crawled_at, last_changed_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(canonical_url) DO UPDATE SET document_id=excluded.document_id, "
                "raw_hash=excluded.raw_hash, etag=excluded.etag, last_modified=excluded.last_modified, "
                "last_status=excluded.last_status, last_error=excluded.last_error, "
                "consecutive_failures=excluded.consecutive_failures, last_crawled_at=excluded.last_crawled_at, "
                "last_changed_at=excluded.last_changed_at, updated_at=excluded.updated_at",
                [canonical_url, document_id, raw_hash, etag, last_modified, status, error,
                 failures, now, last_changed_at, now],
            )
    await asyncio.to_thread(_sync)
