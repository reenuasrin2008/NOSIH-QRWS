from __future__ import annotations

from typing import Any, Callable, Dict, List, Set

from app.ai.tool_args import TOOL_ARGS_MODELS, TOOL_DESCRIPTIONS

_ID_FIELDS: Set[str] = {
    "country_id",
    "donor_country_id",
    "hospital_id",
    "drone_id",
    "district_id",
    "event_id",
    "road_id",
    "approval_id",
}


def classify_tool_category(name: str) -> str:
    if name.startswith("prepare_"):
        return "action"
    if name.startswith(("view_", "focus_")):
        return "navigation"
    if "route" in name or "multistop" in name or "compare_drones" in name:
        return "routing"
    if any(k in name for k in ("hospital", "ambulance", "bed")):
        return "medical"
    if any(k in name for k in ("shelter", "resource", "mutual_aid", "warehouse")):
        return "logistics"
    if any(k in name for k in ("drone", "swarm")):
        return "drone"
    if any(k in name for k in ("disaster", "cascade", "fire")):
        return "disaster"
    if any(k in name for k in ("audit", "event", "playbook", "approval", "save_world")):
        return "governance"
    return "world"


def wrap_validated_handler(
    tool_name: str,
    fn: Callable[[Dict[str, Any]], Any],
) -> Callable[[Dict[str, Any]], Any]:
    args_model = TOOL_ARGS_MODELS[tool_name]

    def _validated(raw_args: Dict[str, Any]) -> Any:
        parsed = args_model(**(raw_args or {}))
        return fn(parsed.to_handler_dict())

    return _validated


def build_tool_schemas() -> List[Dict[str, Any]]:
    schemas: List[Dict[str, Any]] = []
    for name, args_model in TOOL_ARGS_MODELS.items():
        is_action = name.startswith("prepare_")
        cat = classify_tool_category(name)
        params = args_model.json_schema_dict()
        params["additionalProperties"] = False
        schemas.append({
            "name": name,
            "description": TOOL_DESCRIPTIONS.get(name, ""),
            "parameters": params,
            "annotations": {
                "readOnlyHint": not is_action,
                "destructiveHint": is_action,
                "idempotentHint": not is_action,
                "openWorldHint": False,
            },
            "x-category": cat,
            "x-requiresApproval": is_action,
        })
    return schemas


def has_pattern_or_enum(prop: Dict[str, Any]) -> bool:
    if "pattern" in prop or "enum" in prop:
        return True
    for combiner in ("anyOf", "oneOf", "allOf"):
        branches = prop.get(combiner)
        if isinstance(branches, list):
            non_null = [b for b in branches if isinstance(b, dict) and b.get("type") != "null"]
            if non_null and all(has_pattern_or_enum(b) for b in non_null):
                return True
    return False


def _walk_objects(node: Any, tool_name: str, path: str = "") -> None:
    if not isinstance(node, dict):
        return
    if node.get("type") == "object":
        if node.get("additionalProperties") is not False:
            raise AssertionError(
                f"Tool '{tool_name}' schema at '{path or 'root'}' must set additionalProperties=False"
            )
        props = node.get("properties", {})
        if isinstance(props, dict):
            for k, v in props.items():
                sub_path = f"{path}.{k}" if path else k
                if k in _ID_FIELDS and isinstance(v, dict):
                    if not has_pattern_or_enum(v):
                        raise AssertionError(
                            f"Tool '{tool_name}' property '{sub_path}' must define pattern or enum"
                        )
                _walk_objects(v, tool_name, sub_path)
    if isinstance(node.get("items"), dict):
        _walk_objects(node["items"], tool_name, f"{path}[]" if path else "[]")
    for combiner in ("anyOf", "oneOf", "allOf"):
        branches = node.get(combiner)
        if isinstance(branches, list):
            for idx, branch in enumerate(branches):
                _walk_objects(branch, tool_name, f"{path}.{combiner}[{idx}]")


def assert_registry_integrity(
    tool_handlers: Dict[str, Callable[[Dict[str, Any]], Any]],
    tool_schema_map: Dict[str, Dict[str, Any]],
) -> None:
    handler_names = set(tool_handlers.keys())
    schema_names = set(tool_schema_map.keys())
    if handler_names != schema_names:
        raise AssertionError(
            f"Tool registry mismatch: handlers-schemas={handler_names - schema_names}, "
            f"schemas-handlers={schema_names - handler_names}"
        )

    for name, schema in tool_schema_map.items():
        params = schema.get("parameters", {})
        _walk_objects(params, name)
        annotations = schema.get("annotations", {})
        requires_approval = schema.get("x-requiresApproval", annotations.get("requiresApproval"))
        if name.startswith("prepare_") and requires_approval is not True:
            raise AssertionError(f"Action tool '{name}' must have x-requiresApproval=True")


def build_tool_registry(
    tool_handlers: Dict[str, Callable[[Dict[str, Any]], Any]],
    tool_schema_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    meta: Dict[str, Dict[str, Any]] = {}
    for name in tool_handlers:
        schema = tool_schema_map.get(name, {})
        annotations = schema.get("annotations", {})
        is_action = bool(
            schema.get("x-requiresApproval", annotations.get("requiresApproval", name.startswith("prepare_")))
        )
        cat = schema.get("x-category", annotations.get("category", classify_tool_category(name)))
        meta[name] = {
            "tool_name": name,
            "category": cat,
            "description": schema.get("description", ""),
            "parameters": schema.get("parameters", {"type": "object", "properties": {}, "required": [], "additionalProperties": False}),
            "annotations": annotations,
            "read_only": not is_action,
            "requires_approval": is_action,
            "callable": True,
        }
    return meta
