"""Deterministic execution target policy. Cloud remains unavailable until provisioned."""
from dataclasses import dataclass
from enum import StrEnum


class ExecutionTarget(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"
    AUTO = "auto"


@dataclass(frozen=True)
class TargetDecision:
    selected: ExecutionTarget | None
    reason: str


def select_target(*, requested: ExecutionTarget, local_worker_eligible: bool,
                  user_authorized: bool, contains_private_data: bool = True,
                  cloud_provisioned: bool = False, cloud_authorized: bool = False,
                  required_capabilities: frozenset[str] = frozenset(),
                  local_capabilities: frozenset[str] = frozenset(),
                  cloud_capabilities: frozenset[str] = frozenset(),
                  local_resources_available: bool = True, cloud_resources_available: bool = True,
                  required_region: str | None = None, local_region: str | None = None,
                  cloud_region: str | None = None, max_cost: float | None = None,
                  cloud_cost_estimate: float | None = None, max_latency_ms: float | None = None,
                  local_latency_ms: float | None = None, cloud_latency_ms: float | None = None,
                  preferred_target: ExecutionTarget | None = None) -> TargetDecision:
    """Choose a safe target. Unknown cost/latency never satisfies an explicit limit."""
    local_ok = (local_worker_eligible and user_authorized and local_resources_available
        and required_capabilities.issubset(local_capabilities)
        and (required_region is None or local_region == required_region)
        and (max_latency_ms is None or (local_latency_ms is not None and 0 <= local_latency_ms <= max_latency_ms)))
    cloud_ok = (cloud_provisioned and cloud_authorized and user_authorized and cloud_resources_available
        and not contains_private_data and required_capabilities.issubset(cloud_capabilities)
        and (required_region is None or cloud_region == required_region)
        and (max_cost is None or (cloud_cost_estimate is not None and 0 <= cloud_cost_estimate <= max_cost))
        and (max_latency_ms is None or (cloud_latency_ms is not None and 0 <= cloud_latency_ms <= max_latency_ms)))
    if requested == ExecutionTarget.LOCAL:
        return TargetDecision(ExecutionTarget.LOCAL, "eligible local worker") if local_ok else TargetDecision(None, "no authorized healthy local worker")
    if requested == ExecutionTarget.CLOUD:
        return TargetDecision(ExecutionTarget.CLOUD, "authorized cloud environment") if cloud_ok else TargetDecision(None, "cloud execution is unavailable or disallowed by policy")
    if preferred_target == ExecutionTarget.CLOUD and cloud_ok:
        return TargetDecision(ExecutionTarget.CLOUD, "AUTO honored the eligible cloud preference")
    if preferred_target == ExecutionTarget.LOCAL and local_ok:
        return TargetDecision(ExecutionTarget.LOCAL, "AUTO honored the eligible local preference")
    if local_ok:
        return TargetDecision(ExecutionTarget.LOCAL, "AUTO selected the eligible local worker")
    if cloud_ok:
        return TargetDecision(ExecutionTarget.CLOUD, "AUTO selected the eligible cloud environment")
    return TargetDecision(None, "no safe eligible execution target is available")
