"""Unit tests for metrics and telemetry tracking service."""

import time

from sqlalchemy.orm import Session

from app.models.metric import Metric
from app.services.metrics_service import MetricTracker, persist_metric, track, track_fn


def test_metric_tracker_tokens_and_ttft() -> None:
    tracker = MetricTracker("test_comp", "test_op")
    tracker.record_token()
    assert tracker.ttft_ms is not None
    assert tracker.token_count == 1
    assert "ttft_ms" in tracker.extra

    tracker.record_token()
    tracker.record_token()
    assert tracker.token_count == 3

    time.sleep(0.01)
    tracker.finalize()
    assert tracker.latency_ms > 0
    assert tracker.extra.get("tokens_generated") == 3
    assert tracker.extra.get("tokens_per_sec", 0) > 0


def test_persist_metric_writes_to_db(db: Session) -> None:
    metric = persist_metric(
        component="llm",
        operation="generate",
        latency_ms=123.45,
        extra={"model": "qwen", "tokens": 50},
        db=db,
    )
    assert metric is not None
    assert metric.id is not None
    assert metric.component == "llm"
    assert metric.operation == "generate"
    assert metric.latency_ms == 123.45
    assert metric.extra == {"model": "qwen", "tokens": 50}

    # Verify queryable from DB
    saved = db.query(Metric).filter(Metric.id == metric.id).first()
    assert saved is not None
    assert saved.component == "llm"


def test_track_context_manager(db: Session) -> None:
    with track("memory", "retrieve", db=db, extra={"top_k": 3}) as tracker:
        tracker.set_tokens(count=5)
        time.sleep(0.005)

    recent = (
        db.query(Metric)
        .filter(Metric.component == "memory", Metric.operation == "retrieve")
        .order_by(Metric.created_at.desc())
        .first()
    )
    assert recent is not None
    assert recent.latency_ms > 0
    assert recent.extra is not None
    assert recent.extra.get("top_k") == 3
    assert recent.extra.get("tokens_generated") == 5


def test_track_fn_decorator(db: Session) -> None:
    @track_fn("embed", "infer", db_factory=lambda: db)
    def compute_embedding(data: str) -> str:
        return f"embedded_{data}"

    result = compute_embedding("hello")
    assert result == "embedded_hello"

    rec = db.query(Metric).filter(Metric.component == "embed", Metric.operation == "infer").first()
    assert rec is not None
    assert rec.latency_ms > 0


def test_metric_never_crashes_on_invalid_db() -> None:
    # Passing an object that fails on commit/add should not raise an exception
    class BadSession:
        def add(self, obj: object) -> None:
            raise RuntimeError("Database connection broken")

    result = persist_metric(
        component="err_test",
        operation="noop",
        latency_ms=10.0,
        db=BadSession(),  # type: ignore[arg-type]
    )
    # Never raises, returns None gracefully
    assert result is None
