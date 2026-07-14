"""Structured Qdrant knowledge store.

One physical collection is split into logical namespaces through mandatory
payload metadata. Documents are upserted by stable ``document_id`` so repeated
crawls replace stale chunks instead of growing the collection indefinitely.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.rag.embedder import get_embedding, get_embeddings_batch


QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "restaurant_knowledge"
EMBEDDING_DIM = 768

SOURCE_TYPES = {"internal", "regulatory", "market", "daily_digest"}
REGULATORY_DOMAINS = {
    "vanban.chinhphu.vn", "vbpl.vn", "gdt.gov.vn", "www.gdt.gov.vn",
    "vfa.gov.vn", "sattp.hochiminhcity.gov.vn", "cucthuy.gov.vn",
    "nafiqpm.mae.gov.vn", "dms.gov.vn", "tapchicongthuong.vn",
}
_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
    return _client


def canonicalize_url(url: str | None) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = parts.netloc.lower()
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_PARAMS))
    return urlunsplit((scheme, host, path, query, ""))


def stable_document_id(source_type: str, key: str) -> str:
    normalized = f"{source_type}:{key.strip().casefold()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_content(content: str) -> str:
    normalized = re.sub(r"\s+", " ", content).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload_indexes() -> dict[str, models.PayloadSchemaType]:
    return {
        "document_id": models.PayloadSchemaType.KEYWORD,
        "file_id": models.PayloadSchemaType.KEYWORD,
        "source_type": models.PayloadSchemaType.KEYWORD,
        "canonical_url": models.PayloadSchemaType.KEYWORD,
        "domain": models.PayloadSchemaType.KEYWORD,
        "topic": models.PayloadSchemaType.KEYWORD,
        "title_key": models.PayloadSchemaType.KEYWORD,
        "is_current": models.PayloadSchemaType.BOOL,
        "crawled_at": models.PayloadSchemaType.DATETIME,
        "expires_at": models.PayloadSchemaType.DATETIME,
    }


async def init_collection() -> None:
    client = get_qdrant_client()
    collections = client.get_collections().collections
    if not any(c.name == COLLECTION_NAME for c in collections):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE),
        )
        logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")

    for field, schema in _payload_indexes().items():
        try:
            client.create_payload_index(COLLECTION_NAME, field_name=field, field_schema=schema)
        except Exception as exc:
            # Qdrant returns an error when an identical index already exists.
            if "already exists" not in str(exc).lower():
                logger.warning(f"Payload index {field} could not be ensured: {exc}")

    migrated = await migrate_legacy_payloads()
    logger.info(f"Qdrant collection ready: {COLLECTION_NAME}; migrated={migrated}")


def _extract_url(content: str) -> str:
    match = re.search(r"(?:URL|Nguồn)\s*:\s*(https?://\S+)", content or "", flags=re.I)
    return canonicalize_url(match.group(1).rstrip(".,)")) if match else ""


def _infer_legacy_source(payload: dict) -> str:
    if payload.get("file_id"):
        return "internal"
    title = str(payload.get("title", ""))
    content = str(payload.get("content", ""))
    url = _extract_url(content)
    domain = urlsplit(url).netloc
    if domain in REGULATORY_DOMAINS:
        return "regulatory"
    if title.startswith("Crawl ") or title.startswith("Thị trường F&B"):
        return "market"
    return "internal"


def _infer_topic(source_type: str, title: str, canonical_url: str) -> str:
    text = _ascii(f"{title} {canonical_url}").replace("_", " ").replace("-", " ")
    if source_type == "internal":
        if any(term in text for term in ("chinh sach", "policy", "quy dinh", "so tay")):
            return "restaurant_policy"
        if any(term in text for term in ("analytics", "bao cao", "report", "phan tich")):
            return "analytics_report"
        return "uploaded_document"
    if any(term in text for term in ("vfa", "sattp", "nafiq", "thuy", "an toan", "antoan")):
        return "food_safety"
    if any(term in text for term in ("gdt", "thue", "hoa don")):
        return "tax_invoice"
    if any(term in text for term in ("vanban", "vbpl", "docid", "phap luat")):
        return "regulation"
    if any(term in text for term in ("ipos", "brandsvietnam", "vietcetera")):
        return "industry_trend"
    return "market"


async def migrate_legacy_payloads() -> int:
    """Backfill metadata on old points without changing vectors or content."""
    client = get_qdrant_client()
    offset = None
    migrated = 0
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            source_type = _infer_legacy_source(payload)
            canonical_url = _extract_url(str(payload.get("content", "")))
            key = payload.get("file_id") or canonical_url or str(payload.get("title", "untitled"))
            patch = {}
            if not payload.get("document_id") or not payload.get("source_type"):
                patch.update({
                    "document_id": stable_document_id(source_type, str(key)),
                    "source_type": source_type,
                    "canonical_url": canonical_url,
                    "domain": urlsplit(canonical_url).netloc if canonical_url else "",
                    "authority_level": 5 if source_type == "regulatory" else (4 if source_type == "internal" else 2),
                    "content_hash": hash_content(str(payload.get("content", ""))),
                    "is_current": True,
                })
            if not payload.get("title_key"):
                patch["title_key"] = _ascii(str(payload.get("title", ""))).strip()
            inferred_topic = _infer_topic(
                str(payload.get("source_type") or source_type),
                str(payload.get("title", "")),
                str(payload.get("canonical_url") or canonical_url),
            )
            current_topic = str(payload.get("topic") or "")
            generic_topics = {"", "legacy", "uploaded_document", "market"}
            if current_topic in generic_topics and inferred_topic != current_topic:
                patch["topic"] = inferred_topic
            if not patch:
                continue
            client.set_payload(COLLECTION_NAME, payload=patch, points=[point.id])
            migrated += 1
        if offset is None:
            break
    return migrated


def _must_filter(**values) -> models.Filter | None:
    conditions = []
    for key, value in values.items():
        if value is None or value == "":
            continue
        if isinstance(value, (list, tuple, set)):
            conditions.append(models.FieldCondition(key=key, match=models.MatchAny(any=list(value))))
        else:
            conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    return models.Filter(must=conditions) if conditions else None


def _scroll_payloads(filter_: models.Filter, limit: int = 10_000) -> list:
    client = get_qdrant_client()
    rows = []
    offset = None
    while len(rows) < limit:
        batch, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=filter_,
            limit=min(256, limit - len(rows)),
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        rows.extend(batch)
        if offset is None:
            break
    return rows


async def get_document_state(document_id: str) -> dict | None:
    points = _scroll_payloads(_must_filter(document_id=document_id, is_current=True), limit=1)
    return dict(points[0].payload) if points else None


async def get_document_chunks(document_id: str) -> list[dict]:
    points = _scroll_payloads(_must_filter(document_id=document_id, is_current=True))
    rows = [dict(p.payload or {}) for p in points]
    rows.sort(key=lambda row: int(row.get("chunk_index", 0)))
    return rows


async def get_document_content(document_id: str) -> str:
    """Reconstruct a document while removing deterministic chunk overlap."""
    rows = await get_document_chunks(document_id)
    if not rows:
        return ""
    merged = str(rows[0].get("content", ""))
    for row in rows[1:]:
        chunk = str(row.get("content", ""))
        overlap = 0
        max_overlap = min(300, len(merged), len(chunk))
        for size in range(max_overlap, 19, -1):
            if merged[-size:] == chunk[:size]:
                overlap = size
                break
        merged += chunk[overlap:]
    return merged


async def upsert_document(
    *,
    title: str,
    content: str,
    source_type: str,
    document_id: str | None = None,
    canonical_url: str | None = None,
    file_id: str | None = None,
    topic: str = "general",
    authority_level: int = 2,
    crawled_at: str | None = None,
    published_at: str | None = None,
    expires_at: str | None = None,
    raw_hash: str | None = None,
    metadata: dict | None = None,
    chunk_size: int = 900,
    overlap: int = 120,
) -> dict:
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"Invalid source_type: {source_type}")
    clean_content = content.strip()
    if not clean_content:
        raise ValueError("Cannot index empty content")

    canonical_url = canonicalize_url(canonical_url)
    key = file_id or canonical_url or title
    document_id = document_id or stable_document_id(source_type, key)
    digest = hash_content(clean_content)
    existing = await get_document_state(document_id)
    if existing and existing.get("content_hash") == digest:
        chunks = await get_document_chunks(document_id)
        return {"status": "unchanged", "document_id": document_id, "chunks": len(chunks), "content_hash": digest}

    chunks = []
    start = 0
    while start < len(clean_content):
        end = min(len(clean_content), start + chunk_size)
        # Prefer a paragraph/sentence boundary near the end of the chunk.
        if end < len(clean_content):
            boundary = max(clean_content.rfind("\n\n", start + chunk_size // 2, end), clean_content.rfind(". ", start + chunk_size // 2, end))
            if boundary > start:
                end = boundary + 1
        chunks.append(clean_content[start:end].strip())
        if end >= len(clean_content):
            break
        start = max(start + 1, end - overlap)

    embedding_inputs = [f"Tiêu đề: {title}\nLoại nguồn: {source_type}\nChủ đề: {topic}\n\n{chunk}" for chunk in chunks]
    embeddings = await get_embeddings_batch(embedding_inputs)
    client = get_qdrant_client()

    # Delete the previous current version only after embeddings succeed.
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=models.FilterSelector(filter=_must_filter(document_id=document_id)),
        wait=True,
    )

    base_payload = {
        "document_id": document_id,
        "title": title,
        "source_type": source_type,
        "canonical_url": canonical_url,
        "domain": urlsplit(canonical_url).netloc if canonical_url else "",
        "topic": topic,
        "title_key": _ascii(title).strip(),
        "authority_level": max(1, min(int(authority_level), 5)),
        "content_hash": digest,
        "raw_hash": raw_hash or "",
        "crawled_at": crawled_at or _now_iso(),
        "published_at": published_at or "",
        "expires_at": expires_at or None,
        "is_current": True,
    }
    if file_id:
        base_payload["file_id"] = file_id
    if metadata:
        for key_, value in metadata.items():
            if key_ not in base_payload and value is not None:
                base_payload[key_] = value

    points = []
    namespace = uuid.UUID("76d1a0da-2594-4bdd-a672-753575459e75")
    for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        payload = {**base_payload, "content": chunk, "chunk_index": index, "chunk_count": len(chunks)}
        points.append(models.PointStruct(id=str(uuid.uuid5(namespace, f"{document_id}:{index}")), vector=embedding, payload=payload))
    client.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)
    logger.info(f"Upserted '{title}' source={source_type} chunks={len(chunks)} document_id={document_id[:12]}")
    return {"status": "created" if not existing else "updated", "document_id": document_id, "chunks": len(chunks), "content_hash": digest}


async def store_document(
    title: str,
    content: str,
    chunk_size: int = 900,
    overlap: int = 120,
    file_id: str | None = None,
    source_type: str = "internal",
    **metadata,
) -> int:
    """Backward-compatible wrapper used by file/report upload paths."""
    result = await upsert_document(
        title=title,
        content=content,
        source_type=source_type,
        file_id=file_id,
        chunk_size=chunk_size,
        overlap=overlap,
        **metadata,
    )
    return int(result["chunks"])


async def delete_chunks_by_file_id(file_id: str) -> None:
    get_qdrant_client().delete(
        collection_name=COLLECTION_NAME,
        points_selector=models.FilterSelector(filter=_must_filter(file_id=file_id)),
        wait=True,
    )
    logger.info(f"Deleted Qdrant chunks for file_id={file_id}")


def _ascii(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_\.]+", _ascii(value)) if len(token) > 1}


def infer_query_scope(query: str) -> tuple[list[str] | None, str | None]:
    q = _ascii(query)
    scopes = []
    if any(term in q for term in ("chinh sach", "so tay", "noi bo", "file ", ".pdf", ".docx", "bao cao siupo", "cua nha hang")):
        scopes.append("internal")
    if any(term in q for term in ("luat", "nghi dinh", "thong tu", "quy dinh hien hanh", "thue", "hoa don", "an toan thuc pham", "phap ly", "co quan")):
        scopes.append("regulatory")
    if any(term in q for term in ("xu huong", "thi truong", "tin tuc", "gia nguyen lieu", "doi thu", "moi nhat", "hom nay")):
        scopes.extend(("market", "daily_digest"))
    if scopes:
        return list(dict.fromkeys(scopes)), None
    return None, None


def _rerank(query: str, result, inferred_sources: list[str] | None) -> float:
    payload = result.payload or {}
    q_tokens = _tokens(query)
    title = str(payload.get("title", ""))
    content = str(payload.get("content", ""))
    title_tokens = _tokens(title)
    content_tokens = _tokens(content)
    title_overlap = len(q_tokens & title_tokens) / max(1, len(q_tokens))
    content_overlap = len(q_tokens & content_tokens) / max(1, len(q_tokens))
    score = float(result.score) + 0.30 * title_overlap + 0.12 * content_overlap
    q_ascii = _ascii(query).replace(" ", "_")
    title_ascii = _ascii(title).replace(" ", "_")
    if q_ascii and (q_ascii in title_ascii or title_ascii in q_ascii):
        score += 0.30
    source = payload.get("source_type")
    if inferred_sources and source in inferred_sources:
        score += 0.08
    score += 0.01 * int(payload.get("authority_level", 1) or 1)
    return score


async def retrieve_relevant_chunks(
    query: str,
    top_k: int = 8,
    *,
    source_type: str | None = None,
    source_types: list[str] | None = None,
    topic: str | None = None,
    candidate_k: int = 40,
) -> list[dict]:
    inferred_sources, inferred_topic = infer_query_scope(query)
    if source_type and source_types:
        raise ValueError("Use source_type or source_types, not both")
    source_types = ([source_type] if source_type else source_types) or inferred_sources
    if source_types:
        invalid = set(source_types) - SOURCE_TYPES
        if invalid:
            raise ValueError(f"Invalid source types: {sorted(invalid)}")
    # Only enforce an explicit topic. Rule-based topics are hints because old
    # documents may still carry the legacy topic during gradual migration.
    filter_ = _must_filter(source_type=source_types, topic=topic, is_current=True)
    query_embedding = await get_embedding(query)
    results = get_qdrant_client().search(
        collection_name=COLLECTION_NAME,
        query_vector=query_embedding,
        query_filter=filter_,
        limit=max(top_k, candidate_k),
        with_payload=True,
    )

    # Filename queries get a deterministic lexical safety net. This prevents a
    # newly uploaded policy from disappearing below vector top-k as the corpus grows.
    query_ascii = _ascii(query)
    if any(ext in query_ascii for ext in (".pdf", ".doc", ".docx", ".txt", ".md", ".xlsx")):
        exact_filter = _must_filter(source_type=source_types or ["internal"], is_current=True)
        seen_ids = {str(row.id) for row in results}
        matched_document_ids: set[str] = set()
        for point in _scroll_payloads(exact_filter, limit=2_000):
            title_key = str((point.payload or {}).get("title_key", ""))
            if title_key and title_key in query_ascii:
                matched_document_ids.add(str((point.payload or {}).get("document_id", "")))
                if str(point.id) not in seen_ids:
                    results.append(SimpleNamespace(id=point.id, payload=point.payload, score=0.65))
                    seen_ids.add(str(point.id))
        if matched_document_ids:
            results = [
                row for row in results
                if str((row.payload or {}).get("document_id", "")) in matched_document_ids
            ]

    ranked_all = sorted(results, key=lambda row: _rerank(query, row, source_types), reverse=True)
    ranked = []
    per_document: dict[str, int] = {}
    filename_query = any(ext in query_ascii for ext in (".pdf", ".doc", ".docx", ".txt", ".md", ".xlsx"))
    per_document_limit = top_k if filename_query else min(6, top_k)
    for row in ranked_all:
        document_id = str((row.payload or {}).get("document_id", row.id))
        if per_document.get(document_id, 0) >= per_document_limit:
            continue
        ranked.append(row)
        per_document[document_id] = per_document.get(document_id, 0) + 1
        if len(ranked) >= top_k:
            break
    chunks = []
    for result in ranked:
        payload = result.payload or {}
        chunks.append({
            "title": payload.get("title", ""),
            "content": payload.get("content", ""),
            "score": result.score,
            "rerank_score": _rerank(query, result, source_types),
            "document_id": payload.get("document_id", ""),
            "source_type": payload.get("source_type", ""),
            "topic": payload.get("topic", ""),
            "canonical_url": payload.get("canonical_url", ""),
            "crawled_at": payload.get("crawled_at", ""),
            "authority_level": payload.get("authority_level", 1),
        })
    logger.info(f"Retrieved {len(chunks)} chunks query={query[:80]!r} sources={source_types or 'all'}")
    return chunks


async def get_daily_digest(date_iso: str) -> dict | None:
    document_id = stable_document_id("daily_digest", date_iso)
    chunks = await get_document_chunks(document_id)
    if not chunks:
        return None
    first = chunks[0]
    return {
        "date": date_iso,
        "document_id": document_id,
        "title": first.get("title", f"Daily digest {date_iso}"),
        "content": await get_document_content(document_id),
        "source_count": first.get("source_count", 0),
        "crawled_at": first.get("crawled_at", ""),
    }


async def cleanup_expired_documents(now_iso: str | None = None) -> int:
    now_value = datetime.fromisoformat((now_iso or _now_iso()).replace("Z", "+00:00"))
    filter_ = models.Filter(must=[models.FieldCondition(key="expires_at", range=models.DatetimeRange(lte=now_value))])
    points = _scroll_payloads(filter_)
    if not points:
        return 0
    ids = [point.id for point in points]
    get_qdrant_client().delete(COLLECTION_NAME, points_selector=models.PointIdsList(points=ids), wait=True)
    logger.info(f"Retention cleanup removed {len(ids)} expired chunks")
    return len(ids)
