"""
Metrics service module - provides application metrics collection and monitoring.
"""

import datetime
import statistics
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict


class MetricType(str, Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class MetricPoint:
    value: float
    timestamp: datetime.datetime
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class Metric:
    name: str
    metric_type: MetricType
    description: str = ""
    unit: str = ""
    points: List[MetricPoint] = field(default_factory=list)

    def add_point(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        self.points.append(MetricPoint(
            value=value,
            timestamp=datetime.datetime.now(),
            labels=labels or {}
        ))

    def get_latest(self) -> Optional[float]:
        if not self.points:
            return None
        return self.points[-1].value

    def get_stats(self) -> Dict[str, Any]:
        if not self.points:
            return {}
        
        values = [p.value for p in self.points]
        return {
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": statistics.mean(values),
            "median": statistics.median(values) if len(values) > 1 else values[0],
            "stddev": statistics.stdev(values) if len(values) > 1 else 0
        }


class MetricsService:
    def __init__(self, max_points_per_metric: int = 10000):
        self._metrics: Dict[str, Metric] = {}
        self._max_points = max_points_per_metric
        self._request_durations: List[float] = []
        self._error_counts: Dict[str, int] = defaultdict(int)

    def _get_or_create_metric(
        self,
        name: str,
        metric_type: MetricType,
        description: str = "",
        unit: str = ""
    ) -> Metric:
        if name not in self._metrics:
            self._metrics[name] = Metric(
                name=name,
                metric_type=metric_type,
                description=description,
                unit=unit
            )
        return self._metrics[name]

    def _trim_points(self, metric: Metric) -> None:
        if len(metric.points) > self._max_points:
            metric.points = metric.points[-self._max_points:]

    async def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
        description: str = ""
    ) -> float:
        metric = self._get_or_create_metric(name, MetricType.COUNTER, description)
        current = metric.get_latest() or 0
        new_value = current + value
        metric.add_point(new_value, labels)
        self._trim_points(metric)
        return new_value

    async def gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        description: str = ""
    ) -> None:
        metric = self._get_or_create_metric(name, MetricType.GAUGE, description)
        metric.add_point(value, labels)
        self._trim_points(metric)

    async def histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        description: str = "",
        unit: str = ""
    ) -> None:
        metric = self._get_or_create_metric(name, MetricType.HISTOGRAM, description, unit)
        metric.add_point(value, labels)
        self._trim_points(metric)

    async def timer(
        self,
        name: str,
        duration_ms: float,
        labels: Optional[Dict[str, str]] = None,
        description: str = ""
    ) -> None:
        metric = self._get_or_create_metric(name, MetricType.TIMER, description, "ms")
        metric.add_point(duration_ms, labels)
        self._trim_points(metric)
        self._request_durations.append(duration_ms)
        if len(self._request_durations) > 10000:
            self._request_durations = self._request_durations[-10000:]

    async def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float
    ) -> None:
        labels = {
            "endpoint": endpoint,
            "method": method,
            "status": str(status_code)
        }
        
        await self.increment("http_requests_total", labels=labels)
        await self.timer("http_request_duration", duration_ms, labels=labels)
        
        if status_code >= 400:
            error_key = f"{method}:{endpoint}:{status_code}"
            self._error_counts[error_key] += 1

    async def record_error(
        self,
        error_type: str,
        message: str = "",
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        merged_labels = {"error_type": error_type, **(labels or {})}
        await self.increment("errors_total", labels=merged_labels)

    def get_metric(self, name: str) -> Optional[Metric]:
        return self._metrics.get(name)

    def get_metric_value(self, name: str) -> Optional[float]:
        metric = self._metrics.get(name)
        return metric.get_latest() if metric else None

    def get_metric_stats(self, name: str) -> Dict[str, Any]:
        metric = self._metrics.get(name)
        return metric.get_stats() if metric else {}

    def list_metrics(self) -> List[str]:
        return list(self._metrics.keys())

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "type": metric.metric_type.value,
                "description": metric.description,
                "unit": metric.unit,
                "latest_value": metric.get_latest(),
                "stats": metric.get_stats()
            }
            for name, metric in self._metrics.items()
        }

    def get_request_stats(self) -> Dict[str, Any]:
        if not self._request_durations:
            return {}
        
        return {
            "total_requests": len(self._request_durations),
            "avg_duration_ms": statistics.mean(self._request_durations),
            "min_duration_ms": min(self._request_durations),
            "max_duration_ms": max(self._request_durations),
            "p50_duration_ms": statistics.median(self._request_durations),
            "p95_duration_ms": self._percentile(self._request_durations, 95),
            "p99_duration_ms": self._percentile(self._request_durations, 99)
        }

    def _percentile(self, data: List[float], percentile: float) -> float:
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def get_error_stats(self) -> Dict[str, int]:
        return dict(self._error_counts)

    def get_summary(self) -> Dict[str, Any]:
        return {
            "metrics_count": len(self._metrics),
            "request_stats": self.get_request_stats(),
            "error_counts": dict(self._error_counts),
            "metrics": self.get_all_metrics()
        }

    def reset(self, name: Optional[str] = None) -> None:
        if name:
            if name in self._metrics:
                del self._metrics[name]
        else:
            self._metrics.clear()
            self._request_durations.clear()
            self._error_counts.clear()


metrics_service = MetricsService()
