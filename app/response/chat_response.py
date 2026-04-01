from pydantic import BaseModel


class ChatResponse(BaseModel):
    reply: str


class DocumentResponse(BaseModel):
    status: str
