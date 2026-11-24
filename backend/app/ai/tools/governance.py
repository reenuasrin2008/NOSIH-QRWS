from __future__ import annotations

from collections import deque
import os
from typing import Any, Callable, Dict

from app.approvals.engine import PLAYBOOK_CATALOG, ApprovalEngine
from app.core.compat import to_dict
from app.database.repository import ExperimentRepository
from app.world.global_engine import GlobalWorldEngine


def build_handlers(
    world: GlobalWorldEngine,
    approval_engine: ApprovalEngine,
    tool_logs: deque,
) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    def _get_audit_logs(args: Dict[str, Any]) -> Dict[str, Any]:
        limit = max(1, int(args.get("limit", 50)))
        return {
            "audit_log": list(approval_engine.audit_log)[-limit:],
            "tool_logs": list(tool_logs)[-limit:],
            "audit_count": len(approval_engine.audit_log),
            "tool_log_count": len(tool_logs),
        }

    def _list_pending_approvals(args: Dict[str, Any]) -> Dict[str, Any]:
        aid = args.get("approval_id")
        if aid:
            req = approval_engine.approvals.get(aid)
            return {"approvals": [to_dict(req)] if req else []}
        return {"approvals": approval_engine.list_approvals(status=args.get("status", "PENDING"))}

    def _save_world_local(args: Dict[str, Any]) -> Dict[str, Any]:
        raw_name = str(args.get("filename", "world_snapshot.json"))
        filename = os.path.basename(raw_name.replace("\\", "/")).strip() or "world_snapshot.json"
        repo = ExperimentRepository()
        path = repo.save_local_world_snapshot(world.get_global_overview(), filename=filename)
        return {"saved": True, "storage": "local_json", "path": path, "world_version": world.event_bus.world_version}

    return {
        "list_playbooks": lambda a: {"playbooks": PLAYBOOK_CATALOG, "count": len(PLAYBOOK_CATALOG)},
        "get_event_timeline": lambda a: {
            "world_version": world.event_bus.world_version,
            "events": world.event_bus.get_events(
                limit=int(a.get("limit", 40)),
                category=a.get("category"),
                country_id=a.get("country_id"),
            ),
        },
        "get_audit_logs": _get_audit_logs,
        "list_pending_approvals": _list_pending_approvals,
        "save_world_local": _save_world_local,
    }
