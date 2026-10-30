"""Pydantic schemas for conversation messages."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.attachment import AttachmentRead


class MessageCreate(BaseModel):
    """Payload to create a new message."""

    role: Literal["user", "assistant", "system"] = "user"
    content: str = Field(..., min_length=1)
    language: str | None = None
    modalities: list[str] = Field(default_factory=lambda: ["text"])


class MessageRead(BaseModel):
    """Message response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    language: str | None = None
    modalities: list[str] = Field(default_factory=list)
    created_at: datetime
    attachments: list[AttachmentRead] = Field(default_factory=list)


class MessageList(BaseModel):
    """Paginated list of messages."""

    items: list[MessageRead]
    total: int
    page: int
    page_size: int
