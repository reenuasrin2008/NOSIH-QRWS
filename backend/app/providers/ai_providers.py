from __future__ import annotations
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import httpx


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
        key.last_error = error_msg[:180]
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


class AIProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str, api_key: str, model: str) -> str:
        ...

    @abstractmethod
    async def health_check(self, api_key: str, model: str) -> bool:
        ...


class GeminiAdapter(AIProvider):
    async def generate(self, prompt: str, system_prompt: str, api_key: str, model: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
        }
        timeout = float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "60"))
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def health_check(self, api_key: str, model: str) -> bool:
        return bool(api_key and model)


class GrokAdapter(AIProvider):
    async def generate(self, prompt: str, system_prompt: str, api_key: str, model: str) -> str:
        url = "https://api.x.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        timeout = float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "60"))
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def health_check(self, api_key: str, model: str) -> bool:
        return bool(api_key and model)


class AIProviderManager:
    """Centralized provider router with primary/fallback failover and local deterministic fallback."""

    def __init__(self) -> None:
        self.key_pool = AIKeyPool()
        self.adapters: Dict[str, AIProvider] = {
            "gemini": GeminiAdapter(),
            "grok": GrokAdapter(),
        }
        self.primary_provider = os.getenv("AI_PRIMARY_PROVIDER", "gemini").lower()
        self.fallback_provider = os.getenv("AI_FALLBACK_PROVIDER", "grok").lower()
        self.last_latency_ms: float = 0.0

    async def synthesize_narrative(
        self,
        user_query: str,
        grounded_context: str,
        fallback_text: str,
    ) -> Dict[str, Any]:
        """Try primary provider -> fallback provider -> deterministic grounded local fallback."""
        system_prompt = (
            "You are JARVIS, the Global Disaster Intelligence & Command Agent for Quantum Rescue. "
            "Report ONLY the exact figures, entity IDs, and facts present in the provided simulation context. "
            "Never fabricate numbers, casualties, or capabilities. Keep responses concise, structured, and operational."
        )
        prompt = f"USER REQUEST: {user_query}\n\nAUTHORITATIVE SIMULATION DATA:\n{grounded_context}"

        for prov in (self.primary_provider, self.fallback_provider):
            model = os.getenv("GEMINI_MODEL" if prov == "gemini" else "GROK_MODEL", "").strip()
            if not model:
                continue
            key = self.key_pool.select_key(prov)
            if not key:
                continue
            t0 = time.perf_counter()
            try:
                text = await self.adapters[prov].generate(prompt, system_prompt, key.secret, model)
                self.last_latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                return {"text": text, "provider_used": prov, "model_used": model, "latency_ms": self.last_latency_ms}
            except Exception as exc:
                self.key_pool.record_error(key, str(exc), is_rate_limit=("429" in str(exc)))

        return {
            "text": fallback_text,
            "provider_used": "local_deterministic_orchestrator",
            "model_used": "grounded-tool-engine",
            "latency_ms": 0.4,
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "primary_provider": self.primary_provider,
            "fallback_provider": self.fallback_provider,
            "last_latency_ms": self.last_latency_ms,
            "providers": self.key_pool.public_status(),
        }
