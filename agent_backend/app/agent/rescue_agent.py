"""Autonomous AI Rescue Command Agent with genuine multi-step model-native function calling."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.agent.action_executor import ActionExecutor
from app.agent.memory import ConversationMemoryStore
from app.agent.operation_validator import OperationValidator
from app.agent.permission_manager import PermissionManager
from app.agent.state_observer import StateObserver
from app.config import AgentSettings
from app.models.actions import PendingAction, ProviderResponse
from app.models.execution import ExecutionTrace, ToolExecutionRecord
from app.models.messages import AgentMode, ChatMessage, ConversationSession, ProviderMode
from app.providers.key_rotator import ProviderError
from app.providers.provider_manager import ProviderManager
from app.services.execution_logger import AgentEventHub, ExecutionLogger
from app.services.simulation_client import SimulationClient
from app.tools.registry import ToolRegistry


SYSTEM_PROMPT_TEMPLATE = """You are the QUANTUM RESCUE V2 Autonomous Emergency Command AI operating a live 4x4 km metropolitan disaster-response digital twin.

OPERATIONAL RULES (STRICT):
1. You operate the live simulation ONLY through the registered structured function calls provided to you.
2. NEVER pretend, claim, or imply that any disaster was created, drone was dispatched, route was validated, or survivor was rescued unless you actually called the tool AND received a verified success result from the simulation backend.
3. All survivors in this environment are simulated digital-twin entities; never claim to detect real human beings.
4. Always use exact IDs (e.g., DIS-0001, SUR-0001, D-01, T-001) and valid coordinates inside [0, 4000] x [0, 4000] meters.
5. For multi-step rescue operations (e.g., analyzing disasters and dispatching drones), call observation tools first, validate routes/drones, create or assign rescue tasks, and verify the resulting state.
6. If a tool returns an error or requires operator approval, report it accurately and clearly distinguish:
   - What was recommended
   - What was actually executed
   - What was verified in the live simulation
   - What remains pending or failed
7. Resolve follow-up references like "it", "that flood", or "that drone" using the session_context below; if genuinely ambiguous, ask the operator.

CURRENT OPERATING MODE: {mode}
LIVE AUTHORITATIVE WORLD CONTEXT:
{world_context_json}
"""


class RescueAgent:
    """Orchestrates multi-step model-native tool calling, permissions, cancellation, and verification."""

    def __init__(
        self,
        settings: AgentSettings,
        provider_manager: ProviderManager,
        sim_client: SimulationClient,
        registry: ToolRegistry,
        memory: ConversationMemoryStore,
        logger: ExecutionLogger,
        event_hub: AgentEventHub,
    ):
        self.settings = settings
        self.providers = provider_manager
        self.sim = sim_client
        self.registry = registry
        self.memory = memory
        self.logger = logger
        self.event_hub = event_hub

        self.permissions = PermissionManager(confirm_destructive=settings.confirm_destructive_actions)
        self.validator = OperationValidator(registry)
        self.observer = StateObserver(sim_client)
        self.executor = ActionExecutor(sim_client, self.validator, logger, event_hub)

        self.mode: AgentMode = AgentMode(settings.default_agent_mode)
        self.paused: bool = False
        self._cancel_event: asyncio.Event = asyncio.Event()
        self._active_execution_id: Optional[str] = None
        self._pending_traces: Dict[str, ExecutionTrace] = {}
        self._last_verified_at: Optional[str] = None

    def set_mode(self, mode: AgentMode) -> None:
        self.mode = mode

    def pause(self) -> Dict[str, Any]:
        self.paused = True
        self.logger.append_audit("agent_paused", {"mode": self.mode.value})
        return {"paused": True, "mode": self.mode.value}

    def resume(self) -> Dict[str, Any]:
        self.paused = False
        self.logger.append_audit("agent_resumed", {"mode": self.mode.value})
        return {"paused": False, "mode": self.mode.value}

    def stop_current_execution(self) -> Dict[str, Any]:
        """Interrupt active execution: halt further model calls and queued tools without falsifying completed ones."""
        self._cancel_event.set()
        stopped_id = self._active_execution_id
        self.logger.append_audit("execution_interrupted", {"execution_id": stopped_id})
        return {"stop_requested": True, "active_execution_id": stopped_id}

    def runtime_status(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "paused": self.paused,
            "active_execution_id": self._active_execution_id,
            "pending_approvals_count": sum(
                1 for tr in self._pending_traces.values()
                if any(a.status == "PENDING_APPROVAL" for a in tr.pending_actions)
            ),
            "last_verified_at": self._last_verified_at,
            "registered_tools_count": len(self.registry.list_names()),
            "providers": self.providers.status(),
        }

    def _build_model_messages(self, session: ConversationSession, user_message: str) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = []
        if session.summary:
            msgs.append({"role": "user", "content": f"[Earlier operational summary: {session.summary}]"})
        for m in session.messages[-16:]:
            if m.role in ("user", "assistant") and m.content:
                msgs.append({"role": m.role, "content": m.content})
        msgs.append({"role": "user", "content": user_message})
        return msgs

    async def handle_user_command(
        self,
        user_message: str,
        *,
        session_id: Optional[str] = None,
        mode_override: Optional[AgentMode] = None,
        provider_override: Optional[ProviderMode] = None,
    ) -> ExecutionTrace:
        session = self.memory.load_session(session_id)
        active_mode = mode_override or self.mode
        active_prov_mode = provider_override or self.providers.mode

        exec_id = f"EXEC-{uuid.uuid4().hex[:8].upper()}"
        t0 = time.perf_counter()
        started_iso = datetime.now(timezone.utc).isoformat()

        self._cancel_event.clear()
        self._active_execution_id = exec_id

        trace = ExecutionTrace(
            execution_id=exec_id,
            session_id=session.session_id,
            user_message=user_message,
            mode=active_mode.value,
            provider_mode=active_prov_mode.value,
            started_at=started_iso,
            status="RUNNING",
        )
        await self.event_hub.broadcast("execution_started", {
            "execution_id": exec_id,
            "session_id": session.session_id,
            "mode": active_mode.value,
            "user_message": user_message,
        })

        # Step 1: Observe live authoritative world context
        world_ctx = await self.observer.build_compact_context(session.current_context)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            mode=active_mode.value,
            world_context_json=json.dumps(world_ctx, indent=2),
        )
        model_messages = self._build_model_messages(session, user_message)
        tool_schemas = self.registry.canonical_schemas()

        tool_calls_executed = 0
        max_steps = self.settings.max_tool_calls_per_turn

        try:
            while tool_calls_executed < max_steps:
                if self._cancel_event.is_set():
                    trace.status = "INTERRUPTED"
                    trace.incomplete.append("Execution was interrupted by the operator; no further model calls or queued tools were run.")
                    trace.final_response = "Execution interrupted by operator. Already completed operations remain recorded in the execution trace."
                    break

                # Step 2: Call real AI provider with native tool schemas
                resp: ProviderResponse = await self.providers.generate_with_tools(
                    system_prompt=system_prompt,
                    messages=model_messages,
                    tool_schemas=tool_schemas,
                    mode_override=active_prov_mode,
                    timeout_seconds=self.settings.model_timeout_seconds,
                )
                trace.provider_used = resp.provider
                trace.key_alias_used = resp.key_alias
                if resp.switched_from:
                    switch_note = f"Switched from {resp.switched_from} to {resp.provider} ({resp.key_alias})"
                    trace.provider_switches.append(switch_note)
                    await self.event_hub.broadcast("provider_switched", {"execution_id": exec_id, "detail": switch_note})

                # No tool calls -> model produced final response
                if not resp.tool_calls:
                    trace.final_response = resp.text or "No further actions required."
                    trace.status = "PENDING_APPROVAL" if any(a.status == "PENDING_APPROVAL" for a in trace.pending_actions) else "COMPLETED"
                    break

                # Record assistant's structured tool-call turn in model message history
                model_messages.append({
                    "role": "assistant",
                    "content": resp.text,
                    "tool_calls": [tc.model_dump() for tc in resp.tool_calls],
                })

                # Step 3: Fast-path parallel execution when all tool calls in this turn are valid READ_ONLY calls
                all_read_only = (
                    len(resp.tool_calls) > 1
                    and not self._cancel_event.is_set()
                    and all(
                        (self.validator.validate(tc.name, tc.arguments)[0])
                        and (self.registry.get(tc.name) is not None)
                        and (self.registry.get(tc.name).permission_level.value == "READ_ONLY")
                        for tc in resp.tool_calls
                    )
                    and (tool_calls_executed + len(resp.tool_calls) <= max_steps)
                )
                if all_read_only:
                    tool_calls_executed += len(resp.tool_calls)
                    coros = [
                        self.executor.execute_tool(
                            execution_id=exec_id,
                            tool_call_id=tc.tool_call_id,
                            tool=self.registry.get(tc.name),
                            arguments=tc.arguments,
                            provider=resp.provider,
                            key_alias=resp.key_alias,
                            session_ctx=session.current_context,
                        )
                        for tc in resp.tool_calls
                    ]
                    recs = await asyncio.gather(*coros)
                    for tc, rec in zip(resp.tool_calls, recs):
                        trace.tool_records.append(rec)
                        if rec.status == "SUCCESS":
                            trace.executed.append(f"{tc.name} (ver {rec.state_version_before}->{rec.state_version_after})")
                            self._last_verified_at = rec.completed_at
                            trace.verified.append(f"{tc.name} verified at world version {rec.state_version_after}")
                        else:
                            trace.incomplete.append(f"{tc.name} failed: {rec.error}")
                        model_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.tool_call_id,
                            "tool_name": tc.name,
                            "content": json.dumps({
                                "success": rec.status == "SUCCESS",
                                "tool": tc.name,
                                "execution_id": exec_id,
                                "result": rec.result,
                                "error": rec.error,
                                "state_version": rec.state_version_after,
                            }, default=str),
                        })
                    continue

                # Step 3b: Validate, permission-check, and execute each tool call sequentially
                for tc in resp.tool_calls:
                    if self._cancel_event.is_set():
                        trace.status = "INTERRUPTED"
                        trace.incomplete.append(f"Queued tool '{tc.name}' skipped due to operator stop.")
                        break

                    if tool_calls_executed >= max_steps:
                        trace.incomplete.append(f"Maximum tool-call limit ({max_steps}) reached before '{tc.name}'.")
                        break

                    tool_calls_executed += 1
                    ok, tool_def, val_err = self.validator.validate(tc.name, tc.arguments)
                    if not ok or tool_def is None:
                        rec = ToolExecutionRecord(
                            execution_id=exec_id,
                            tool_call_id=tc.tool_call_id,
                            tool=tc.name,
                            provider=resp.provider,
                            key_alias=resp.key_alias,
                            status="REJECTED",
                            started_at=datetime.now(timezone.utc).isoformat(),
                            completed_at=datetime.now(timezone.utc).isoformat(),
                            arguments=tc.arguments,
                            error=val_err,
                        )
                        trace.tool_records.append(rec)
                        trace.incomplete.append(f"{tc.name}: {val_err}")
                        model_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.tool_call_id,
                            "tool_name": tc.name,
                            "content": json.dumps({"success": False, "error": val_err}),
                        })
                        continue

                    perm = self.permissions.evaluate(active_mode, tool_def)
                    if perm.decision == "DENY":
                        rec = ToolExecutionRecord(
                            execution_id=exec_id,
                            tool_call_id=tc.tool_call_id,
                            tool=tc.name,
                            provider=resp.provider,
                            key_alias=resp.key_alias,
                            status="REJECTED",
                            started_at=datetime.now(timezone.utc).isoformat(),
                            completed_at=datetime.now(timezone.utc).isoformat(),
                            arguments=tc.arguments,
                            error=perm.reason,
                        )
                        trace.tool_records.append(rec)
                        trace.recommended.append(f"{tc.name}({json.dumps(tc.arguments)})")
                        trace.incomplete.append(perm.reason)
                        model_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.tool_call_id,
                            "tool_name": tc.name,
                            "content": json.dumps({"success": False, "blocked_by_mode": True, "error": perm.reason}),
                        })
                        continue

                    if perm.decision == "REQUIRE_APPROVAL":
                        action = PendingAction(
                            action_id=f"ACT-{uuid.uuid4().hex[:6].upper()}",
                            tool_call_id=tc.tool_call_id,
                            tool_name=tc.name,
                            arguments=tc.arguments,
                            permission_level=tool_def.permission_level,
                            reason=perm.reason,
                        )
                        trace.pending_actions.append(action)
                        trace.recommended.append(f"{tc.name}({json.dumps(tc.arguments)})")
                        rec = ToolExecutionRecord(
                            execution_id=exec_id,
                            tool_call_id=tc.tool_call_id,
                            tool=tc.name,
                            provider=resp.provider,
                            key_alias=resp.key_alias,
                            status="PENDING_APPROVAL",
                            started_at=datetime.now(timezone.utc).isoformat(),
                            completed_at=datetime.now(timezone.utc).isoformat(),
                            arguments=tc.arguments,
                            result={"status": "PENDING_APPROVAL", "action_id": action.action_id, "reason": perm.reason},
                        )
                        trace.tool_records.append(rec)
                        await self.event_hub.broadcast("approval_required", {
                            "execution_id": exec_id,
                            "action": action.model_dump(),
                        })
                        model_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.tool_call_id,
                            "tool_name": tc.name,
                            "content": json.dumps({
                                "success": False,
                                "pending_operator_approval": True,
                                "action_id": action.action_id,
                                "reason": perm.reason,
                            }),
                        })
                        continue

                    # Execute the real validated Python tool handler against port 8000
                    rec = await self.executor.execute_tool(
                        execution_id=exec_id,
                        tool_call_id=tc.tool_call_id,
                        tool=tool_def,
                        arguments=tc.arguments,
                        provider=resp.provider,
                        key_alias=resp.key_alias,
                        session_ctx=session.current_context,
                    )
                    trace.tool_records.append(rec)
                    if rec.status == "SUCCESS":
                        trace.executed.append(f"{tc.name} (ver {rec.state_version_before}->{rec.state_version_after})")
                        if rec.state_version_after >= rec.state_version_before:
                            self._last_verified_at = rec.completed_at
                            trace.verified.append(f"{tc.name} verified at world version {rec.state_version_after}")
                    else:
                        trace.incomplete.append(f"{tc.name} failed: {rec.error}")

                    tool_return_payload = {
                        "success": rec.status == "SUCCESS",
                        "tool": tc.name,
                        "execution_id": exec_id,
                        "result": rec.result,
                        "error": rec.error,
                        "state_version": rec.state_version_after,
                    }
                    model_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.tool_call_id,
                        "tool_name": tc.name,
                        "content": json.dumps(tool_return_payload, default=str),
                    })

                if trace.status == "INTERRUPTED":
                    break
            else:
                trace.status = "COMPLETED"
                trace.incomplete.append(f"Reached max tool calls per turn ({max_steps}).")
                trace.final_response = "Completed maximum tool calls for this turn. Review the execution receipts above for verified results."

        except ProviderError as exc:
            trace.status = "FAILED"
            trace.error = str(exc)
            trace.incomplete.append(str(exc))
            trace.final_response = f"AI Provider Error ({exc.provider} / {exc.kind.value}): {exc}"
        except Exception as exc:
            trace.status = "FAILED"
            trace.error = str(exc)
            trace.incomplete.append(str(exc))
            trace.final_response = f"Execution Error: {exc}"
        finally:
            trace.completed_at = datetime.now(timezone.utc).isoformat()
            trace.duration_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            self._active_execution_id = None

        if any(a.status == "PENDING_APPROVAL" for a in trace.pending_actions):
            self._pending_traces[exec_id] = trace

        # Persist conversation & execution trace to plain JSON
        session.mode = active_mode
        session.provider_preference = active_prov_mode
        if exec_id not in session.execution_ids:
            session.execution_ids.append(exec_id)
        self.memory.append_message(session, ChatMessage(role="user", content=user_message, execution_id=exec_id))
        self.memory.append_message(session, ChatMessage(role="assistant", content=trace.final_response, execution_id=exec_id))
        self.logger.save_execution(trace)
        await self.event_hub.broadcast("execution_completed", trace.model_dump())
        return trace

    async def approve_pending_actions(self, execution_id: str, action_ids: Optional[List[str]] = None) -> ExecutionTrace:
        trace = self._pending_traces.get(execution_id)
        if not trace:
            raise KeyError(f"No pending approval trace found for {execution_id}")
        session = self.memory.load_session(trace.session_id)

        for action in trace.pending_actions:
            if action.status != "PENDING_APPROVAL":
                continue
            if action_ids and action.action_id not in action_ids:
                continue
            ok, tool_def, err = self.validator.validate(action.tool_name, action.arguments)
            if not ok or tool_def is None:
                action.status = "FAILED"
                action.error = err
                continue
            rec = await self.executor.execute_tool(
                execution_id=trace.execution_id,
                tool_call_id=action.tool_call_id,
                tool=tool_def,
                arguments=action.arguments,
                provider=trace.provider_used or "OPERATOR_APPROVED",
                key_alias=trace.key_alias_used or "OPERATOR",
                session_ctx=session.current_context,
            )
            trace.tool_records.append(rec)
            if rec.status == "SUCCESS":
                action.status = "EXECUTED"
                action.result = rec.result
                trace.executed.append(f"{action.tool_name} (approved, ver {rec.state_version_before}->{rec.state_version_after})")
                trace.verified.append(f"{action.tool_name} verified at world version {rec.state_version_after}")
                self._last_verified_at = rec.completed_at
            else:
                action.status = "FAILED"
                action.error = rec.error
                trace.incomplete.append(f"{action.tool_name} failed: {rec.error}")

        if not any(a.status == "PENDING_APPROVAL" for a in trace.pending_actions):
            trace.status = "COMPLETED"
            self._pending_traces.pop(execution_id, None)
        self.memory.save_session(session)
        self.logger.save_execution(trace)
        await self.event_hub.broadcast("approval_executed", trace.model_dump())
        return trace

    async def reject_pending_actions(self, execution_id: str) -> ExecutionTrace:
        trace = self._pending_traces.pop(execution_id, None)
        if not trace:
            raise KeyError(f"No pending approval trace found for {execution_id}")
        for action in trace.pending_actions:
            if action.status == "PENDING_APPROVAL":
                action.status = "REJECTED"
                trace.incomplete.append(f"{action.tool_name} rejected by operator.")
        trace.status = "COMPLETED"
        self.logger.save_execution(trace)
        await self.event_hub.broadcast("approval_rejected", {"execution_id": execution_id})
        return trace

    async def on_meaningful_world_event(self, event_msg: Dict[str, Any]) -> None:
        """React to live WebSocket disaster/failure events from port 8000."""
        await self.event_hub.broadcast("world_alert", event_msg)
        if self.paused or self.mode != AgentMode.AUTONOMOUS:
            return
        if self._active_execution_id is not None:
            return
        if not (self.providers.grok.rotator.has_available_keys() or self.providers.gemini.rotator.has_available_keys()):
            return
        ev_type = event_msg.get("event_type", "world_change")
        prompt = (
            f"AUTONOMOUS ALERT: Live simulation reported '{ev_type}' at world version "
            f"{event_msg.get('state_version')}. Inspect affected disasters, survivors, and available drones, "
            f"then dispatch or optimize rescue operations safely."
        )
        await self.handle_user_command(prompt, mode_override=AgentMode.AUTONOMOUS)
