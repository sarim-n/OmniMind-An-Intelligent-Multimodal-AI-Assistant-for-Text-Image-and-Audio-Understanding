"""Transcript model."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.attachment import Attachment


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Transcript(Base):
    """ASR transcription generated for an audio attachment."""

    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    attachment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("attachments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    insights: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Relationships
    attachment: Mapped["Attachment"] = relationship("Attachment", back_populates="transcripts")
