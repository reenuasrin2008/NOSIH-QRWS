"""Independent round-robin API key rotator with health, cooldown, and error classification."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ProviderErrorKind(str, Enum):
    NETWORK_ERROR = "NETWORK_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AUTH_INVALID = "AUTH_INVALID"
    UNSUPPORTED_MODEL = "UNSUPPORTED_MODEL"
    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    PROVIDER_SERVER_ERROR = "PROVIDER_SERVER_ERROR"
    UNCONFIGURED = "UNCONFIGURED"
    TIMEOUT = "TIMEOUT"


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        kind: ProviderErrorKind,
        key_alias: str = "",
        status_code: Optional[int] = None,
        retryable: bool = True,
    ):
        super().__init__(message)
        self.provider = provider
        self.kind = kind
        self.key_alias = key_alias
        self.status_code = status_code
        self.retryable = retryable


def mask_api_key(key: str) -> str:
    if not key:
        return "(not configured)"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


@dataclass
class KeySlot:
    index: int
    alias: str
    api_key: str
    health: str = "HEALTHY"  # HEALTHY, COOLDOWN, AUTH_INVALID, UNCONFIGURED
    consecutive_failures: int = 0
    last_success_at: Optional[str] = None
    last_error: Optional[str] = None
    last_error_kind: Optional[str] = None
    cooldown_until: float = 0.0
    rate_limited: bool = False
    request_count: int = 0
    total_latency_ms: float = 0.0

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def is_available(self, now: Optional[float] = None) -> bool:
        if not self.is_configured():
            return False
        if self.health == "AUTH_INVALID":
            return False
        t = now if now is not None else time.monotonic()
        if self.cooldown_until > t:
            return False
        return True

    def status_dict(self, now: Optional[float] = None) -> Dict[str, Any]:
        t = now if now is not None else time.monotonic()
        rem_cd = max(0.0, round(self.cooldown_until - t, 1)) if self.cooldown_until > t else 0.0
        eff_health = self.health
        if not self.is_configured():
            eff_health = "UNCONFIGURED"
        elif self.health == "COOLDOWN" and rem_cd == 0.0:
            eff_health = "HEALTHY"
        avg_lat = round(self.total_latency_ms / self.request_count, 1) if self.request_count > 0 else 0.0
        return {
            "index": self.index,
            "alias": self.alias,
            "masked_key": mask_api_key(self.api_key),
            "configured": self.is_configured(),
            "health": eff_health,
            "consecutive_failures": self.consecutive_failures,
            "last_success_at": self.last_success_at,
            "cooldown_remaining_s": rem_cd,
            "rate_limited": self.rate_limited and rem_cd > 0.0,
            "request_count": self.request_count,
            "avg_latency_ms": avg_lat,
            "last_error_kind": self.last_error_kind,
        }


class RoundRobinKeyRotator:
    """Strict per-provider round-robin key rotation: Req 1 -> Key 1, Req 2 -> Key 2, Req 3 -> Key 3, Req 4 -> Key 1."""

    def __init__(
        self,
        provider_name: str,
        api_keys: List[str],
        *,
        cooldown_rate_limit_s: int = 45,
        cooldown_quota_s: int = 300,
        cooldown_server_s: int = 20,
    ):
        self.provider_name = provider_name.upper()
        self.cooldown_rate_limit_s = cooldown_rate_limit_s
        self.cooldown_quota_s = cooldown_quota_s
        self.cooldown_server_s = cooldown_server_s
        self._lock = threading.Lock()
        self._cursor: int = 0
        self.last_selected_index: int = -1

        padded = list(api_keys[:3]) + [""] * max(0, 3 - len(api_keys))
        self.slots: List[KeySlot] = [
            KeySlot(
                index=i,
                alias=f"{self.provider_name}_KEY_{i + 1}",
                api_key=(padded[i] or "").strip(),
                health="HEALTHY" if (padded[i] or "").strip() else "UNCONFIGURED",
            )
            for i in range(3)
        ]

    def has_configured_keys(self) -> bool:
        return any(s.is_configured() for s in self.slots)

    def has_available_keys(self) -> bool:
        now = time.monotonic()
        return any(s.is_available(now) for s in self.slots)

    def acquire_next(self) -> KeySlot:
        """Select the next eligible key in strict round-robin order."""
        with self._lock:
            now = time.monotonic()
            n = len(self.slots)
            for offset in range(n):
                idx = (self._cursor + offset) % n
                slot = self.slots[idx]
                if slot.is_available(now):
                    if slot.health == "COOLDOWN" and slot.cooldown_until <= now:
                        slot.health = "HEALTHY"
                        slot.rate_limited = False
                    self._cursor = (idx + 1) % n
                    self.last_selected_index = idx
                    return slot

            if not self.has_configured_keys():
                raise ProviderError(
                    f"No API keys configured for {self.provider_name}. Set {self.provider_name}_API_KEY_1..3 in agent_backend/.env.",
                    provider=self.provider_name,
                    kind=ProviderErrorKind.UNCONFIGURED,
                    retryable=False,
                )
            if all(s.health == "AUTH_INVALID" or not s.is_configured() for s in self.slots):
                raise ProviderError(
                    f"All configured API keys for {self.provider_name} failed authentication (AUTH_INVALID).",
                    provider=self.provider_name,
                    kind=ProviderErrorKind.AUTH_INVALID,
                    retryable=False,
                )
            raise ProviderError(
                f"All configured {self.provider_name} keys are currently in rate-limit/quota cooldown.",
                provider=self.provider_name,
                kind=ProviderErrorKind.RATE_LIMIT,
                retryable=True,
            )

    def record_success(self, slot: KeySlot, latency_ms: float) -> None:
        with self._lock:
            slot.health = "HEALTHY"
            slot.consecutive_failures = 0
            slot.rate_limited = False
            slot.cooldown_until = 0.0
            slot.last_error = None
            slot.last_error_kind = None
            slot.last_success_at = datetime.now(timezone.utc).isoformat()
            slot.request_count += 1
            slot.total_latency_ms += max(0.0, latency_ms)

    def record_failure(self, slot: KeySlot, kind: ProviderErrorKind, error_message: str) -> None:
        with self._lock:
            now = time.monotonic()
            slot.consecutive_failures += 1
            slot.last_error = error_message[:240]
            slot.last_error_kind = kind.value
            if kind == ProviderErrorKind.AUTH_INVALID:
                slot.health = "AUTH_INVALID"
                slot.cooldown_until = 0.0
            elif kind == ProviderErrorKind.RATE_LIMIT:
                slot.health = "COOLDOWN"
                slot.rate_limited = True
                slot.cooldown_until = now + self.cooldown_rate_limit_s
            elif kind == ProviderErrorKind.QUOTA_EXHAUSTED:
                slot.health = "COOLDOWN"
                slot.rate_limited = True
                slot.cooldown_until = now + self.cooldown_quota_s
            elif kind in (ProviderErrorKind.PROVIDER_SERVER_ERROR, ProviderErrorKind.NETWORK_ERROR, ProviderErrorKind.TIMEOUT):
                slot.health = "COOLDOWN"
                slot.cooldown_until = now + self.cooldown_server_s

    def status(self) -> Dict[str, Any]:
        now = time.monotonic()
        active_idx = self.last_selected_index if self.last_selected_index >= 0 else self._cursor
        return {
            "provider": self.provider_name,
            "active_key_index": active_idx,
            "active_key_alias": self.slots[active_idx].alias if 0 <= active_idx < len(self.slots) else "",
            "healthy_keys": sum(1 for s in self.slots if s.is_available(now)),
            "configured_keys": sum(1 for s in self.slots if s.is_configured()),
            "keys": [s.status_dict(now) for s in self.slots],
        }
