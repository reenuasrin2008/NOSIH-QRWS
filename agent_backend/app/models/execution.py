"""Execution trace and tool execution receipt models."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field

from app.models.actions import PendingAction
from app.models.messages import BaseModel


class ToolExecutionRecord(BaseModel):
    execution_id: str
    tool_call_id: str
    tool: str
    provider: str = ""
    key_alias: str = ""
    status: str = "RUNNING"  # RUNNING, SUCCESS, FAILED, REJECTED, PENDING_APPROVAL, INTERRUPTED
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    state_version_before: int = 0
    state_version_after: int = 0
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ExecutionTrace(BaseModel):
    schema_version: str = "2.0.0"
    execution_id: str
    session_id: str
    user_message: str
    mode: str
    provider_mode: str
    provider_used: str = ""
    key_alias_used: str = ""
    provider_switches: List[str] = Field(default_factory=list)
    status: str = "RUNNING"  # RUNNING, COMPLETED, PENDING_APPROVAL, INTERRUPTED, FAILED
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    tool_records: List[ToolExecutionRecord] = Field(default_factory=list)
    pending_actions: List[PendingAction] = Field(default_factory=list)
    final_response: str = ""
    recommended: List[str] = Field(default_factory=list)
    executed: List[str] = Field(default_factory=list)
    verified: List[str] = Field(default_factory=list)
    incomplete: List[str] = Field(default_factory=list)
    error: Optional[str] = None
