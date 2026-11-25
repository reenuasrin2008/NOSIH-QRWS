"""Pydantic v1/v2 compatible message and session models for the AI Rescue Agent."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel as _PydanticBaseModel, Field


class BaseModel(_PydanticBaseModel):
    if not hasattr(_PydanticBaseModel, "model_dump"):
        def model_dump(self, *args, **kwargs):
            return self.dict(*args, **kwargs)

    if not hasattr(_PydanticBaseModel, "model_validate"):
        @classmethod
        def model_validate(cls, obj):
            return cls.parse_obj(obj)

    if not hasattr(_PydanticBaseModel, "model_copy"):
        def model_copy(self, *, update=None, deep=False):
            return self.copy(update=update, deep=deep)


class AgentMode(str, Enum):
    OBSERVE = "OBSERVE"
    ASSISTED = "ASSISTED"
    AUTONOMOUS = "AUTONOMOUS"


class ProviderMode(str, Enum):
    GROK = "GROK"
    GEMINI = "GEMINI"
    AUTO = "AUTO"


class PermissionLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    OPERATIONAL = "OPERATIONAL"
    DESTRUCTIVE = "DESTRUCTIVE"


class ChatMessage(BaseModel):
    role: str  # "user", "assistant", "system", "tool"
    content: str = ""
    timestamp: str = ""
    execution_id: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None


class SessionContext(BaseModel):
    selected_disaster_id: Optional[str] = None
    selected_drone_id: Optional[str] = None
    selected_survivor_id: Optional[str] = None
    selected_task_id: Optional[str] = None
    selected_region: Optional[str] = None
    last_world_version: int = 0


class ConversationSession(BaseModel):
    schema_version: str = "2.0.0"
    session_id: str
    created_at: str
    updated_at: str = ""
    provider_preference: ProviderMode = ProviderMode.AUTO
    mode: AgentMode = AgentMode.ASSISTED
    messages: List[ChatMessage] = Field(default_factory=list)
    execution_ids: List[str] = Field(default_factory=list)
    current_context: SessionContext = Field(default_factory=SessionContext)
    summary: str = ""
