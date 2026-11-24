from __future__ import annotations

from collections import deque
import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.ai.entities import (
    _RE_BATTERY_PCT,
    _RE_DRONE_ID,
    build_country_lookup,
    extract_entities,
    resolve_country,
)
from app.ai.formatters import (
    JarvisReply,
    ToolTraceEntry,
    execute_intent,
    summarize_result,
)
from app.ai.intents import recognize_intents
from app.ai.registry import (
    _ID_FIELDS,
    _walk_objects,
    assert_registry_integrity,
    build_tool_registry,
    build_tool_schemas,
    classify_tool_category,
    has_pattern_or_enum,
    wrap_validated_handler,
)
from app.ai.session import (
    MAX_SESSIONS,
    SessionContext,
    evict_stale_sessions,
    get_or_create_session,
)
from app.ai.tools import build_all_tool_handlers
from app.approvals.engine import ApprovalEngine
from app.core.compat import utc_now_iso
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.providers.ai_providers import AIProviderManager
from app.world.global_engine import GlobalWorldEngine

logger = logging.getLogger("jarvis")

MAX_MESSAGE_LENGTH = 4000


class JarvisAgent:
    """Fast Universal Command Orchestrator with 50 real callable backend tools & multi-intent routing."""

    def __init__(
        self,
        world: GlobalWorldEngine,
        route_explorer: AdvancedRouteExplorer,
        approval_engine: ApprovalEngine,
        provider_manager: AIProviderManager,
    ) -> None:
        self.world = world
        self.route_explorer = route_explorer
        self.approval_engine = approval_engine
        self.provider_manager = provider_manager
        self.sessions: Dict[str, SessionContext] = {}
        self.conversations: Dict[str, deque] = {}
        self.tool_logs: deque = deque(maxlen=2000)
        self._country_lookup: List[Tuple[str, str]] = self._build_country_lookup()
        self._tool_schemas: List[Dict[str, Any]] = self._build_tool_schemas()
        self._tool_schema_map: Dict[str, Dict[str, Any]] = {s["name"]: s for s in self._tool_schemas}
        self._tool_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = self._build_tool_handlers()
        self.registry: Dict[str, Dict[str, Any]] = self._build_tool_registry()
        self._assert_registry_integrity()

    @property
    def tool_count(self) -> int:
        return len(self._tool_schemas)

    def _build_country_lookup(self) -> List[Tuple[str, str]]:
        return build_country_lookup(self.world)

    def _get_session(self, session_id: str) -> SessionContext:
        return get_or_create_session(
            self.sessions,
            self.conversations,
            session_id=session_id,
            default_country_id=self.world.selected_country_id,
            valid_countries=self.world.countries,
            max_sessions=MAX_SESSIONS,
        )

    def _evict_stale_sessions(self, max_age_seconds: float = 3600.0) -> int:
        return evict_stale_sessions(self.sessions, self.conversations, max_age_seconds=max_age_seconds)

    # ------------------------------------------------------------------
    # Tool Handlers, Schemas & Registry Integrity
    # ------------------------------------------------------------------
    def _build_tool_handlers(self) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
        raw_handlers = build_all_tool_handlers(
            self.world,
            self.route_explorer,
            self.approval_engine,
            self.tool_logs,
        )
        return {name: wrap_validated_handler(name, fn) for name, fn in raw_handlers.items()}

    @staticmethod
    def _classify_tool_category(name: str) -> str:
        return classify_tool_category(name)

    def _build_tool_schemas(self) -> List[Dict[str, Any]]:
        return build_tool_schemas()

    @staticmethod
    def _has_pattern_or_enum(prop: Dict[str, Any]) -> bool:
        return has_pattern_or_enum(prop)

    def _assert_registry_integrity(self) -> None:
        assert_registry_integrity(self._tool_handlers, self._tool_schema_map)

    def get_tool_schemas(self, categories: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        """Return clean JSON-Schema tool definitions compatible with Gemini function_declarations and Grok/OpenAI tools."""
        if categories is None:
            return [dict(s) for s in self._tool_schemas]
        return [
            dict(s)
            for s in self._tool_schemas
            if s.get("x-category", s.get("annotations", {}).get("category")) in categories
        ]

    def _build_tool_registry(self) -> Dict[str, Dict[str, Any]]:
        return build_tool_registry(self._tool_handlers, self._tool_schema_map)

    def _tool_category(self, tool_name: str) -> str:
        schema = self._tool_schema_map.get(tool_name, {})
        return str(schema.get("x-category", schema.get("annotations", {}).get("category", "unknown")))

    # ------------------------------------------------------------------
    # Tool Execution & Tracing
    # ------------------------------------------------------------------
    @staticmethod
    def _is_tool_error(res: Any) -> bool:
        return isinstance(res, dict) and res.get("status") == "ERROR" and "error" in res

    def _summarize_result(self, tool_name: str, res: Any) -> str:
        return summarize_result(tool_name, res)

    def execute_tool_direct(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Direct fast execution endpoint for any registered JARVIS tool (never raises)."""
        if tool_name not in self._tool_handlers:
            logger.warning("tool_err tool=%s duration_ms=0.00 error=Unknown tool", tool_name)
            return {
                "tool": tool_name,
                "duration_ms": 0.0,
                "status": "ERROR",
                "error": f"Unknown tool: {tool_name}",
            }
        t0 = time.perf_counter()
        started = utc_now_iso()
        call_args = args or {}
        try:
            result = self._tool_handlers[tool_name](call_args)
            dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if self._is_tool_error(result):
                cat = result.get("category") or self._tool_category(tool_name)
                entry: ToolTraceEntry = {
                    "timestamp": started,
                    "tool": tool_name,
                    "arguments": call_args,
                    "duration_ms": dur_ms,
                    "status": "ERROR",
                    "summary": str(result.get("error", "unknown error")),
                    "category": cat,
                }
                self.tool_logs.append(entry)
                logger.warning("tool_err tool=%s duration_ms=%.2f error=%s", tool_name, dur_ms, result.get("error"))
                return {
                    "tool": tool_name,
                    "duration_ms": dur_ms,
                    "status": "ERROR",
                    "error": str(result.get("error", "unknown error")),
                    "result": result,
                    "trace_entry": entry,
                }
            entry = {
                "timestamp": started,
                "tool": tool_name,
                "arguments": call_args,
                "duration_ms": dur_ms,
                "status": "OK",
                "summary": self._summarize_result(tool_name, result),
            }
            self.tool_logs.append(entry)
            logger.debug("tool_ok tool=%s duration_ms=%.2f", tool_name, dur_ms)
            return {"tool": tool_name, "duration_ms": dur_ms, "status": "OK", "result": result, "trace_entry": entry}
        except Exception as exc:
            dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            cat = self._tool_category(tool_name)
            entry = {
                "timestamp": started,
                "tool": tool_name,
                "arguments": call_args,
                "duration_ms": dur_ms,
                "status": "ERROR",
                "summary": str(exc),
                "category": cat,
            }
            self.tool_logs.append(entry)
            logger.warning("tool_err tool=%s duration_ms=%.2f error=%s", tool_name, dur_ms, exc)
            return {
                "tool": tool_name,
                "duration_ms": dur_ms,
                "status": "ERROR",
                "error": str(exc),
                "trace_entry": entry,
            }

    def _run_tool(self, trace: List[ToolTraceEntry], tool_name: str, args: Dict[str, Any]) -> Any:
        t0 = time.perf_counter()
        started = utc_now_iso()
        try:
            res = self._tool_handlers[tool_name](args)
            dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if self._is_tool_error(res):
                cat = res.get("category") or self._tool_category(tool_name)
                entry: ToolTraceEntry = {
                    "timestamp": started,
                    "tool": tool_name,
                    "arguments": args,
                    "duration_ms": dur_ms,
                    "status": "ERROR",
                    "summary": str(res.get("error", "unknown error")),
                    "category": cat,
                }
                trace.append(entry)
                self.tool_logs.append(entry)
                logger.warning("tool_err tool=%s duration_ms=%.2f error=%s", tool_name, dur_ms, res.get("error"))
                return res
            entry = {
                "timestamp": started,
                "tool": tool_name,
                "arguments": args,
                "duration_ms": dur_ms,
                "status": "OK",
                "summary": self._summarize_result(tool_name, res),
            }
            trace.append(entry)
            self.tool_logs.append(entry)
            logger.debug("tool_ok tool=%s duration_ms=%.2f", tool_name, dur_ms)
            return res
        except Exception as exc:
            dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            cat = self._tool_category(tool_name)
            entry = {
                "timestamp": started,
                "tool": tool_name,
                "arguments": args,
                "duration_ms": dur_ms,
                "status": "ERROR",
                "summary": str(exc),
                "category": cat,
            }
            trace.append(entry)
            self.tool_logs.append(entry)
            logger.warning("tool_err tool=%s duration_ms=%.2f error=%s", tool_name, dur_ms, exc)
            return {
                "status": "ERROR",
                "tool": tool_name,
                "error": str(exc),
                "category": cat,
            }

    # ------------------------------------------------------------------
    # Entity Extraction & Multi-Intent Recognition
    # ------------------------------------------------------------------
    def _resolve_country(self, text: str, ctx: SessionContext) -> str:
        return resolve_country(text, ctx, self._country_lookup)

    def _extract_entities(self, message: str, low: str, ctx: SessionContext) -> Dict[str, Any]:
        return extract_entities(message, low, ctx, self.world, self._country_lookup)

    def _recognize_intents(self, low: str, entities: Dict[str, Any]) -> List[str]:
        return recognize_intents(low, entities)

    # ------------------------------------------------------------------
    # Main Fast Command Orchestrator
    # ------------------------------------------------------------------
    async def process_command(self, message: str, session_id: str = "default", use_llm_polish: bool = False) -> JarvisReply:
        t_start = time.perf_counter()
        self._evict_stale_sessions(max_age_seconds=3600)
        session_id = (session_id or "default").strip() if isinstance(session_id, str) else "default"
        if not session_id:
            session_id = "default"
        ctx = self._get_session(session_id)
        trace: List[ToolTraceEntry] = []

        raw_message = "" if message is None else str(message)
        message = raw_message.strip()
        if len(message) > MAX_MESSAGE_LENGTH:
            message = message[:MAX_MESSAGE_LENGTH]
        low = message.lower()

        if not low:
            total_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            answer = "Standing by, Sir. Please provide a command, country query, route request, or operational instruction."
            empty_reply: JarvisReply = {
                "reply_id": f"MSG-{uuid.uuid4().hex[:8].upper()}",
                "timestamp": utc_now_iso(),
                "session_id": session_id,
                "user_message": "",
                "assistant_message": answer,
                "spoken_summary": answer[:280],
                "provider": "instant_grounded_orchestrator",
                "model": "zero-latency-tool-engine",
                "latency_ms": total_ms,
                "globe_state": "IDLE",
                "intent": "empty_input",
                "intents": [],
                "intents_succeeded": 0,
                "intents_failed": 0,
                "entities": {"country_id": ctx.active_country_id},
                "kpis": [],
                "tables": [],
                "tools_called": [],
                "context": ctx.snapshot(),
                "execution_trace": [],
                "structured_cards": [],
                "frontend_commands": [],
                "pending_approval": None,
            }
            self.conversations.setdefault(session_id, deque(maxlen=200)).append(empty_reply)
            return empty_reply

        entities = self._extract_entities(message, low, ctx)
        cid = entities["country_id"]
        country = self.world.countries[cid]
        intents = self._recognize_intents(low, entities)

        structured_cards: List[Dict[str, Any]] = []
        frontend_commands: List[Dict[str, Any]] = []
        kpis: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []
        answer_sections: List[str] = []
        pending_approval: Optional[Dict[str, Any]] = None
        globe_state = "SUCCESS"
        intents_succeeded = 0

        for intent in intents:
            ok, globe_state, pending_approval = execute_intent(
                intent,
                intents_count=len(intents),
                cid=cid,
                country=country,
                low=low,
                entities=entities,
                ctx=ctx,
                world=self.world,
                run_tool=lambda name, args: self._run_tool(trace, name, args),
                is_tool_error=self._is_tool_error,
                structured_cards=structured_cards,
                frontend_commands=frontend_commands,
                kpis=kpis,
                tables=tables,
                answer_sections=answer_sections,
                globe_state=globe_state,
                pending_approval=pending_approval,
            )
            if ok:
                intents_succeeded += 1

        intents_failed = len(intents) - intents_succeeded
        if intents_succeeded == 0 and intents:
            globe_state = "ERROR"

        answer = "\n".join(answer_sections)

        # Ultra-fast grounded response by default (<5ms); optional LLM polish when requested & keys configured
        provider_used = "instant_grounded_orchestrator"
        model_used = "zero-latency-tool-engine"
        if use_llm_polish:
            tool_context = json.dumps(
                {"kpis": kpis, "tables": tables, "tools_called": [e["tool"] for e in trace], "draft_summary": answer},
                default=str,
            )[:4000]
            try:
                llm_res = await self.provider_manager.synthesize_narrative(
                    user_query=message,
                    grounded_context=tool_context,
                    fallback_text=answer,
                )
                polished = llm_res.get("text") if isinstance(llm_res, dict) else None
                if isinstance(polished, str) and polished.strip():
                    answer = polished
                    provider_used = str(llm_res.get("provider_used") or "local_deterministic_orchestrator")
                    model_used = str(llm_res.get("model_used") or "grounded-tool-engine")
                else:
                    provider_used = "local_deterministic_orchestrator"
                    model_used = "grounded-tool-engine"
            except Exception as exc:
                logger.warning("llm_polish_fallback error=%s", exc)
                provider_used = "local_deterministic_orchestrator"
                model_used = "grounded-tool-engine"

        total_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
        tools_called = [entry["tool"] for entry in trace]
        intent_label = intents[0] if len(intents) == 1 else f"compound:{'+'.join(intents)}"

        reply_record: JarvisReply = {
            "reply_id": f"MSG-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": utc_now_iso(),
            "session_id": session_id,
            "user_message": message,
            "assistant_message": answer,
            "spoken_summary": answer.replace("\n", " ").replace("•", "")[:280],
            "provider": provider_used,
            "model": model_used,
            "latency_ms": total_ms,
            "globe_state": globe_state,
            "intent": intent_label,
            "intents": intents,
            "intents_succeeded": intents_succeeded,
            "intents_failed": intents_failed,
            "entities": entities,
            "kpis": kpis,
            "tables": tables,
            "tools_called": tools_called,
            "context": ctx.snapshot(),
            "execution_trace": trace,
            "structured_cards": structured_cards,
            "frontend_commands": frontend_commands,
            "pending_approval": pending_approval,
        }
        logger.info(
            "reply session=%s intent=%s globe_state=%s succeeded=%d failed=%d latency_ms=%.2f",
            session_id,
            intent_label,
            globe_state,
            intents_succeeded,
            intents_failed,
            total_ms,
        )
        self.conversations.setdefault(session_id, deque(maxlen=200)).append(reply_record)
        return reply_record


__all__ = [
    "JarvisAgent",
    "JarvisReply",
    "MAX_MESSAGE_LENGTH",
    "MAX_SESSIONS",
    "SessionContext",
    "ToolTraceEntry",
    "_ID_FIELDS",
    "_RE_BATTERY_PCT",
    "_RE_DRONE_ID",
    "_walk_objects",
]
