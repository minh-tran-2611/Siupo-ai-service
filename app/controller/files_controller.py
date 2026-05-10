"""
Files controller — File Manager endpoints.
Handles upload (multipart), list, download (blob stream), and delete.
"""
import traceback
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from loguru import logger

from app.service.file_service import (
    upload_file,
    list_files,
    get_file_blob,
    delete_file,
    MAX_FILE_SIZE,
)

router = APIRouter()


@router.post("/files/upload")
async def upload_endpoint(
    file: UploadFile = File(...),
    description: str | None = Form(None),
    uploaded_by: str | None = Form(None),
):
    """Multipart upload — saves blob, registers metadata, indexes if text-based."""
    try:
        raw = await file.read()
        if len(raw) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max {MAX_FILE_SIZE // (1024 * 1024)} MB."
            )
        row = await upload_file(
            raw_bytes=raw,
            filename=file.filename or "untitled",
            description=description,
            uploaded_by=uploaded_by,
        )
        return {"status": "ok", "file": row}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"upload_endpoint error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files")
async def list_endpoint(
    file_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """List files with optional file_type filter (document/image/data/other/all)."""
    try:
        return await list_files(file_type=file_type, limit=limit)
    except Exception as e:
        logger.error(f"list_endpoint error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/{file_id}/download")
async def download_endpoint(file_id: str):
    """Stream the original blob with the original filename."""
    blob = await get_file_blob(file_id)
    if not blob:
        raise HTTPException(status_code=404, detail="File not found")
    path, filename, mime = blob
    # RFC 5987 — encode filename for non-ASCII names
    encoded_name = quote(filename)
    return FileResponse(
        path=path,
        media_type=mime,
        filename=filename,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"
        },
    )


@router.delete("/files/{file_id}")
async def delete_endpoint(file_id: str):
    """Delete file: blob from FS, row from Turso, chunks from Qdrant."""
    try:
        ok = await delete_file(file_id)
        if not ok:
            raise HTTPException(status_code=404, detail="File not found")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"delete_endpoint error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
