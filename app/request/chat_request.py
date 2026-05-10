from pydantic import BaseModel, Field


class ImagePayload(BaseModel):
    """Inline image attached to a chat turn (lives only for the session)."""
    data: str = Field(..., description="base64-encoded image bytes")
    mime: str = Field(..., description="MIME type, e.g. image/png")


class ChatRequest(BaseModel):
    userId: str
    message: str
    images: list[ImagePayload] = Field(default_factory=list)


class ClearChatRequest(BaseModel):
    userId: str


class DocumentRequest(BaseModel):
    title: str
    content: str
