"""Metric telemetry model."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Metric(Base):
    """Inference and system performance metrics record."""

    __tablename__ = "metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    component: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    gpu_mem_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ram_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )
