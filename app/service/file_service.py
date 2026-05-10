"""
File service — orchestrates uploads, parsing, indexing, and deletion.
Coordinates Turso registry, local FS blob storage, and Qdrant chunks.
"""
import os
import uuid
import asyncio
from pathlib import Path
from loguru import logger

from app.memory import file_log
from app.rag.retriever import store_document, delete_chunks_by_file_id
from app.utils.file_parser import (
    get_extension,
    categorize,
    get_mime_type,
    is_indexable,
    extract_text,
)


UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(25 * 1024 * 1024)))  # 25 MB


def _ensure_upload_dir():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def upload_file(
    raw_bytes: bytes,
    filename: str,
    description: str | None = None,
    uploaded_by: str | None = None,
) -> dict:
    """
    Save blob to local FS, register in Turso, and (if indexable) index in Qdrant.
    Returns the created file row.
    """
    _ensure_upload_dir()

    size_bytes = len(raw_bytes)
    if size_bytes > MAX_FILE_SIZE:
        raise ValueError(f"File too large: {size_bytes} bytes > {MAX_FILE_SIZE}")
    if size_bytes == 0:
        raise ValueError("Empty file")

    extension = get_extension(filename)
    file_type = categorize(extension)
    mime_type = get_mime_type(extension)
    file_id = str(uuid.uuid4())

    storage_filename = f"{file_id}.{extension}" if extension else file_id
    storage_path = (UPLOAD_DIR / storage_filename).resolve()

    # Write blob (sync write inside thread)
    def _write_blob():
        with open(storage_path, "wb") as f:
            f.write(raw_bytes)

    await asyncio.to_thread(_write_blob)
    logger.info(f"FileService: Saved blob {storage_path} ({size_bytes} bytes)")

    # Register in Turso
    await file_log.create_file(
        file_id=file_id,
        filename=filename,
        file_type=file_type,
        extension=extension,
        mime_type=mime_type,
        size_bytes=size_bytes,
        storage_path=str(storage_path),
        description=description,
        uploaded_by=uploaded_by,
    )

    # Index in Qdrant if applicable
    chunk_count = 0
    index_error: str | None = None
    if is_indexable(extension):
        logger.info(f"FileService: Extracting text from {filename} (.{extension})")
        text = await asyncio.to_thread(extract_text, str(storage_path), extension)
        if text and text.strip():
            # Prepend metadata so filename + description are searchable too.
            # Without this, queries that match metadata words (not body) would miss.
            header_lines = [f"Tên file: {filename}"]
            if description:
                header_lines.append(f"Mô tả: {description}")
            indexable_text = "\n".join(header_lines) + "\n\n" + text

            logger.info(f"FileService: Extracted {len(text)} chars, embedding to Qdrant...")
            try:
                chunk_count = await store_document(
                    title=filename,
                    content=indexable_text,
                    file_id=file_id,
                )
                await file_log.mark_indexed(file_id, chunk_count)
                logger.info(f"FileService: Indexed {filename} → {chunk_count} chunks in Qdrant")
            except Exception as e:
                index_error = f"{type(e).__name__}: {e}"
                logger.exception(f"FileService: Qdrant indexing failed for {file_id}: {e}")
        else:
            index_error = "Empty or unreadable content"
            logger.warning(f"FileService: No extractable text in {filename}, skipping index")
    else:
        logger.info(f"FileService: .{extension} not indexable, blob-only")

    row = await file_log.get_file(file_id)
    if index_error:
        row["index_error"] = index_error
    return row


async def list_files(file_type: str | None = None, limit: int = 100) -> dict:
    """Return file list + counts grouped by type."""
    files = await file_log.list_files(file_type=file_type, limit=limit)
    counts = await file_log.count_by_type()
    return {"files": files, "counts": counts}


async def get_file_blob(file_id: str) -> tuple[Path, str, str] | None:
    """Return (storage_path, original_filename, mime_type) for download, or None."""
    row = await file_log.get_file(file_id)
    if not row:
        return None
    path = Path(row["storage_path"])
    if not path.exists():
        logger.error(f"FileService: Blob missing for {file_id}: {path}")
        return None
    return path, row["filename"], row["mime_type"] or "application/octet-stream"


async def delete_file(file_id: str) -> bool:
    """Remove blob from FS, registry row from Turso, and chunks from Qdrant."""
    row = await file_log.get_file(file_id)
    if not row:
        return False

    # Delete blob
    path = Path(row["storage_path"])
    if path.exists():
        try:
            await asyncio.to_thread(path.unlink)
        except Exception as e:
            logger.error(f"FileService: Failed to delete blob {path}: {e}")

    # Delete Qdrant chunks (only if indexed)
    if row.get("indexed"):
        try:
            await delete_chunks_by_file_id(file_id)
        except Exception as e:
            logger.error(f"FileService: Failed to delete Qdrant chunks for {file_id}: {e}")

    # Delete registry row
    await file_log.delete_file(file_id)
    logger.info(f"FileService: Deleted file {file_id}")
    return True
