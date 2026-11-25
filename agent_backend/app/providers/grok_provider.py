"""Genuine xAI Grok provider implementing OpenAI-compatible native structured function calling."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional
import httpx

from app.models.actions import ProviderResponse, ToolCallRequest
from app.providers.base_provider import BaseAIProvider
from app.providers.key_rotator import KeySlot, ProviderError, ProviderErrorKind, RoundRobinKeyRotator


def _classify_http_error(status: int, body_text: str) -> tuple[ProviderErrorKind, bool]:
    low = body_text.lower()
    if status in (401, 403):
        return ProviderErrorKind.AUTH_INVALID, False
    if status == 429:
        if "quota" in low or "credit" in low or "billing" in low or "insufficient" in low:
            return ProviderErrorKind.QUOTA_EXHAUSTED, True
        return ProviderErrorKind.RATE_LIMIT, True
    if status == 404 and "model" in low:
        return ProviderErrorKind.UNSUPPORTED_MODEL, False
    if status == 400:
        if "model" in low and ("not found" in low or "unsupported" in low):
            return ProviderErrorKind.UNSUPPORTED_MODEL, False
        return ProviderErrorKind.MALFORMED_REQUEST, False
    if status >= 500:
        return ProviderErrorKind.PROVIDER_SERVER_ERROR, True
    return ProviderErrorKind.PROVIDER_SERVER_ERROR, True


class GrokProvider(BaseAIProvider):
    """xAI Grok provider with independent 3-key round-robin rotation and native tool_calls."""

    provider_name = "GROK"

    def __init__(
        self,
        api_keys: List[str],
        model_id: str = "grok-3-mini",
        base_url: str = "https://api.x.ai/v1",
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
            "GROK",
            api_keys,
            cooldown_rate_limit_s=cooldown_rate_limit_s,
            cooldown_quota_s=cooldown_quota_s,
            cooldown_server_s=cooldown_server_s,
        )

    @staticmethod
    def translate_tool_schemas(canonical_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Translate canonical internal schemas into xAI/OpenAI function-calling declarations."""
        out: List[Dict[str, Any]] = []
        for t in canonical_tools:
            out.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            })
        return out

    @staticmethod
    def build_messages(system_prompt: str, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        api_msgs: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = m.get("role", "user")
            if role == "tool":
                api_msgs.append({
                    "role": "tool",
                    "tool_call_id": m.get("tool_call_id", "call_unknown"),
                    "name": m.get("tool_name", ""),
                    "content": m.get("content", "{}"),
                })
            elif role == "assistant" and m.get("tool_calls"):
                tc_list = []
                for tc in m["tool_calls"]:
                    args = tc.get("arguments", {})
                    tc_list.append({
                        "id": tc.get("tool_call_id") or f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": args if isinstance(args, str) else json.dumps(args),
                        },
                    })
                api_msgs.append({
                    "role": "assistant",
                    "content": m.get("content") or "",
                    "tool_calls": tc_list,
                })
            else:
                api_msgs.append({"role": role, "content": m.get("content", "")})
        return api_msgs

    async def generate_with_tools(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        timeout_seconds: float = 45.0,
    ) -> ProviderResponse:
        payload: Dict[str, Any] = {
            "model": self.model_id,
            "messages": self.build_messages(system_prompt, messages),
            "temperature": 0.15,
        }
        if tool_schemas:
            payload["tools"] = self.translate_tool_schemas(tool_schemas)
            payload["tool_choice"] = "auto"

        last_err: Optional[ProviderError] = None
        for _attempt in range(3):
            slot: KeySlot = self.rotator.acquire_next()
            t0 = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=timeout_seconds, transport=self._transport) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {slot.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
            except httpx.TimeoutException as exc:
                self.rotator.record_failure(slot, ProviderErrorKind.TIMEOUT, str(exc))
                last_err = ProviderError(
                    f"Grok request timed out on {slot.alias}: {exc}",
                    provider="GROK",
                    kind=ProviderErrorKind.TIMEOUT,
                    key_alias=slot.alias,
                    retryable=True,
                )
                continue
            except httpx.HTTPError as exc:
                self.rotator.record_failure(slot, ProviderErrorKind.NETWORK_ERROR, str(exc))
                last_err = ProviderError(
                    f"Grok network error on {slot.alias}: {exc}",
                    provider="GROK",
                    kind=ProviderErrorKind.NETWORK_ERROR,
                    key_alias=slot.alias,
                    retryable=True,
                )
                continue

            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            if resp.status_code >= 400:
                kind, retryable = _classify_http_error(resp.status_code, resp.text)
                self.rotator.record_failure(slot, kind, f"HTTP {resp.status_code}: {resp.text[:200]}")
                last_err = ProviderError(
                    f"Grok API error ({resp.status_code}) on {slot.alias}: {resp.text[:200]}",
                    provider="GROK",
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
            choices = data.get("choices") or []
            if not choices:
                raise ProviderError(
                    "Grok returned empty choices array.",
                    provider="GROK",
                    kind=ProviderErrorKind.PROVIDER_SERVER_ERROR,
                    key_alias=slot.alias,
                    retryable=True,
                )
            msg = choices[0].get("message") or {}
            text = msg.get("content") or ""
            raw_calls = msg.get("tool_calls") or []
            parsed_calls: List[ToolCallRequest] = []
            for tc in raw_calls:
                fn = tc.get("function") or {}
                raw_args = fn.get("arguments", "{}")
                if isinstance(raw_args, str):
                    try:
                        args_obj = json.loads(raw_args) if raw_args.strip() else {}
                    except json.JSONDecodeError:
                        args_obj = {}
                elif isinstance(raw_args, dict):
                    args_obj = raw_args
                else:
                    args_obj = {}
                parsed_calls.append(
                    ToolCallRequest(
                        tool_call_id=tc.get("id") or f"GROK-CALL-{uuid.uuid4().hex[:8].upper()}",
                        name=fn.get("name", ""),
                        arguments=args_obj,
                    )
                )

            return ProviderResponse(
                provider="GROK",
                model_id=data.get("model", self.model_id),
                key_alias=slot.alias,
                response_id=data.get("id", ""),
                text=text,
                tool_calls=parsed_calls,
                latency_ms=latency_ms,
                finish_reason=choices[0].get("finish_reason", "stop") or "stop",
                raw_usage=data.get("usage") or {},
            )

        raise last_err or ProviderError("Grok provider exhausted retries.", provider="GROK", kind=ProviderErrorKind.PROVIDER_SERVER_ERROR)

    def status(self) -> Dict[str, Any]:
        return {
            **self.rotator.status(),
            "model_id": self.model_id,
            "base_url": self.base_url,
        }
