"""Allowlist validation, JSON-schema checking, and idempotency deduplication."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional, Tuple

from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolDefinition, validate_arguments


class OperationValidator:
    """Validates tool names against allowlist, checks JSON schemas, and prevents duplicate mutations."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._idempotency_cache: Dict[str, Dict[str, Any]] = {}

    def validate(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, Optional[ToolDefinition], Optional[str]]:
        tool = self.registry.get(tool_name)
        if tool is None:
            return False, None, f"Tool '{tool_name}' is not in the registered allowlist."
        ok, err = validate_arguments(tool.input_schema, arguments)
        if not ok:
            return False, tool, f"Invalid arguments for '{tool_name}': {err}"
        return True, tool, None

    @staticmethod
    def build_idempotency_key(execution_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        raw = json.dumps({"exec": execution_id, "tool": tool_name, "args": arguments}, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def get_cached_result(self, key: str) -> Optional[Dict[str, Any]]:
        return self._idempotency_cache.get(key)

    def store_result(self, key: str, result: Dict[str, Any]) -> None:
        self._idempotency_cache[key] = result
        if len(self._idempotency_cache) > 400:
            oldest = next(iter(self._idempotency_cache))
            self._idempotency_cache.pop(oldest, None)
