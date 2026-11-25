"""Permission policy enforcement for OBSERVE, ASSISTED, and AUTONOMOUS modes."""
from __future__ import annotations

from dataclasses import dataclass

from app.models.messages import AgentMode, PermissionLevel
from app.tools.schemas import ToolDefinition


@dataclass
class PermissionDecision:
    decision: str  # "ALLOW", "REQUIRE_APPROVAL", "DENY"
    reason: str


class PermissionManager:
    """Enforces mode-based execution policies and destructive action confirmation."""

    def __init__(self, confirm_destructive: bool = True):
        self.confirm_destructive = confirm_destructive

    def evaluate(self, mode: AgentMode, tool: ToolDefinition) -> PermissionDecision:
        if tool.permission_level == PermissionLevel.READ_ONLY:
            return PermissionDecision("ALLOW", "Read-only observation tool is permitted in all modes.")

        if mode == AgentMode.OBSERVE:
            return PermissionDecision(
                "DENY",
                f"OBSERVE mode is read-only; '{tool.name}' ({tool.permission_level.value}) cannot execute.",
            )

        if tool.permission_level == PermissionLevel.DESTRUCTIVE and self.confirm_destructive:
            return PermissionDecision(
                "REQUIRE_APPROVAL",
                f"Destructive action '{tool.name}' requires explicit operator confirmation.",
            )

        if mode == AgentMode.ASSISTED:
            return PermissionDecision(
                "REQUIRE_APPROVAL",
                f"ASSISTED mode requires operator approval before executing '{tool.name}'.",
            )

        return PermissionDecision("ALLOW", f"AUTONOMOUS mode permits operational tool '{tool.name}'.")
