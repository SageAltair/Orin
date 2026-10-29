"""Small dependency-free operational counters for private infrastructure scraping."""
from __future__ import annotations

from collections import Counter
from threading import Lock

_lock = Lock()
_requests: Counter[tuple[str, str]] = Counter()
_request_duration_seconds = 0.0
_maintenance_failures = 0


def record_request(route: str, status: int, duration_seconds: float) -> None:
    status_class = f"{status // 100}xx"
    with _lock:
        _requests[(route, status_class)] += 1
        global _request_duration_seconds
        _request_duration_seconds += duration_seconds


def record_maintenance_failure() -> None:
    with _lock:
        global _maintenance_failures
        _maintenance_failures += 1


def render_prometheus() -> str:
    with _lock:
        request_rows = sorted(_requests.items())
        duration = _request_duration_seconds
        maintenance_failures = _maintenance_failures
    lines = [
        "# HELP orin_http_requests_total Completed HTTP requests.",
        "# TYPE orin_http_requests_total counter",
    ]
    for (route, status_class), count in request_rows:
        safe_route = route.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'orin_http_requests_total{{route="{safe_route}",status_class="{status_class}"}} {count}')
    lines.extend([
        "# HELP orin_http_request_duration_seconds_total Total request processing time.",
        "# TYPE orin_http_request_duration_seconds_total counter",
        f"orin_http_request_duration_seconds_total {duration:.6f}",
        "# HELP orin_background_maintenance_failures_total Background maintenance failures.",
        "# TYPE orin_background_maintenance_failures_total counter",
        f"orin_background_maintenance_failures_total {maintenance_failures}",
        "",
    ])
    return "\n".join(lines)
