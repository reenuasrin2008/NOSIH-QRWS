from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel

if not hasattr(BaseModel, "model_dump"):
    BaseModel.model_dump = BaseModel.dict  # type: ignore[attr-defined]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_dict(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, list):
        return [to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj
