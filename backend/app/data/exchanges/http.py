"""Shared HTTP utilities for exchange connectors."""
from __future__ import annotations

from typing import Any, Mapping

import httpx


class HTTPExchangeClient:
    """Lightweight async HTTP client wrapper for exchange data sources."""

    base_url: str
    venue: str

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._external_client = client
        self._timeout = timeout
        self._headers = dict(headers or {})

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        url = self._build_url(path)
        if self._external_client is not None:
            response = await self._external_client.request(method, url, params=params, headers=self._headers)
            response.raise_for_status()
            return response.json()

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout, headers=self._headers) as client:
            response = await client.request(method, path, params=params)
            response.raise_for_status()
            return response.json()

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if path.startswith("/"):
            return f"{self.base_url}{path}"
        return f"{self.base_url}/{path}"






