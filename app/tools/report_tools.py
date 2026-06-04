"""
Report tools — Generate and persist analytics reports.

Reports are saved as Markdown files into the File Manager and indexed in Qdrant
so they can be retrieved via RAG search later.
"""
import os
import re
import uuid
import asyncio
import unicodedata
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from loguru import logger

from app.memory import file_log
from app.rag.retriever import store_document


UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "data/uploads"))

# Collects file metadata created during a single chat turn.
# Reset by chat_service before each orchestrator run.
created_files: ContextVar[list] = ContextVar("created_files", default=[])


def _slugify(text: str, max_length: int = 60) -> str:
    """Vietnamese-safe slug for filenames."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[-\s]+", "_", text)
    return text[:max_length] or "report"


async def create_analytics_report(title: str, content: str, topic: str = "") -> dict:
    """
    Save an analytics report as a Markdown file in the File Manager and index it in Qdrant.

    Call this only after the user has explicitly confirmed they want a report file.

    Args:
        title: Short human-readable title of the report (e.g., "Phân tích doanh thu tháng 5/2026").
        content: Full Markdown body of the report.
        topic: Short slug-friendly topic for the filename (e.g., "doanh_thu_thang_5").
               If empty, a slug will be generated from the title.

    Returns:
        Dict with file_id, filename, chunk_count, and a short success message.
    """
    logger.info(f"Tool: create_analytics_report(title='{title}', topic='{topic}')")

    if not content or not content.strip():
        return {"error": "Nội dung báo cáo rỗng, không thể lưu."}

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    slug = _slugify(topic or title)
    filename = f"analytics_{slug}_{timestamp}.md"

    storage_path = (UPLOAD_DIR / f"{file_id}.md").resolve()

    # Prepend a title header so the rendered markdown opens cleanly
    body = content if content.lstrip().startswith("#") else f"# {title}\n\n{content}"
    body_bytes = body.encode("utf-8")

    def _write():
        with open(storage_path, "wb") as f:
            f.write(body_bytes)

    await asyncio.to_thread(_write)
    logger.info(f"ReportTool: Wrote {storage_path} ({len(body_bytes)} bytes)")

    await file_log.create_file(
        file_id=file_id,
        filename=filename,
        file_type="document",
        extension="md",
        mime_type="text/markdown",
        size_bytes=len(body_bytes),
        storage_path=str(storage_path),
        description=f"Báo cáo phân tích tự sinh: {title}",
        uploaded_by="analytics-agent",
    )

    chunk_count = 0
    try:
        indexable = f"Tên file: {filename}\nMô tả: Báo cáo phân tích tự sinh: {title}\n\n{body}"
        chunk_count = await store_document(title=title, content=indexable, file_id=file_id)
        await file_log.mark_indexed(file_id, chunk_count)
        logger.info(f"ReportTool: Indexed {filename} → {chunk_count} chunks in Qdrant")
    except Exception as e:
        logger.exception(f"ReportTool: Qdrant indexing failed for {file_id}: {e}")

    result = {
        "file_id": file_id,
        "filename": filename,
        "chunk_count": chunk_count,
        "message": f"Đã lưu báo cáo '{title}' vào File Manager. Anh có thể xem trong mục quản lý file.",
    }

    # Collect file info for the chat response
    try:
        files = created_files.get()
    except LookupError:
        files = []
        created_files.set(files)
    files.append({
        "file_id": file_id,
        "filename": filename,
        "extension": "md",
        "mime_type": "text/markdown",
        "size_bytes": len(body_bytes),
    })

    return result
