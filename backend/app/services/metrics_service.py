"""Inference and operational metrics tracking service."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import wraps
from typing import Any

import psutil
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.metric import Metric

logger = get_logger(__name__)


def _get_gpu_mem_mb() -> float | None:
    """Safely query allocated GPU memory if PyTorch with CUDA is available."""
    try:
        import torch

        if torch.cuda.is_available():
            return float(torch.cuda.memory_allocated() / (1024 * 1024))
    except Exception:
        pass
    return None


class MetricTracker:
    """Mutable tracker context populated during operation execution."""

    def __init__(self, component: str, operation: str, extra: dict[str, Any] | None = None):
        self.component = component
        self.operation = operation
        self.extra: dict[str, Any] = extra.copy() if extra else {}
        self.start_time: float = time.perf_counter()
        self.ttft_ms: float | None = None
        self.token_count: int = 0
        self.latency_ms: float = 0.0

    def mark_first_token(self) -> None:
        """Record Time-To-First-Token (TTFT) in milliseconds."""
        if self.ttft_ms is None:
            self.ttft_ms = (time.perf_counter() - self.start_time) * 1000.0
            self.extra["ttft_ms"] = round(self.ttft_ms, 2)

    def record_token(self) -> None:
        """Increment token count and mark first token if not already recorded."""
        self.mark_first_token()
        self.token_count += 1

    def set_tokens(self, count: int, prompt_tokens: int | None = None) -> None:
        """Explicitly set generated and prompt token counts."""
        self.token_count = count
        self.extra["tokens_generated"] = count
        if prompt_tokens is not None:
            self.extra["prompt_tokens"] = prompt_tokens

    def finalize(self) -> None:
        """Compute final latency and throughput metrics."""
        self.latency_ms = (time.perf_counter() - self.start_time) * 1000.0
        if self.token_count > 0:
            self.extra["tokens_generated"] = self.token_count
            sec = self.latency_ms / 1000.0
            if sec > 0:
                self.extra["tokens_per_sec"] = round(self.token_count / sec, 2)


def persist_metric(
    component: str,
    operation: str,
    latency_ms: float,
    extra: dict[str, Any] | None = None,
    db: Session | None = None,
) -> Metric | None:
    """Save an inference/system metric row to the database safely."""
    try:
        cpu_pct = psutil.cpu_percent(interval=None)
        ram_mb = float(psutil.virtual_memory().used / (1024 * 1024))
        gpu_mem_mb = _get_gpu_mem_mb()

        metric = Metric(
            component=component,
            operation=operation,
            latency_ms=round(latency_ms, 3),
            cpu_pct=round(cpu_pct, 2) if cpu_pct is not None else None,
            ram_mb=round(ram_mb, 2),
            gpu_mem_mb=round(gpu_mem_mb, 2) if gpu_mem_mb is not None else None,
            extra=extra if extra else None,
        )

        # Use passed session or isolated SessionLocal to never disrupt ongoing transactions
        if db is not None:
            db.add(metric)
            db.commit()
            db.refresh(metric)
        else:
            import app.db.session

            with app.db.session.SessionLocal() as session:
                session.add(metric)
                session.commit()
                session.refresh(metric)

        return metric
    except Exception as e:
        logger.warning(
            "Failed to record metric telemetry",
            component=component,
            operation=operation,
            error=str(e),
        )
        return None


@contextmanager
def track(
    component: str,
    operation: str,
    db: Session | None = None,
    extra: dict[str, Any] | None = None,
) -> Generator[MetricTracker, None, None]:
    """Context manager for telemetry tracking of inference and operational workloads."""
    tracker = MetricTracker(component=component, operation=operation, extra=extra)
    try:
        yield tracker
    finally:
        tracker.finalize()
        persist_metric(
            component=tracker.component,
            operation=tracker.operation,
            latency_ms=tracker.latency_ms,
            extra=tracker.extra,
            db=db,
        )


def track_fn(
    component: str,
    operation: str,
    db_factory: Callable[[], Session | None] | None = None,
) -> Callable[..., Any]:
    """Decorator to trace latency and telemetry of a sync or async function."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if asyncio.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracker = MetricTracker(component=component, operation=operation)
                try:
                    return await fn(*args, **kwargs)
                finally:
                    tracker.finalize()
                    db = db_factory() if db_factory else None
                    persist_metric(
                        component=tracker.component,
                        operation=tracker.operation,
                        latency_ms=tracker.latency_ms,
                        extra=tracker.extra,
                        db=db,
                    )

            return async_wrapper
        else:

            @wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracker = MetricTracker(component=component, operation=operation)
                try:
                    return fn(*args, **kwargs)
                finally:
                    tracker.finalize()
                    db = db_factory() if db_factory else None
                    persist_metric(
                        component=tracker.component,
                        operation=tracker.operation,
                        latency_ms=tracker.latency_ms,
                        extra=tracker.extra,
                        db=db,
                    )

            return sync_wrapper

    return decorator
