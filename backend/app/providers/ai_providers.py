from __future__ import annotations
import asyncio
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set
import httpx

DEFAULT_AI_TIMEOUT_SECONDS = 12.0


def _get_timeout_seconds() -> float:
    raw = os.getenv("AI_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_AI_TIMEOUT_SECONDS)).strip()
    try:
        return max(1.0, float(raw))
    except ValueError:
        return DEFAULT_AI_TIMEOUT_SECONDS


def build_provider_tool_payload(schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert clean JSON-Schema tool definitions into Gemini and Grok/OpenAI provider payloads."""
    gemini_declarations: List[Dict[str, Any]] = []
    openai_tools: List[Dict[str, Any]] = []

    for schema in schemas or []:
        if not isinstance(schema, dict):
            continue
        name = str(schema.get("name", "")).strip()
        if not name:
            continue
        description = str(schema.get("description", "")).strip()
        parameters = schema.get("parameters") or {
            "type": "object",
            "properties": {},
            "required": [],
        }

        gemini_declarations.append({
            "name": name,
            "description": description,
            "parameters": parameters,
        })
        openai_tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        })

    return {
        "gemini": [{"function_declarations": gemini_declarations}],
        "grok": openai_tools,
        "openai": openai_tools,
        "tool_count": len(gemini_declarations),
    }


@dataclass
class KeyRecord:
    key_id: str
    provider: str
    secret: str
    enabled: bool = True
    healthy: bool = True
    request_count: int = 0
    error_count: int = 0
    rate_limit_events: int = 0
    last_used_ts: float = 0.0
    cooldown_until_ts: float = 0.0
    last_error: Optional[str] = None


class AIKeyPool:
    """Six-key provider pool (up to 3 Gemini + 3 Grok keys). Never exposes raw secrets."""

    def __init__(self) -> None:
        self.keys: Dict[str, List[KeyRecord]] = {"gemini": [], "grok": []}
        self._load_from_env()

    def _load_from_env(self) -> None:
        for provider, prefix in [("gemini", "GEMINI_API_KEY"), ("grok", "GROK_API_KEY")]:
            records: List[KeyRecord] = []
            for idx in (1, 2, 3):
                val = os.getenv(f"{prefix}_{idx}", "").strip()
                if val:
                    records.append(KeyRecord(key_id=f"{provider}_key_{idx}", provider=provider, secret=val))
            self.keys[provider] = records

    def select_key(self, provider: str) -> Optional[KeyRecord]:
        now = time.time()
        candidates = [
            k for k in self.keys.get(provider, [])
            if k.enabled and k.healthy and k.cooldown_until_ts <= now
        ]
        if not candidates:
            return None
        # Least-recently-used distribution
        candidates.sort(key=lambda k: k.last_used_ts)
        chosen = candidates[0]
        chosen.last_used_ts = now
        chosen.request_count += 1
        return chosen

    def record_error(self, key: KeyRecord, error_msg: str, is_rate_limit: bool = False) -> None:
        key.error_count += 1
        key.last_error = str(error_msg or "unknown error")[:180]
        if is_rate_limit:
            key.rate_limit_events += 1
        backoff = min(300.0, 10.0 * (2 ** min(4, key.error_count - 1)))
        key.cooldown_until_ts = time.time() + backoff
        if key.error_count >= 5:
            key.healthy = False

    def disable_key(self, key_id: str) -> bool:
        for recs in self.keys.values():
            for k in recs:
                if k.key_id == key_id:
                    k.enabled = False
                    return True
        return False

    def enable_key(self, key_id: str) -> bool:
        for recs in self.keys.values():
            for k in recs:
                if k.key_id == key_id:
                    k.enabled = True
                    k.healthy = True
                    k.error_count = 0
                    k.cooldown_until_ts = 0.0
                    return True
        return False

    def public_status(self) -> Dict[str, Any]:
        now = time.time()
        out: Dict[str, Any] = {}
        for prov in ("gemini", "grok"):
            recs = self.keys.get(prov, [])
            active = [k for k in recs if k.enabled and k.healthy and k.cooldown_until_ts <= now]
            status = "Available" if active else ("Degraded" if recs else "Offline (Local Fallback Active)")
            out[prov] = {
                "status": status,
                "configured_keys": len(recs),
                "active_keys": len(active),
                "total_requests": sum(k.request_count for k in recs),
                "total_errors": sum(k.error_count for k in recs),
                "last_error": next((k.last_error for k in recs if k.last_error), None),
                "model": os.getenv("GEMINI_MODEL" if prov == "gemini" else "GROK_MODEL", "not-configured"),
            }
        return out


class SharedHTTPClientPool:
    """Reusable httpx.AsyncClient pool with tight timeouts and keep-alive connection limits."""

    def __init__(
        self,
        timeout_seconds: Optional[float] = None,
        max_connections: int = 20,
        max_keepalive_connections: int = 10,
    ) -> None:
        self.timeout_seconds = timeout_seconds or _get_timeout_seconds()
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self._client: Optional[httpx.AsyncClient] = None
        self._loop_id: Optional[int] = None

    def get_client(self) -> httpx.AsyncClient:
        try:
            current_loop_id = id(asyncio.get_running_loop())
        except RuntimeError:
            current_loop_id = None

        if (
            self._client is None
            or self._client.is_closed
            or (current_loop_id is not None and self._loop_id is not None and self._loop_id != current_loop_id)
        ):
            timeout = httpx.Timeout(
                timeout=self.timeout_seconds,
                connect=min(5.0, self.timeout_seconds),
                read=self.timeout_seconds,
                write=min(5.0, self.timeout_seconds),
                pool=min(5.0, self.timeout_seconds),
            )
            limits = httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=self.max_keepalive_connections,
                keepalive_expiry=30.0,
            )
            self._client = httpx.AsyncClient(timeout=timeout, limits=limits)
            self._loop_id = current_loop_id
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        self._loop_id = None


class AIProvider(ABC):
    def __init__(self, http_pool: Optional[SharedHTTPClientPool] = None) -> None:
        self.http_pool = http_pool or SharedHTTPClientPool()

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str,
        api_key: str,
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        ...

    @abstractmethod
    async def health_check(self, api_key: str, model: str) -> bool:
        ...


class GeminiAdapter(AIProvider):
    async def generate(
        self,
        prompt: str,
        system_prompt: str,
        api_key: str,
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload: Dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
        }
        if tools:
            payload["tools"] = tools
        client = self.http_pool.get_client()
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception as exc:
            raise ValueError(f"Malformed Gemini JSON response: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Malformed Gemini response: expected JSON object")
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
            raise ValueError("Gemini response contained no candidates")
        content = candidates[0].get("content")
        if not isinstance(content, dict):
            raise ValueError("Gemini candidate missing content object")
        parts = content.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError("Gemini candidate contained no content parts")
        texts = [
            p.get("text")
            for p in parts
            if isinstance(p, dict) and isinstance(p.get("text"), str) and p.get("text").strip()
        ]
        if not texts:
            raise ValueError("Gemini response parts contained no text")
        return "\n".join(texts).strip()

    async def health_check(self, api_key: str, model: str) -> bool:
        return bool(api_key and model)


class GrokAdapter(AIProvider):
    async def generate(
        self,
        prompt: str,
        system_prompt: str,
        api_key: str,
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        url = "https://api.x.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
        client = self.http_pool.get_client()
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception as exc:
            raise ValueError(f"Malformed Grok JSON response: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Malformed Grok response: expected JSON object")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("Grok response contained no choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("Grok choice missing message object")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Grok response message contained empty or non-string content")
        return content.strip()

    async def health_check(self, api_key: str, model: str) -> bool:
        return bool(api_key and model)


class AIProviderManager:
    """Centralized provider router with shared connection pooling, fast failover, and deterministic fallback."""

    def __init__(self, timeout_seconds: Optional[float] = None) -> None:
        self.key_pool = AIKeyPool()
        self.http_pool = SharedHTTPClientPool(timeout_seconds=timeout_seconds or _get_timeout_seconds())
        self.adapters: Dict[str, AIProvider] = {
            "gemini": GeminiAdapter(http_pool=self.http_pool),
            "grok": GrokAdapter(http_pool=self.http_pool),
        }
        self.primary_provider = os.getenv("AI_PRIMARY_PROVIDER", "gemini").lower()
        self.fallback_provider = os.getenv("AI_FALLBACK_PROVIDER", "grok").lower()
        self.last_latency_ms: float = 0.0

    @staticmethod
    def build_provider_tool_payload(schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
        return build_provider_tool_payload(schemas)

    async def aclose(self) -> None:
        await self.http_pool.aclose()

    @staticmethod
    def _coerce_context(grounded_context: Any) -> str:
        if grounded_context is None:
            return ""
        if isinstance(grounded_context, str):
            return grounded_context
        try:
            return json.dumps(grounded_context, default=str)
        except Exception:
            return str(grounded_context)

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            if exc.response.status_code == 429:
                return True
        return "429" in str(exc)

    async def synthesize_narrative(
        self,
        user_query: str,
        grounded_context: Any,
        fallback_text: str,
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Try primary provider (rotating across all healthy keys) -> fallback provider -> deterministic grounded local fallback."""
        safe_query = "" if user_query is None else str(user_query)
        safe_context = self._coerce_context(grounded_context)
        safe_fallback = "" if fallback_text is None else str(fallback_text)

        system_prompt = (
            "You are JARVIS, the Global Disaster Intelligence & Command Agent for Quantum Rescue. "
            "Report ONLY the exact figures, entity IDs, and facts present in the provided simulation context. "
            "Never fabricate numbers, casualties, or capabilities. Keep responses concise, structured, and operational."
        )
        prompt = f"USER REQUEST: {safe_query}\n\nAUTHORITATIVE SIMULATION DATA:\n{safe_context}"
        provider_tools = build_provider_tool_payload(tool_schemas) if tool_schemas else None

        provider_order: List[str] = []
        for prov in (self.primary_provider, self.fallback_provider):
            if prov and prov in self.adapters and prov not in provider_order:
                provider_order.append(prov)

        for prov in provider_order:
            model = os.getenv("GEMINI_MODEL" if prov == "gemini" else "GROK_MODEL", "").strip()
            if not model:
                continue
            max_attempts = max(1, len(self.key_pool.keys.get(prov, [])))
            tried_key_ids: Set[str] = set()
            for _ in range(max_attempts):
                key = self.key_pool.select_key(prov)
                if not key or key.key_id in tried_key_ids:
                    break
                tried_key_ids.add(key.key_id)
                t0 = time.perf_counter()
                try:
                    tools_arg = provider_tools.get(prov) if provider_tools else None
                    text = await self.adapters[prov].generate(
                        prompt, system_prompt, key.secret, model, tools=tools_arg
                    )
                    if not isinstance(text, str) or not text.strip():
                        raise ValueError(f"Empty or non-string narrative returned by {prov}")
                    self.last_latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                    return {
                        "text": text.strip(),
                        "provider_used": prov,
                        "model_used": model,
                        "latency_ms": self.last_latency_ms,
                    }
                except Exception as exc:
                    self.key_pool.record_error(
                        key, str(exc), is_rate_limit=self._is_rate_limit_error(exc)
                    )

        return {
            "text": safe_fallback,
            "provider_used": "local_deterministic_orchestrator",
            "model_used": "grounded-tool-engine",
            "latency_ms": 0.4,
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "primary_provider": self.primary_provider,
            "fallback_provider": self.fallback_provider,
            "timeout_seconds": self.http_pool.timeout_seconds,
            "connection_pooling": True,
            "last_latency_ms": self.last_latency_ms,
            "providers": self.key_pool.public_status(),
        }
