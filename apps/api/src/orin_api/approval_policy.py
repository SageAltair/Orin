"""Deterministic approval policy; action risk comes only from the trusted registry."""
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ApprovalDecision:
    action: str
    risk_level: str
    approval_level: str
    requires_approval: bool
    reason: str
    policy_source: str


def decide_approval(
    action: str, risk_level: str, mode: str = "balanced", always: bool = False,
    custom: Mapping[str, str] | None = None,
) -> ApprovalDecision:
    risk = risk_level.lower()
    mode = mode if mode in {"conservative", "balanced", "automatic", "custom"} else "balanced"
    if risk in {"restricted", "critical"} or always:
        required, source, reason = True, "protected_action", "This protected action always requires explicit approval."
    elif mode == "custom":
        required = (custom or {}).get(action, "approval") != "automatic"
        source = "custom_action" if action in (custom or {}) else "custom_default"
        reason = "Your custom policy requires approval." if required else "Your custom policy permits this action automatically."
    else:
        thresholds = {"conservative": {"low"}, "balanced": {"low", "medium"}, "automatic": {"low", "medium"}}
        required = risk not in thresholds[mode]
        if always and mode == "automatic":
            required = True
        source = "autonomy_mode"
        reason = ("This action's registered risk level requires approval in your autonomy mode."
                  if required else "This action is permitted automatically by your autonomy mode.")
    level = "always" if risk in {"restricted", "critical"} or always else ("approval" if required else "automatic")
    return ApprovalDecision(action, risk, level, required, reason, source)
