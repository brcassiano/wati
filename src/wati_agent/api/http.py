"""Shared HTTP client base for WATI API clients."""

from __future__ import annotations

import time

import httpx
import structlog


class BaseHttpClient:
    """Base class with shared httpx setup and request logging.

    Both V3 and V1 clients inherit this to avoid duplicating
    connection setup, teardown, and request instrumentation.
    """

    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout: float = 30.0,
        *,
        log_event: str = "wati_api_call",
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        self._log_event = log_event
        self._logger = structlog.get_logger(type(self).__name__)

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> httpx.Response:
        """Execute HTTP request with timing and structured logging."""
        start = time.monotonic()
        resp = await self._http.request(method, path, params=params, json=json_body)
        elapsed_ms = (time.monotonic() - start) * 1000
        self._logger.debug(
            self._log_event,
            method=method,
            path=path,
            status=resp.status_code,
            duration_ms=round(elapsed_ms, 1),
        )
        resp.raise_for_status()
        return resp
