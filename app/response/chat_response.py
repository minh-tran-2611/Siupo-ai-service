from pydantic import BaseModel


class FileAttachment(BaseModel):
    """A file created during the chat turn (e.g. analytics report)."""
    file_id: str
    filename: str
    extension: str = ""
    mime_type: str = ""
    size_bytes: int = 0


class ChatResponse(BaseModel):
    reply: str
    files: list[FileAttachment] = []


class DocumentResponse(BaseModel):
    status: str
