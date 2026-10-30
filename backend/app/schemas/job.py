"""Pydantic schemas for asynchronous jobs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobRead(BaseModel):
    """Job status and result schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    type: str
    status: str
    progress: float = Field(default=0.0, description="Completion progress from 0.0 to 1.0")
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
