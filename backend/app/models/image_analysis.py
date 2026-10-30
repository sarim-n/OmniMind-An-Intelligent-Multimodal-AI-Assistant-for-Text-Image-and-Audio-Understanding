"""Image analysis model."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.attachment import Attachment


def generate_uuid() -> str:
    return str(uuid.uuid4())


class ImageAnalysis(Base):
    """Computer vision and OCR analysis for an image attachment."""

    __tablename__ = "image_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    attachment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("attachments.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    objects: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, default=dict, nullable=True
    )

    # Relationships
    attachment: Mapped["Attachment"] = relationship("Attachment", back_populates="image_analyses")
