"""User model."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.attachment import Attachment
    from app.models.conversation import Conversation
    from app.models.job import Job


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    """User account entity."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )

    # Relationships
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    jobs: Mapped[list["Job"]] = relationship(
        "Job", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
