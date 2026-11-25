"""Abstract base provider interface for model-native function calling."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from app.models.actions import ProviderResponse


class BaseAIProvider(ABC):
    provider_name: str = ""

    @abstractmethod
    async def generate_with_tools(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        timeout_seconds: float = 45.0,
    ) -> ProviderResponse:
        """Send messages + canonical tool schemas and return parsed native tool calls or text."""

    @abstractmethod
    def status(self) -> Dict[str, Any]:
        """Return provider and key-rotator health without exposing raw API keys."""
