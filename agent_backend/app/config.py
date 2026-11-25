"""Environment and JSON configuration loader for the AI Rescue Agent backend."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from app.services.json_store import get_runtime_data_dir, read_json_safe


def _load_dotenv_file(env_path: Path) -> None:
    """Minimal zero-dependency .env loader (does not overwrite existing env vars)."""
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


@dataclass
class AgentSettings:
    grok_api_keys: List[str] = field(default_factory=list)
    grok_model_id: str = "grok-3-mini"
    grok_base_url: str = "https://api.x.ai/v1"

    gemini_api_keys: List[str] = field(default_factory=list)
    gemini_model_id: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    simulation_api_base_url: str = "http://127.0.0.1:8000"
    agent_host: str = "127.0.0.1"
    agent_port: int = 8001

    default_provider_mode: str = "AUTO"
    default_agent_mode: str = "ASSISTED"
    max_tool_calls_per_turn: int = 14
    tool_timeout_seconds: float = 25.0
    model_timeout_seconds: float = 45.0
    autonomous_event_debounce_seconds: float = 8.0
    confirm_destructive_actions: bool = True
    max_conversation_messages: int = 40

    grok_cooldown_rate_limit_s: int = 45
    grok_cooldown_quota_s: int = 300
    grok_cooldown_server_s: int = 20
    gemini_cooldown_rate_limit_s: int = 45
    gemini_cooldown_quota_s: int = 300
    gemini_cooldown_server_s: int = 20

    @classmethod
    def load(cls) -> "AgentSettings":
        agent_root = Path(__file__).resolve().parents[1]
        _load_dotenv_file(agent_root / ".env")

        data_dir = get_runtime_data_dir()
        agent_cfg: Dict[str, Any] = read_json_safe(data_dir / "config" / "agent_config.json", default={}) or {}
        prov_cfg: Dict[str, Any] = read_json_safe(data_dir / "config" / "provider_config.json", default={}) or {}
        grok_cfg = prov_cfg.get("grok", {}) if isinstance(prov_cfg, dict) else {}
        gemini_cfg = prov_cfg.get("gemini", {}) if isinstance(prov_cfg, dict) else {}

        grok_keys = [
            os.environ.get(f"GROK_API_KEY_{i}", "").strip()
            for i in (1, 2, 3)
        ]
        gemini_keys = [
            os.environ.get(f"GEMINI_API_KEY_{i}", "").strip()
            for i in (1, 2, 3)
        ]

        return cls(
            grok_api_keys=grok_keys,
            grok_model_id=os.environ.get("GROK_MODEL_ID", "").strip() or grok_cfg.get("default_model_id", "grok-3-mini"),
            grok_base_url=(os.environ.get("GROK_BASE_URL", "").strip() or grok_cfg.get("default_base_url", "https://api.x.ai/v1")).rstrip("/"),
            gemini_api_keys=gemini_keys,
            gemini_model_id=os.environ.get("GEMINI_MODEL_ID", "").strip() or gemini_cfg.get("default_model_id", "gemini-2.5-flash"),
            gemini_base_url=(os.environ.get("GEMINI_BASE_URL", "").strip() or gemini_cfg.get("base_url", "https://generativelanguage.googleapis.com/v1beta")).rstrip("/"),
            simulation_api_base_url=os.environ.get("SIMULATION_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
            agent_host=os.environ.get("AGENT_HOST", "127.0.0.1"),
            agent_port=int(os.environ.get("AGENT_PORT", "8001")),
            default_provider_mode=prov_cfg.get("default_provider_mode", "AUTO"),
            default_agent_mode=agent_cfg.get("default_mode", "ASSISTED"),
            max_tool_calls_per_turn=int(agent_cfg.get("max_tool_calls_per_turn", 14)),
            tool_timeout_seconds=float(agent_cfg.get("tool_timeout_seconds", 25.0)),
            model_timeout_seconds=float(agent_cfg.get("model_timeout_seconds", 45.0)),
            autonomous_event_debounce_seconds=float(agent_cfg.get("autonomous_event_debounce_seconds", 8.0)),
            confirm_destructive_actions=bool(agent_cfg.get("confirm_destructive_actions", True)),
            max_conversation_messages=int(agent_cfg.get("max_conversation_messages", 40)),
            grok_cooldown_rate_limit_s=int(grok_cfg.get("cooldown_rate_limit_s", 45)),
            grok_cooldown_quota_s=int(grok_cfg.get("cooldown_quota_s", 300)),
            grok_cooldown_server_s=int(grok_cfg.get("cooldown_server_s", 20)),
            gemini_cooldown_rate_limit_s=int(gemini_cfg.get("cooldown_rate_limit_s", 45)),
            gemini_cooldown_quota_s=int(gemini_cfg.get("cooldown_quota_s", 300)),
            gemini_cooldown_server_s=int(gemini_cfg.get("cooldown_server_s", 20)),
        )
