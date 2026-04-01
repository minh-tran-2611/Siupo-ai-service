from pydantic import BaseModel


class ChatRequest(BaseModel):
    userId: str
    message: str


class ClearChatRequest(BaseModel):
    userId: str


class DocumentRequest(BaseModel):
    title: str
    content: str
