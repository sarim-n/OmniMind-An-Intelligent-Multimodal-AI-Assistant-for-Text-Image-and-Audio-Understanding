"""Pydantic schemas for performance and operational telemetry metrics."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ComponentMetricSummary(BaseModel):
    """Aggregated latency and resource statistics per component and operation."""

    component: str
    operation: str
    count: int
    p50_latency_ms: float
    p95_latency_ms: float
    avg_latency_ms: float
    avg_tokens_per_sec: float | None = None
    avg_rtf: float | None = None
    avg_cpu_pct: float | None = None
    avg_ram_mb: float | None = None
    avg_gpu_mem_mb: float | None = None


class TimeSeriesDataPoint(BaseModel):
    """Individual timestamped telemetry measurement for charting."""

    id: str
    timestamp: str
    component: str
    operation: str
    latency_ms: float
    cpu_pct: float | None = None
    ram_mb: float | None = None
    gpu_mem_mb: float | None = None
    tokens_per_sec: float | None = None


class MetricsSummaryResponse(BaseModel):
    """Comprehensive performance dashboard summary."""

    total_operations: int
    average_latency_ms: float
    components: list[ComponentMetricSummary] = Field(default_factory=list)
    recent_time_series: list[TimeSeriesDataPoint] = Field(default_factory=list)
    system_status: dict[str, Any] = Field(default_factory=dict)
