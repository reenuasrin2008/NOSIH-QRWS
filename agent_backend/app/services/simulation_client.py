"""HTTP client connecting the AI Rescue Agent to the authoritative simulation backend (:8000)."""
from __future__ import annotations

from typing import Any, Dict, Optional
import httpx


class SimulationAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int = 500, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class SimulationClient:
    """Async REST client for http://127.0.0.1:8000 (single source of truth)."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", transport: Optional[httpx.AsyncBaseTransport] = None, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self.timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self._transport,
        )

    async def request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json_body: Optional[Dict[str, Any]] = None) -> Any:
        try:
            async with self._client() as client:
                resp = await client.request(method, path, params=params, json=json_body)
        except httpx.HTTPError as exc:
            raise SimulationAPIError(f"Simulation backend unreachable at {self.base_url}: {exc}", status_code=503) from exc

        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            msg = detail.get("detail") if isinstance(detail, dict) and "detail" in detail else str(detail)
            raise SimulationAPIError(f"Simulation API {method} {path} failed ({resp.status_code}): {msg}", status_code=resp.status_code, detail=detail)

        ctype = resp.headers.get("content-type", "")
        if "application/json" in ctype:
            return resp.json()
        return {"status_code": resp.status_code, "content_length": len(resp.content), "content_type": ctype}

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        return await self.request("POST", path, params=params, json_body=json_body)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def get_world_version(self) -> int:
        try:
            data = await self.get("/api/world/version")
            return int(data.get("state_version", 0))
        except Exception:
            return 0
