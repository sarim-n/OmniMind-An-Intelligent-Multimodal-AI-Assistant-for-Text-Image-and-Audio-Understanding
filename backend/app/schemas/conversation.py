"""Pydantic schemas for conversations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    """Payload to create a new conversation."""

    title: str = Field(default="New Conversation", min_length=1, max_length=255)


class ConversationUpdate(BaseModel):
    """Payload to update/rename a conversation."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = None


class ConversationRead(BaseModel):
    """Conversation response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    summary: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    """Paginated list of conversations."""

    items: list[ConversationRead]
    total: int
    page: int
    page_size: int
