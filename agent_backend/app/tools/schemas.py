"""Canonical ToolDefinition and strict JSON-schema argument validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from app.models.messages import PermissionLevel
from app.services.simulation_client import SimulationClient

ToolHandler = Callable[[SimulationClient, Dict[str, Any]], Awaitable[Dict[str, Any]]]


@dataclass
class ToolDefinition:
    name: str
    category: str
    description: str
    input_schema: Dict[str, Any]
    handler: ToolHandler
    permission_level: PermissionLevel = PermissionLevel.READ_ONLY
    timeout_seconds: float = 20.0
    idempotent: bool = True

    def to_canonical_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def validate_arguments(schema: Dict[str, Any], arguments: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate tool call arguments against JSON schema (required keys, types, ranges, additionalProperties)."""
    if not isinstance(arguments, dict):
        return False, "Tool arguments must be a JSON object."

    props = schema.get("properties") or {}
    required = schema.get("required") or []

    for req_key in required:
        if req_key not in arguments or arguments[req_key] is None:
            return False, f"Missing required argument '{req_key}'."

    if schema.get("additionalProperties") is False:
        unknown = [k for k in arguments.keys() if k not in props]
        if unknown:
            return False, f"Unexpected argument(s): {', '.join(unknown)}."

    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    for k, val in arguments.items():
        if k not in props or val is None:
            continue
        spec = props[k]
        expected = spec.get("type")
        if expected in type_map:
            if expected == "integer" and isinstance(val, bool):
                return False, f"Argument '{k}' must be an integer, not boolean."
            if expected == "number" and isinstance(val, bool):
                return False, f"Argument '{k}' must be a number, not boolean."
            if not isinstance(val, type_map[expected]):
                return False, f"Argument '{k}' must be of type '{expected}'."
        if "enum" in spec and val not in spec["enum"]:
            return False, f"Argument '{k}' must be one of {spec['enum']}."
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if "minimum" in spec and val < spec["minimum"]:
                return False, f"Argument '{k}'={val} is below minimum {spec['minimum']}."
            if "maximum" in spec and val > spec["maximum"]:
                return False, f"Argument '{k}'={val} exceeds maximum {spec['maximum']}."
    return True, None
