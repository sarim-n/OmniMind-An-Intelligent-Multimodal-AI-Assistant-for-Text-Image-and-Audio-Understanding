"""Pydantic schemas for media attachments."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AttachmentRead(BaseModel):
    """Attachment response payload."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    message_id: str | None = None
    user_id: str
    type: str
    path: str
    mime: str
    size: int
    duration_sec: float | None = None
    metadata_: dict[str, Any] = Field(
        default_factory=dict, alias="metadata", validation_alias="metadata_"
    )
    created_at: datetime
