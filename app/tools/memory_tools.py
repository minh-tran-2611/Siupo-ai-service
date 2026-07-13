import math
import re
import unicodedata

from loguru import logger

from app.memory.sqlite_memory import (
    count_consolidated_memories,
    get_consolidated_memories,
    get_memories,
)


_STOPWORDS = {
    "anh", "chi", "cho", "cua", "duoc", "hay", "hoi", "khong", "khi", "la",
    "lay", "mot", "nay", "neu", "nhung", "noi", "ten", "the", "thi", "thong",
    "tin", "toi", "trong", "tu", "va", "ve", "website",
}


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    tokens = set(re.findall(r"[\w._-]{3,}", normalized, flags=re.UNICODE))
    return {token for token in tokens if token not in _STOPWORDS}


def _matches(rows: list[dict], query: str) -> bool:
    query_tokens = _tokens(query)
    if not query_tokens:
        return bool(rows)
    for row in rows:
        searchable = " ".join([
            str(row.get("summary") or ""),
            str(row.get("raw_message") or ""),
            " ".join(map(str, row.get("entities") or [])),
            " ".join(map(str, row.get("topics") or [])),
            str(row.get("period") or ""),
        ])
        if query_tokens & _tokens(searchable):
            return True
    return False


def _third_windows(total: int) -> list[tuple[int, int, str]]:
    if total <= 0:
        return []
    size = max(1, math.ceil(total / 3))
    return [
        (0, min(size, total), "newest-third"),
        (size, min(size, max(0, total - size)), "middle-third"),
        (size * 2, max(0, total - size * 2), "oldest-third"),
    ]


async def remember(query: str) -> dict:
    """Retrieve relevant past conversation memory across all chat channels."""
    logger.info(f"Tool: remember(query={query})")

    raw_memories = await get_memories(
        limit=None,
        only_unconsolidated=True,
    )

    consolidated_matches: list[dict] = []
    total_consolidated = await count_consolidated_memories()
    scanned_windows = []
    for offset, limit, label in _third_windows(total_consolidated):
        if limit <= 0:
            continue
        rows = await get_consolidated_memories(limit=limit, offset=offset)
        scanned_windows.append({"window": label, "offset": offset, "limit": limit, "rows": len(rows)})
        if _matches(rows, query):
            consolidated_matches = rows
            break

    raw_results = []
    query_tokens = _tokens(query)
    for row in raw_memories:
        text = row.get("raw_message") or row.get("summary") or ""
        if not query_tokens or (query_tokens & _tokens(text)):
            raw_results.append({
                "id": row.get("id"),
                "created_at": row.get("created_at"),
                "content": text,
            })

    return {
        "query": query,
        "raw_memory_count": len(raw_memories),
        "raw_results": raw_results[:50],
        "raw_results_truncated": len(raw_results) > 50,
        "consolidated_total": total_consolidated,
        "consolidated_scanned_windows": scanned_windows,
        "consolidated_results": consolidated_matches,
    }
