"""Structured tool call, provider response, and approval action models."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field

from app.models.messages import BaseModel, PermissionLevel


class ToolCallRequest(BaseModel):
    tool_call_id: str
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    provider: str  # "GROK" or "GEMINI"
    model_id: str
    key_alias: str
    response_id: str = ""
    text: str = ""
    tool_calls: List[ToolCallRequest] = Field(default_factory=list)
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    raw_usage: Dict[str, Any] = Field(default_factory=dict)
    switched_from: Optional[str] = None


class PendingAction(BaseModel):
    action_id: str
    tool_call_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    permission_level: PermissionLevel
    reason: str
    status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL, APPROVED, REJECTED, EXECUTED, FAILED
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
