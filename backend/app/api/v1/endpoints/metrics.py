"""Performance metrics and telemetry summary endpoints."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import psutil
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.metric import Metric
from app.models.user import User
from app.schemas.metrics import (
    ComponentMetricSummary,
    MetricsSummaryResponse,
    TimeSeriesDataPoint,
)

router = APIRouter()


def _percentile(values: list[float], pct: float) -> float:
    """Calculate percentile from a sorted list of float values."""
    if not values:
        return 0.0
    k = (len(values) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(values[int(k)], 2)
    d0 = values[int(f)] * (c - k)
    d1 = values[int(c)] * (k - f)
    return round(d0 + d1, 2)


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


@router.get(
    "/summary",
    response_model=MetricsSummaryResponse,
    summary="Get telemetry and performance metrics summary",
    description="Calculate p50/p95 latency, throughput, resource usage, and recent time-series metrics.",
)
def get_metrics_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MetricsSummaryResponse:
    """Aggregate all stored metrics into statistical summaries and chart series."""
    # Retrieve all metrics ordered chronologically
    records = db.query(Metric).order_by(Metric.created_at.asc()).all()

    if not records:
        return MetricsSummaryResponse(
            total_operations=0,
            average_latency_ms=0.0,
            components=[],
            recent_time_series=[],
            system_status={
                "cpu_percent": psutil.cpu_percent(interval=None),
                "ram_used_mb": round(psutil.virtual_memory().used / (1024 * 1024), 1),
            },
        )

    # Group metrics by (component, operation)
    grouped: dict[tuple[str, str], list[Metric]] = defaultdict(list)
    total_latency = 0.0

    for m in records:
        grouped[(m.component, m.operation)].append(m)
        total_latency += m.latency_ms

    components_summary: list[ComponentMetricSummary] = []
    for (comp, op), items in grouped.items():
        latencies = sorted(item.latency_ms for item in items)
        count = len(items)
        avg_lat = round(sum(latencies) / count, 2)
        p50 = _percentile(latencies, 50.0)
        p95 = _percentile(latencies, 95.0)

        tps_vals = [
            _safe_float((item.extra or {}).get("tokens_per_sec"))
            for item in items
            if (item.extra or {}).get("tokens_per_sec") is not None
        ]
        valid_tps = [v for v in tps_vals if v is not None]
        avg_tps = round(sum(valid_tps) / len(valid_tps), 2) if valid_tps else None

        rtf_vals = [
            _safe_float((item.extra or {}).get("rtf"))
            for item in items
            if (item.extra or {}).get("rtf") is not None
        ]
        valid_rtf = [v for v in rtf_vals if v is not None]
        avg_rtf = round(sum(valid_rtf) / len(valid_rtf), 2) if valid_rtf else None

        cpu_vals = [item.cpu_pct for item in items if item.cpu_pct is not None]
        avg_cpu = round(sum(cpu_vals) / len(cpu_vals), 1) if cpu_vals else None

        ram_vals = [item.ram_mb for item in items if item.ram_mb is not None]
        avg_ram = round(sum(ram_vals) / len(ram_vals), 1) if ram_vals else None

        gpu_vals = [item.gpu_mem_mb for item in items if item.gpu_mem_mb is not None]
        avg_gpu = round(sum(gpu_vals) / len(gpu_vals), 1) if gpu_vals else None

        components_summary.append(
            ComponentMetricSummary(
                component=comp,
                operation=op,
                count=count,
                p50_latency_ms=p50,
                p95_latency_ms=p95,
                avg_latency_ms=avg_lat,
                avg_tokens_per_sec=avg_tps,
                avg_rtf=avg_rtf,
                avg_cpu_pct=avg_cpu,
                avg_ram_mb=avg_ram,
                avg_gpu_mem_mb=avg_gpu,
            )
        )

    # Sort components by count desc
    components_summary.sort(key=lambda c: c.count, reverse=True)

    # Recent time series (last 60 records for charts)
    time_series = [
        TimeSeriesDataPoint(
            id=m.id,
            timestamp=m.created_at.isoformat(),
            component=m.component,
            operation=m.operation,
            latency_ms=round(m.latency_ms, 2),
            cpu_pct=m.cpu_pct,
            ram_mb=m.ram_mb,
            gpu_mem_mb=m.gpu_mem_mb,
            tokens_per_sec=_safe_float((m.extra or {}).get("tokens_per_sec")),
        )
        for m in records[-60:]
    ]

    # Current system status
    sys_status: dict[str, Any] = {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_used_mb": round(psutil.virtual_memory().used / (1024 * 1024), 1),
        "ram_total_mb": round(psutil.virtual_memory().total / (1024 * 1024), 1),
    }
    try:
        import torch

        if torch.cuda.is_available():
            sys_status["gpu_allocated_mb"] = round(torch.cuda.memory_allocated() / (1024 * 1024), 1)
    except Exception:
        pass

    return MetricsSummaryResponse(
        total_operations=len(records),
        average_latency_ms=round(total_latency / len(records), 2),
        components=components_summary,
        recent_time_series=time_series,
        system_status=sys_status,
    )
