"""
Pydantic models for Zalo Bot webhook payloads.
"""
from pydantic import BaseModel, Field
from typing import Optional


class ZaloUser(BaseModel):
    id: str = Field(..., description="Zalo user ID")
    display_name: str = Field("", description="Display name of the user")
    is_bot: bool = Field(False, description="Whether the sender is a bot")


class ZaloChat(BaseModel):
    id: str = Field(..., description="Chat ID")
    chat_type: str = Field("PRIVATE", description="PRIVATE or GROUP")


class ZaloMessage(BaseModel):
    from_user: ZaloUser = Field(..., alias="from")
    chat: ZaloChat = Field(..., description="Chat info")
    message_id: str = Field("", description="Unique message ID")
    date: int = Field(0, description="Timestamp in milliseconds")
    text: Optional[str] = Field(None)
    photo: Optional[str] = Field(None)
    caption: Optional[str] = Field(None)
    sticker: Optional[str] = Field(None)
    url: Optional[str] = Field(None)

    model_config = {"populate_by_name": True}


class ZaloWebhookEvent(BaseModel):
    """
    Zalo gửi payload phẳng — event_name và message nằm ở root, không có wrapper 'result'.

    Sample payload:
    {
      "event_name": "message.text.received",
      "message": {
        "from": {"id": "abc123", "display_name": "Ted", "is_bot": false},
        "chat": {"id": "abc123", "chat_type": "PRIVATE"},
        "text": "Xin chào",
        "message_id": "msg_001",
        "date": 1750316131602
      }
    }
    """
    event_name: str = Field(..., description="Event type")
    message: Optional[ZaloMessage] = Field(None, description="Message details")