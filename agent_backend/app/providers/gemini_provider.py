"""Genuine Google Gemini provider implementing native functionDeclarations / functionCall / functionResponse."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional
import httpx

from app.models.actions import ProviderResponse, ToolCallRequest
from app.providers.base_provider import BaseAIProvider
from app.providers.key_rotator import KeySlot, ProviderError, ProviderErrorKind, RoundRobinKeyRotator


def _sanitize_gemini_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Strip JSON Schema fields Gemini REST API rejects (e.g., additionalProperties)."""
    if not isinstance(schema, dict):
        return {}
    cleaned: Dict[str, Any] = {}
    for k, v in schema.items():
        if k in ("additionalProperties", "$schema", "default"):
            continue
        if k == "properties" and isinstance(v, dict):
            cleaned["properties"] = {pk: _sanitize_gemini_schema(pv) for pk, pv in v.items()}
        elif k == "items" and isinstance(v, dict):
            cleaned["items"] = _sanitize_gemini_schema(v)
        else:
            cleaned[k] = v
    return cleaned


def _classify_gemini_error(status: int, body_text: str) -> tuple[ProviderErrorKind, bool]:
    low = body_text.lower()
    if status in (401, 403) or "api_key_invalid" in low or "api key not valid" in low:
        return ProviderErrorKind.AUTH_INVALID, False
    if status == 429 or "resource_exhausted" in low:
        if "quota" in low or "daily" in low:
            return ProviderErrorKind.QUOTA_EXHAUSTED, True
        return ProviderErrorKind.RATE_LIMIT, True
    if status == 404 or ("model" in low and "not found" in low):
        return ProviderErrorKind.UNSUPPORTED_MODEL, False
    if status == 400:
        return ProviderErrorKind.MALFORMED_REQUEST, False
    return ProviderErrorKind.PROVIDER_SERVER_ERROR, True


class GeminiProvider(BaseAIProvider):
    """Google Gemini provider with independent 3-key round-robin rotation and native functionCall."""

    provider_name = "GEMINI"

    def __init__(
        self,
        api_keys: List[str],
        model_id: str = "gemini-2.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        *,
        cooldown_rate_limit_s: int = 45,
        cooldown_quota_s: int = 300,
        cooldown_server_s: int = 20,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self.rotator = RoundRobinKeyRotator(
            "GEMINI",
            api_keys,
            cooldown_rate_limit_s=cooldown_rate_limit_s,
            cooldown_quota_s=cooldown_quota_s,
            cooldown_server_s=cooldown_server_s,
        )

    @staticmethod
    def translate_tool_schemas(canonical_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        declarations = []
        for t in canonical_tools:
            decl: Dict[str, Any] = {
                "name": t["name"],
                "description": t.get("description", ""),
            }
            params = _sanitize_gemini_schema(t.get("input_schema", {"type": "object", "properties": {}}))
            if params.get("properties"):
                decl["parameters"] = params
            declarations.append(decl)
        return [{"functionDeclarations": declarations}] if declarations else []

    @staticmethod
    def build_contents(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        contents: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "user")
            if role == "tool":
                raw = m.get("content", "{}")
                try:
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    parsed = {"output": str(raw)}
                if not isinstance(parsed, dict):
                    parsed = {"result": parsed}
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": m.get("tool_name", "tool"),
                            "response": parsed,
                        }
                    }],
                })
            elif role == "assistant":
                parts: List[Dict[str, Any]] = []
                if m.get("content"):
                    parts.append({"text": m["content"]})
                for tc in m.get("tool_calls", []):
                    parts.append({
                        "functionCall": {
                            "name": tc["name"],
                            "args": tc.get("arguments", {}),
                        }
                    })
                if parts:
                    contents.append({"role": "model", "parts": parts})
            else:
                contents.append({"role": "user", "parts": [{"text": m.get("content", "")}]})
        return contents

    async def generate_with_tools(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        timeout_seconds: float = 45.0,
    ) -> ProviderResponse:
        payload: Dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": self.build_contents(messages),
            "generationConfig": {"temperature": 0.15},
        }
        tools = self.translate_tool_schemas(tool_schemas)
        if tools:
            payload["tools"] = tools

        url = f"{self.base_url}/models/{self.model_id}:generateContent"
        last_err: Optional[ProviderError] = None
        for _attempt in range(3):
            slot: KeySlot = self.rotator.acquire_next()
            t0 = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=timeout_seconds, transport=self._transport) as client:
                    resp = await client.post(
                        url,
                        params={"key": slot.api_key},
                        headers={"Content-Type": "application/json"},
                        json=payload,
                    )
            except httpx.TimeoutException as exc:
                self.rotator.record_failure(slot, ProviderErrorKind.TIMEOUT, str(exc))
                last_err = ProviderError(
                    f"Gemini request timed out on {slot.alias}: {exc}",
                    provider="GEMINI",
                    kind=ProviderErrorKind.TIMEOUT,
                    key_alias=slot.alias,
                    retryable=True,
                )
                continue
            except httpx.HTTPError as exc:
                self.rotator.record_failure(slot, ProviderErrorKind.NETWORK_ERROR, str(exc))
                last_err = ProviderError(
                    f"Gemini network error on {slot.alias}: {exc}",
                    provider="GEMINI",
                    kind=ProviderErrorKind.NETWORK_ERROR,
                    key_alias=slot.alias,
                    retryable=True,
                )
                continue

            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            if resp.status_code >= 400:
                kind, retryable = _classify_gemini_error(resp.status_code, resp.text)
                self.rotator.record_failure(slot, kind, f"HTTP {resp.status_code}: {resp.text[:200]}")
                last_err = ProviderError(
                    f"Gemini API error ({resp.status_code}) on {slot.alias}: {resp.text[:200]}",
                    provider="GEMINI",
                    kind=kind,
                    key_alias=slot.alias,
                    status_code=resp.status_code,
                    retryable=retryable,
                )
                if kind in (ProviderErrorKind.UNSUPPORTED_MODEL, ProviderErrorKind.MALFORMED_REQUEST):
                    raise last_err
                if not self.rotator.has_available_keys():
                    raise last_err
                continue

            data = resp.json()
            self.rotator.record_success(slot, latency_ms)
            candidates = data.get("candidates") or []
            if not candidates:
                raise ProviderError(
                    "Gemini returned empty candidates array.",
                    provider="GEMINI",
                    kind=ProviderErrorKind.PROVIDER_SERVER_ERROR,
                    key_alias=slot.alias,
                    retryable=True,
                )
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            text_chunks: List[str] = []
            parsed_calls: List[ToolCallRequest] = []
            for p in parts:
                if "text" in p and p["text"]:
                    text_chunks.append(p["text"])
                if "functionCall" in p and isinstance(p["functionCall"], dict):
                    fc = p["functionCall"]
                    args = fc.get("args") or {}
                    parsed_calls.append(
                        ToolCallRequest(
                            tool_call_id=f"GEM-CALL-{uuid.uuid4().hex[:8].upper()}",
                            name=fc.get("name", ""),
                            arguments=args if isinstance(args, dict) else {},
                        )
                    )

            return ProviderResponse(
                provider="GEMINI",
                model_id=data.get("modelVersion", self.model_id),
                key_alias=slot.alias,
                response_id=data.get("responseId", ""),
                text="\n".join(text_chunks).strip(),
                tool_calls=parsed_calls,
                latency_ms=latency_ms,
                finish_reason=candidates[0].get("finishReason", "STOP") or "STOP",
                raw_usage=data.get("usageMetadata") or {},
            )

        raise last_err or ProviderError("Gemini provider exhausted retries.", provider="GEMINI", kind=ProviderErrorKind.PROVIDER_SERVER_ERROR)

    def status(self) -> Dict[str, Any]:
        return {
            **self.rotator.status(),
            "model_id": self.model_id,
            "base_url": self.base_url,
        }
