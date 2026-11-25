"""FastAPI AI Rescue Agent Service (Port 8001) — JSON-only persistence, real Grok & Gemini tool calling."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import Field

from app.agent.memory import ConversationMemoryStore
from app.agent.rescue_agent import RescueAgent
from app.config import AgentSettings
from app.models.messages import AgentMode, BaseModel, ProviderMode
from app.providers.gemini_provider import GeminiProvider
from app.providers.grok_provider import GrokProvider
from app.providers.provider_manager import ProviderManager
from app.services.execution_logger import AgentEventHub, ExecutionLogger
from app.services.simulation_client import SimulationClient
from app.services.websocket_client import SimulationWebSocketClient
from app.tools.registry import ToolRegistry


class CommandReq(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: Optional[AgentMode] = None
    provider_mode: Optional[ProviderMode] = None


class ModeReq(BaseModel):
    mode: AgentMode


class ProviderModeReq(BaseModel):
    mode: ProviderMode


class ApprovalReq(BaseModel):
    action_ids: Optional[List[str]] = None


class NewSessionReq(BaseModel):
    mode: AgentMode = AgentMode.ASSISTED
    provider_preference: ProviderMode = ProviderMode.AUTO


class AgentRuntime:
    def __init__(self):
        self.settings = AgentSettings.load()
        self.sim_client = SimulationClient(base_url=self.settings.simulation_api_base_url)
        self.registry = ToolRegistry()
        self.memory = ConversationMemoryStore(max_messages=self.settings.max_conversation_messages)
        self.logger = ExecutionLogger()
        self.event_hub = AgentEventHub()

        self.grok = GrokProvider(
            api_keys=self.settings.grok_api_keys,
            model_id=self.settings.grok_model_id,
            base_url=self.settings.grok_base_url,
            cooldown_rate_limit_s=self.settings.grok_cooldown_rate_limit_s,
            cooldown_quota_s=self.settings.grok_cooldown_quota_s,
            cooldown_server_s=self.settings.grok_cooldown_server_s,
        )
        self.gemini = GeminiProvider(
            api_keys=self.settings.gemini_api_keys,
            model_id=self.settings.gemini_model_id,
            base_url=self.settings.gemini_base_url,
            cooldown_rate_limit_s=self.settings.gemini_cooldown_rate_limit_s,
            cooldown_quota_s=self.settings.gemini_cooldown_quota_s,
            cooldown_server_s=self.settings.gemini_cooldown_server_s,
        )
        self.providers = ProviderManager(
            grok=self.grok,
            gemini=self.gemini,
            default_mode=ProviderMode(self.settings.default_provider_mode),
        )
        self.agent = RescueAgent(
            settings=self.settings,
            provider_manager=self.providers,
            sim_client=self.sim_client,
            registry=self.registry,
            memory=self.memory,
            logger=self.logger,
            event_hub=self.event_hub,
        )
        ws_base = self.settings.simulation_api_base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.ws_observer = SimulationWebSocketClient(
            ws_url=f"{ws_base}/ws/simulation",
            on_meaningful_event=self.agent.on_meaningful_world_event,
            debounce_seconds=self.settings.autonomous_event_debounce_seconds,
        )


agent_runtime = AgentRuntime()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    agent_runtime.ws_observer.start()
    try:
        yield
    finally:
        await agent_runtime.ws_observer.stop()


app = FastAPI(title="QUANTUM RESCUE V2 — Autonomous AI Rescue Agent Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/api/agent/health")
def agent_health():
    return {
        "status": "ok",
        "service": "quantum-rescue-agent",
        "version": "2.0.0",
        "storage": "json_only",
        "simulation_url": agent_runtime.settings.simulation_api_base_url,
        "ws_observer": agent_runtime.ws_observer.status_dict(),
        "registered_tools": len(agent_runtime.registry.list_names()),
    }


@app.get("/api/agent/status")
def agent_status():
    return {
        **agent_runtime.agent.runtime_status(),
        "ws_observer": agent_runtime.ws_observer.status_dict(),
    }


@app.get("/api/agent/providers")
def provider_status():
    return agent_runtime.providers.status()


@app.post("/api/agent/providers/mode")
def set_provider_mode(req: ProviderModeReq):
    agent_runtime.providers.set_mode(req.mode)
    return {"mode": agent_runtime.providers.mode.value}


@app.post("/api/agent/mode")
def set_agent_mode(req: ModeReq):
    agent_runtime.agent.set_mode(req.mode)
    return {"mode": agent_runtime.agent.mode.value}


@app.post("/api/agent/stop")
async def stop_agent_execution():
    res = agent_runtime.agent.stop_current_execution()
    await agent_runtime.event_hub.broadcast("execution_stop_requested", res)
    return res


@app.post("/api/agent/pause")
async def pause_agent():
    res = agent_runtime.agent.pause()
    await agent_runtime.event_hub.broadcast("agent_paused", res)
    return res


@app.post("/api/agent/resume")
async def resume_agent():
    res = agent_runtime.agent.resume()
    await agent_runtime.event_hub.broadcast("agent_resumed", res)
    return res


@app.get("/api/agent/tools")
def list_tools():
    return {"count": len(agent_runtime.registry.list_names()), "tools": agent_runtime.registry.catalog()}


@app.post("/api/agent/chat")
async def chat_command(req: CommandReq):
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty.")
    trace = await agent_runtime.agent.handle_user_command(
        req.message.strip(),
        session_id=req.session_id,
        mode_override=req.mode,
        provider_override=req.provider_mode,
    )
    return trace.model_dump()


@app.post("/api/agent/approvals/{execution_id}/approve")
async def approve_actions(execution_id: str, req: ApprovalReq = ApprovalReq()):
    try:
        trace = await agent_runtime.agent.approve_pending_actions(execution_id, action_ids=req.action_ids)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    return trace.model_dump()


@app.post("/api/agent/approvals/{execution_id}/reject")
async def reject_actions(execution_id: str):
    try:
        trace = await agent_runtime.agent.reject_pending_actions(execution_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    return trace.model_dump()


@app.get("/api/agent/sessions")
def list_sessions():
    return agent_runtime.memory.list_sessions()


@app.post("/api/agent/sessions")
def create_session(req: NewSessionReq):
    sess = agent_runtime.memory.create_session(mode=req.mode, provider_preference=req.provider_preference)
    return sess.model_dump()


@app.get("/api/agent/sessions/current")
def get_current_session():
    return agent_runtime.memory.load_session().model_dump()


@app.get("/api/agent/sessions/{session_id}")
def get_session(session_id: str):
    return agent_runtime.memory.load_session(session_id).model_dump()


@app.get("/api/agent/executions")
def list_executions(limit: int = Query(default=40, ge=1, le=200)):
    return agent_runtime.logger.list_executions(limit=limit)


@app.get("/api/agent/executions/{execution_id}")
def get_execution(execution_id: str):
    doc = agent_runtime.logger.get_execution(execution_id)
    if not doc:
        raise HTTPException(404, f"Execution {execution_id} not found")
    return JSONResponse(doc)


@app.get("/api/agent/audit")
def get_audit_log(limit: int = Query(default=150, ge=1, le=1000)):
    return {"entries": agent_runtime.logger.read_audit(limit=limit)}


@app.websocket("/ws/agent")
async def ws_agent(ws: WebSocket):
    await agent_runtime.event_hub.connect(ws)
    try:
        await ws.send_json({"type": "status", "payload": agent_runtime.agent.runtime_status()})
        while True:
            _ = await ws.receive_text()
    except WebSocketDisconnect:
        agent_runtime.event_hub.disconnect(ws)
