"""Shared HTTP plumbing for every external provider: one client, timeouts, retries, caching.

Error messages never include request URLs, because some carry API keys in the query string.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Mapping
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

# Transient failures are retried once. Each attempt has the client timeout (~8 s), so a dead
# provider fails over to its fallback quickly instead of stalling the request.
MAX_ATTEMPTS = 2
RETRY_WAIT = wait_exponential(multiplier=0.5, max=2)
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class ProviderError(Exception):
    """An external service failed or returned something unusable.

    ``body`` holds the parsed JSON error body when there was one, so callers can inspect
    provider-specific error codes.
    """

    def __init__(
        self, provider: str, message: str, *, status: int | None = None, body: Any = None
    ) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.status = status
        self.body = body


class NoRouteError(ProviderError):
    """The router worked but there is no road route between the points. Not retryable."""


class _TransientHTTPError(Exception):
    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"HTTP {response.status_code}")
        self.response = response


_client: httpx.Client | None = None


def get_client() -> httpx.Client:
    """The process-wide HTTP client (connection pooling; thread-safe)."""
    global _client
    if _client is None:
        _client = httpx.Client(
            timeout=settings.HTTP_TIMEOUT_S,
            headers={"User-Agent": settings.NWS_USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )
    return _client


def request_json(
    provider: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout_s: float | None = None,
) -> Any:
    """GET ``url`` and return its JSON body, retrying timeouts, network errors, 429 and 5xx.

    ``timeout_s`` overrides the default per-attempt timeout (``settings.HTTP_TIMEOUT_S``).
    Raises :class:`ProviderError` on any failure.
    """
    timeout: Any = timeout_s if timeout_s is not None else httpx.USE_CLIENT_DEFAULT

    @retry(
        stop=stop_after_attempt(MAX_ATTEMPTS),
        wait=RETRY_WAIT,
        retry=retry_if_exception_type((httpx.TransportError, _TransientHTTPError)),
        reraise=True,
    )
    def attempt() -> httpx.Response:
        response = get_client().get(url, params=params, headers=headers, timeout=timeout)
        if response.status_code in RETRYABLE_STATUS:
            raise _TransientHTTPError(response)
        return response

    try:
        response = attempt()
    except httpx.TimeoutException as exc:
        log.warning("%s timed out", provider)
        raise ProviderError(provider, "request timed out") from exc
    except httpx.TransportError as exc:
        log.warning("%s network error: %s", provider, type(exc).__name__)
        raise ProviderError(provider, f"network error ({type(exc).__name__})") from exc
    except _TransientHTTPError as exc:
        status = exc.response.status_code
        log.warning("%s unavailable: HTTP %s", provider, status)
        raise ProviderError(provider, f"HTTP {status}", status=status) from exc

    try:
        body = response.json()
    except ValueError:
        body = None

    if response.status_code >= 400:
        log.warning("%s rejected request: HTTP %s", provider, response.status_code)
        raise ProviderError(
            provider, f"HTTP {response.status_code}", status=response.status_code, body=body
        )
    if body is None:
        raise ProviderError(provider, "response was not valid JSON", status=response.status_code)
    return body


def cache_key(namespace: str, *parts: object) -> str:
    """A short, safe cache key: the namespace plus a hash of the parts."""
    digest = hashlib.sha1(repr(parts).encode(), usedforsecurity=False).hexdigest()
    return f"{namespace}:{digest}"


def cached[T](key: str, ttl_s: int, fetch: Callable[[], T]) -> T:
    """Return the cached value for ``key``, or call ``fetch`` and cache its result.

    A cache outage degrades to "no cache" rather than failing the request. Errors from
    ``fetch`` are not cached.
    """
    try:
        hit = cache.get(key)
    except Exception:
        log.warning("cache read failed", exc_info=True)
        hit = None
    if hit is not None:
        return hit

    value = fetch()
    try:
        cache.set(key, value, ttl_s)
    except Exception:
        log.warning("cache write failed", exc_info=True)
    return value
