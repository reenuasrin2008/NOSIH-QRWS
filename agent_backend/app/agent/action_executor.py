"""Validated, lock-serialized tool execution engine with real simulation calls and receipts."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.agent.operation_validator import OperationValidator
from app.models.execution import ToolExecutionRecord
from app.models.messages import PermissionLevel, SessionContext
from app.services.execution_logger import AgentEventHub, ExecutionLogger
from app.services.simulation_client import SimulationAPIError, SimulationClient
from app.tools.schemas import ToolDefinition


class ActionExecutor:
    """Executes validated tools against the live simulation API (:8000) and records verifiable receipts."""

    def __init__(
        self,
        sim_client: SimulationClient,
        validator: OperationValidator,
        logger: ExecutionLogger,
        event_hub: AgentEventHub,
    ):
        self.sim = sim_client
        self.validator = validator
        self.logger = logger
        self.event_hub = event_hub
        self._mutation_lock = asyncio.Lock()

    async def execute_tool(
        self,
        *,
        execution_id: str,
        tool_call_id: str,
        tool: ToolDefinition,
        arguments: Dict[str, Any],
        provider: str,
        key_alias: str,
        session_ctx: SessionContext,
    ) -> ToolExecutionRecord:
        started_iso = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()

        # Idempotency check for non-idempotent mutations within the same execution
        idem_key = self.validator.build_idempotency_key(execution_id, tool.name, arguments)
        if not tool.idempotent:
            cached = self.validator.get_cached_result(idem_key)
            if cached is not None:
                return ToolExecutionRecord(
                    execution_id=execution_id,
                    tool_call_id=tool_call_id,
                    tool=tool.name,
                    provider=provider,
                    key_alias=key_alias,
                    status="SUCCESS",
                    started_at=started_iso,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    duration_ms=0.0,
                    arguments=arguments,
                    result={"deduplicated": True, **cached},
                )

        await self.event_hub.broadcast("tool_started", {
            "execution_id": execution_id,
            "tool_call_id": tool_call_id,
            "tool": tool.name,
            "category": tool.category,
            "arguments": arguments,
            "provider": provider,
            "key_alias": key_alias,
        })

        async def _run() -> ToolExecutionRecord:
            ver_before = await self.sim.get_world_version()
            try:
                raw_res = await asyncio.wait_for(tool.handler(self.sim, arguments), timeout=tool.timeout_seconds)
                ver_after = await self.sim.get_world_version()
                dur_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                result_dict = raw_res if isinstance(raw_res, dict) else {"value": raw_res}

                if not tool.idempotent:
                    self.validator.store_result(idem_key, result_dict)

                self._update_session_context(tool.name, arguments, result_dict, session_ctx, ver_after)
                await self._emit_3d_visual_feedback(tool.name, arguments, result_dict)


                rec = ToolExecutionRecord(
                    execution_id=execution_id,
                    tool_call_id=tool_call_id,
                    tool=tool.name,
                    provider=provider,
                    key_alias=key_alias,
                    status="SUCCESS",
                    started_at=started_iso,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    duration_ms=dur_ms,
                    state_version_before=ver_before,
                    state_version_after=ver_after,
                    arguments=arguments,
                    result=result_dict,
                    error=None,
                )
            except asyncio.TimeoutError:
                dur_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                rec = ToolExecutionRecord(
                    execution_id=execution_id,
                    tool_call_id=tool_call_id,
                    tool=tool.name,
                    provider=provider,
                    key_alias=key_alias,
                    status="FAILED",
                    started_at=started_iso,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    duration_ms=dur_ms,
                    state_version_before=ver_before,
                    state_version_after=ver_before,
                    arguments=arguments,
                    error=f"Tool '{tool.name}' timed out after {tool.timeout_seconds}s.",
                )
            except (SimulationAPIError, Exception) as exc:
                dur_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                rec = ToolExecutionRecord(
                    execution_id=execution_id,
                    tool_call_id=tool_call_id,
                    tool=tool.name,
                    provider=provider,
                    key_alias=key_alias,
                    status="FAILED",
                    started_at=started_iso,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    duration_ms=dur_ms,
                    state_version_before=ver_before,
                    state_version_after=ver_before,
                    arguments=arguments,
                    error=str(exc),
                )

            self.logger.append_audit("tool_executed", rec.model_dump())
            await self.event_hub.broadcast("tool_completed", rec.model_dump())
            return rec

        if tool.permission_level == PermissionLevel.READ_ONLY:
            return await _run()
        async with self._mutation_lock:
            return await _run()

    @staticmethod
    def _update_session_context(
        tool_name: str,
        arguments: Dict[str, Any],
        result: Dict[str, Any],
        ctx: SessionContext,
        ver_after: int,
    ) -> None:
        ctx.last_world_version = ver_after
        if "event_id" in arguments:
            ctx.selected_disaster_id = str(arguments["event_id"])
        elif isinstance(result.get("disaster"), dict) and result["disaster"].get("event_id"):
            ctx.selected_disaster_id = str(result["disaster"]["event_id"])
        if "drone_id" in arguments:
            ctx.selected_drone_id = str(arguments["drone_id"])
        if "survivor_id" in arguments:
            ctx.selected_survivor_id = str(arguments["survivor_id"])
        if "task_id" in arguments:
            ctx.selected_task_id = str(arguments["task_id"])
        elif result.get("task_id"):
            ctx.selected_task_id = str(result["task_id"])

    async def _emit_3d_visual_feedback(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any]) -> None:
        try:
            if tool_name == "search_area_for_survivors":
                await self.sim.post("/api/ui/sync", json_body={
                    "action": "ai_scan_pulse",
                    "payload": {"point": [float(arguments["x"]), 8.0, float(arguments["z"])], "radius": float(arguments.get("radius", 400.0)), "label": "AI THERMAL SCAN"},
                })
            elif tool_name == "assign_drone_to_task" and result.get("ok"):
                d = await self.sim.get(f"/api/drones/{arguments['drone_id']}")
                t = await self.sim.get(f"/api/tasks/{arguments['task_id']}")
                await self.sim.post("/api/ui/sync", json_body={
                    "action": "ai_dispatch_beam",
                    "payload": {"from": d["position"], "to": t["location"], "drone_id": d["id"], "task_id": t["id"]},
                })
        except Exception:
            pass
