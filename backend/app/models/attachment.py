"""Attachment model."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.image_analysis import ImageAnalysis
    from app.models.message import Message
    from app.models.transcript import Transcript
    from app.models.user import User


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Attachment(Base):
    """Uploaded or derived media attachment."""

    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    message_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("messages.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # image | audio
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )

    # Relationships
    message: Mapped["Message | None"] = relationship("Message", back_populates="attachments")
    user: Mapped["User"] = relationship("User", back_populates="attachments")
    transcripts: Mapped[list["Transcript"]] = relationship(
        "Transcript",
        back_populates="attachment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    image_analyses: Mapped[list["ImageAnalysis"]] = relationship(
        "ImageAnalysis",
        back_populates="attachment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
