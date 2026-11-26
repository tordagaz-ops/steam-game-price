"""Shared MCP runtime helpers.

This module is the common core reused by every server in this portfolio. It is
deliberately dependency-light (``httpx`` + stdlib only) so that Docker images
stay small and cold starts stay fast.

Design rules
------------
* Never leak a stack trace to the model. Tools return ``{"error": "<code>",
  "message": "<localized text>"}`` instead of raising.
* Every outbound HTTP call goes through :class:`HttpClient`, which applies
  timeouts, bounded retries with jitter and ``Retry-After`` support.
* Upstream responses are cached in-process with single-flight semantics, so a
  burst of identical calls produces one upstream request.
"""

from __future__ import annotations

import asyncio
import email.utils
import os
import random
import time
from typing import Any, Awaitable, Callable

import httpx

__all__ = [
    "DEFAULT_USER_AGENT",
    "HttpClient",
    "TTLCache",
    "UpstreamError",
    "clamp",
    "err",
    "fmt_pct",
    "ms_to_iso",
    "round_or_none",
]

DEFAULT_USER_AGENT = "mcp-tools/1.0 (+https://github.com)"

# Status codes worth retrying: transport hiccups and transient upstream states.
RETRIABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

_MISS = object()


class UpstreamError(Exception):
    """A failed upstream call, already classified for the caller."""

    def __init__(
        self,
        code: str,
        detail: str = "",
        *,
        status: int | None = None,
        retriable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.status = status
        self.retriable = retriable
        self.retry_after = retry_after


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header given either as seconds or as an HTTP date."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    return max(0.0, dt.timestamp() - time.time())


class HttpClient:
    """Minimal async JSON client: retries, jitter, honouring ``Retry-After``."""

    def __init__(
        self,
        base_url: str = "",
        *,
        timeout: float = 12.0,
        attempts: int = 3,
        base_delay: float = 0.35,
        max_delay: float = 3.0,
        headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.attempts = max(1, attempts)
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5.0),
            headers={
                "User-Agent": os.getenv("MCP_HTTP_USER_AGENT", DEFAULT_USER_AGENT),
                "Accept": "application/json",
                **(headers or {}),
            },
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
            follow_redirects=True,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        attempts: int | None = None,
    ) -> Any:
        """GET ``path`` and decode JSON.

        Raises :class:`UpstreamError` with a stable ``code`` on any failure.
        """
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}{path}"
        # Drop None values so callers can pass optional parameters directly.
        query = {k: v for k, v in (params or {}).items() if v is not None} or None
        total = attempts or self.attempts
        last: UpstreamError | None = None

        for index in range(total):
            try:
                response = await self._client.get(url, params=query)
            except httpx.TimeoutException as exc:
                last = UpstreamError("timeout", str(exc) or "request timed out", retriable=True)
            except httpx.HTTPError as exc:
                last = UpstreamError(
                    "network_error", f"{type(exc).__name__}: {exc}", retriable=True
                )
            else:
                if response.status_code in RETRIABLE_STATUS:
                    last = UpstreamError(
                        "upstream_unavailable",
                        f"HTTP {response.status_code}",
                        status=response.status_code,
                        retriable=True,
                        retry_after=_parse_retry_after(response.headers.get("Retry-After")),
                    )
                elif response.status_code >= 400:
                    raise UpstreamError(
                        "upstream_rejected",
                        f"HTTP {response.status_code}: {response.text[:200]}",
                        status=response.status_code,
                    )
                else:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise UpstreamError(
                            "bad_payload", "upstream response is not valid JSON"
                        ) from exc

            if index < total - 1:
                await asyncio.sleep(self._backoff(index, last))

        raise last or UpstreamError("upstream_unavailable", "no attempt was made")

    def _backoff(self, attempt: int, error: UpstreamError | None) -> float:
        if error is not None and error.retry_after is not None:
            return min(error.retry_after, self.max_delay)
        delay = min(self.base_delay * (2**attempt), self.max_delay)
        return delay * (0.75 + random.random() * 0.5)


class TTLCache:
    """Tiny in-process TTL cache with single-flight de-duplication."""

    def __init__(self, max_entries: int = 256) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._max_entries = max_entries

    def peek(self, key: str) -> Any:
        """Return the cached value or the module sentinel ``_MISS``."""
        entry = self._data.get(key)
        if entry is None:
            return _MISS
        expires_at, value = entry
        if expires_at <= time.monotonic():
            self._data.pop(key, None)
            return _MISS
        return value

    def store(self, key: str, value: Any, ttl: float) -> None:
        if len(self._data) >= self._max_entries:
            self._prune()
        self._data[key] = (time.monotonic() + ttl, value)

    async def get_or_set(
        self, key: str, ttl: float, factory: Callable[[], Awaitable[Any]]
    ) -> Any:
        cached = self.peek(key)
        if cached is not _MISS:
            return cached
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self.peek(key)
            if cached is not _MISS:
                return cached
            value = await factory()
            self.store(key, value, ttl)
            return value

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._data.items() if exp <= now]
        for key in expired:
            self._data.pop(key, None)
        # Still full: drop the entries closest to expiry.
        if len(self._data) >= self._max_entries:
            for key, _ in sorted(self._data.items(), key=lambda kv: kv[1][0])[:64]:
                self._data.pop(key, None)


def err(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """Build the canonical error payload returned by every tool."""
    payload: dict[str, Any] = {"error": code, "message": message}
    payload.update(extra)
    return payload


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def round_or_none(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def fmt_pct(value: float | None, digits: int = 4) -> float | None:
    """Convert a fraction (0.0001) into a percentage number (0.01)."""
    if value is None:
        return None
    return round(value * 100.0, digits)


def ms_to_iso(timestamp_ms: int | float | str | None) -> str | None:
    """Convert a millisecond epoch to an ISO-8601 UTC string."""
    if timestamp_ms in (None, ""):
        return None
    try:
        seconds = float(timestamp_ms) / 1000.0
    except (TypeError, ValueError):
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))
