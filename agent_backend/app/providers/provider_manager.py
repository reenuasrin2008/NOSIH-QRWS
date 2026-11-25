"""Provider manager coordinating GROK, GEMINI, and AUTO failover modes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.actions import ProviderResponse
from app.models.messages import ProviderMode
from app.providers.gemini_provider import GeminiProvider
from app.providers.grok_provider import GrokProvider
from app.providers.key_rotator import ProviderError, ProviderErrorKind


class ProviderManager:
    """Selects healthy provider, applies independent key rotation, and fails over cleanly in AUTO mode."""

    def __init__(
        self,
        grok: GrokProvider,
        gemini: GeminiProvider,
        default_mode: ProviderMode = ProviderMode.AUTO,
    ):
        self.grok = grok
        self.gemini = gemini
        self.mode: ProviderMode = default_mode
        self.history: List[Dict[str, Any]] = []
        self._last_provider: Optional[str] = None

    def set_mode(self, mode: ProviderMode) -> None:
        self.mode = mode

    def _ordered_providers(self, mode_override: Optional[ProviderMode] = None) -> List[Any]:
        active_mode = mode_override or self.mode
        if active_mode == ProviderMode.GROK:
            return [self.grok]
        if active_mode == ProviderMode.GEMINI:
            return [self.gemini]
        # AUTO mode: prefer healthy provider with configured keys; preserve Grok -> Gemini default order
        if self.grok.rotator.has_available_keys():
            return [self.grok, self.gemini]
        if self.gemini.rotator.has_available_keys():
            return [self.gemini, self.grok]
        return [self.grok, self.gemini]

    async def generate_with_tools(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        mode_override: Optional[ProviderMode] = None,
        timeout_seconds: float = 45.0,
    ) -> ProviderResponse:
        providers = self._ordered_providers(mode_override)
        errors: List[str] = []
        first_failed_provider: Optional[str] = None

        for idx, prov in enumerate(providers):
            try:
                resp = await prov.generate_with_tools(
                    system_prompt=system_prompt,
                    messages=messages,
                    tool_schemas=tool_schemas,
                    timeout_seconds=timeout_seconds,
                )
                if first_failed_provider and first_failed_provider != prov.provider_name:
                    resp.switched_from = first_failed_provider
                self._last_provider = resp.provider
                self.history.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "provider": resp.provider,
                    "key_alias": resp.key_alias,
                    "model_id": resp.model_id,
                    "latency_ms": resp.latency_ms,
                    "tool_call_count": len(resp.tool_calls),
                    "switched_from": resp.switched_from,
                    "status": "OK",
                })
                if len(self.history) > 100:
                    self.history = self.history[-100:]
                return resp
            except ProviderError as exc:
                errors.append(f"{prov.provider_name}: {exc}")
                self.history.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "provider": prov.provider_name,
                    "key_alias": exc.key_alias,
                    "error_kind": exc.kind.value,
                    "error": str(exc)[:200],
                    "status": "ERROR",
                })
                if idx == 0:
                    first_failed_provider = prov.provider_name
                # Only fail over to secondary provider if AUTO mode has another provider
                continue

        raise ProviderError(
            "All selected AI providers failed: " + " | ".join(errors),
            provider=(mode_override or self.mode).value,
            kind=ProviderErrorKind.PROVIDER_SERVER_ERROR,
            retryable=False,
        )

    def status(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "last_provider": self._last_provider,
            "grok": self.grok.status(),
            "gemini": self.gemini.status(),
            "recent_history": self.history[-20:],
        }
